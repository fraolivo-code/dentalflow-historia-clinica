# app/services/tratamiento_realizado.py — Accion «Tratamiento realizado» del odontograma
# (flujo de visitas, fase 2, 15/10/2026). Una sola accion atomica, con la fecha de la visita:
# cierra los hallazgos "antes" y abre los "despues", segun la tabla confirmada por la Dra.
# (especificacion-tecnica-flujo-visitas-tratamientos.md, seccion 5).
#
# Las reglas viven solo aqui: la pantalla las lee del endpoint de reglas, asi no hay una
# segunda copia que mantener. El cierre por defecto es una propuesta: la pantalla muestra
# los hallazgos activos del diente con casillas y la Dra. confirma cual se cierra.

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import SuperficieDental, TipoHallazgo, TratamientoRealizado
from app.models.bitacora_tratamiento import BitacoraDiente, BitacoraTratamiento
from app.models.common import ahora
from app.models.odontograma import OdontogramaHallazgo
from app.models.tratamiento import Tratamiento
from app.models.visita import Visita
from app.schemas.odontograma import OdontogramaHallazgoCreate
from app.services import etiquetas
from app.services.odontograma_logic import aplicar_hallazgo

T = TipoHallazgo
S = SuperficieDental


@dataclass(frozen=True)
class Regla:
    nombre: str
    abre: tuple[TipoHallazgo, ...]
    cierra: tuple[TipoHallazgo, ...]  # cierre por defecto (propuesta)
    # "no": sin superficie · "elegir": una o varias de las seis · "diastema": mesial / distal
    superficies: str = "no"
    # El cierre por defecto solo alcanza a las superficies elegidas.
    cierra_en_superficies: bool = False
    # Si no esta vacio, la Dra. elige el resultado entre estos (carilla).
    resultados: tuple[TipoHallazgo, ...] = ()


REGLAS: dict[TratamientoRealizado, Regla] = {
    TratamientoRealizado.restauracion: Regla(
        "Restauración (resina)", (T.obturacion_ok,), (T.caries, T.obturacion_defecto),
        superficies="elegir", cierra_en_superficies=True,
    ),
    TratamientoRealizado.cambio_restauracion: Regla(
        "Cambio de una restauración mala", (T.obturacion_ok,), (T.obturacion_defecto,),
        superficies="elegir", cierra_en_superficies=True,
    ),
    TratamientoRealizado.endodoncia: Regla(
        "Endodoncia", (T.conducto_ok,), (T.conducto_indicado, T.conducto_defecto)
    ),
    TratamientoRealizado.perno: Regla("Perno", (T.perno_ok,), (T.perno_defecto,)),
    TratamientoRealizado.extraccion: Regla("Extracción (simple o quirúrgica)", (T.ausente,), ()),
    TratamientoRealizado.corona: Regla(
        "Corona", (T.corona_ok,), (T.caries, T.obturacion_defecto, T.corona_defecto)
    ),
    TratamientoRealizado.carilla: Regla(
        "Carilla", (), (T.caries, T.obturacion_defecto, T.carilla_defecto),
        resultados=(T.carilla_ok, T.corona_ok, T.ausente),
    ),
    TratamientoRealizado.implante: Regla(
        "Implante colocado", (T.implante,), (T.ausente, T.exodoncia_simple, T.exodoncia_quirurgica)
    ),
    TratamientoRealizado.sellante: Regla("Sellante", (T.sellante,), (T.spp,)),
    TratamientoRealizado.diastema_resina: Regla(
        "Diastema cerrado con resina", (T.obturacion_ok,), (T.diastema,),
        superficies="diastema", cierra_en_superficies=True,
    ),
    TratamientoRealizado.diastema_carilla: Regla(
        "Diastema cerrado con carilla", (T.carilla_ok,), (T.diastema,)
    ),
    TratamientoRealizado.diastema_ortodoncia: Regla("Diastema cerrado con ortodoncia", (), (T.diastema,)),
}

_SUPERFICIES_DIASTEMA = frozenset({S.mesial, S.distal})


def _a_abrir(regla: Regla, resultado: TipoHallazgo | None, superficies: list[S]) -> list[tuple[T, S | None]]:
    """Lista (tipo, superficie) de los hallazgos que se abren."""
    if regla.resultados:
        if resultado not in regla.resultados:
            opciones = ", ".join(r.value for r in regla.resultados)
            raise HTTPException(422, f"Elija el resultado del tratamiento: {opciones}.")
        return [(resultado, S.vestibular if resultado == T.carilla_ok else None)]
    if regla.superficies in ("elegir", "diastema"):
        return [(regla.abre[0], s) for s in superficies]
    return [(t, S.vestibular if t == T.carilla_ok else None) for t in regla.abre]


def _validar_superficies(regla: Regla, superficies: list[S]) -> list[S]:
    unicas = list(dict.fromkeys(superficies))
    if regla.superficies == "no":
        return []
    if not unicas:
        raise HTTPException(422, "Indique al menos una superficie.")
    if regla.superficies == "diastema" and not set(unicas) <= _SUPERFICIES_DIASTEMA:
        raise HTTPException(422, "Un diastema se cierra en la superficie mesial o distal.")
    return unicas


def _texto_hallazgo(h: OdontogramaHallazgo) -> str:
    return etiquetas.etiqueta_hallazgo(h.tipo_hallazgo, h.superficie, h.numero_diente)


async def registrar(
    session: AsyncSession,
    paciente_id: UUID,
    numero_diente: int,
    *,
    tratamiento: TratamientoRealizado,
    fecha: date,
    superficies: list[S],
    resultado: TipoHallazgo | None,
    cierra_ids: list[UUID] | None,
    descripcion: str | None,
    visita_id: UUID | None,
    tratamiento_id: UUID | None,
    usuario_id: UUID,
) -> tuple[list[OdontogramaHallazgo], list[OdontogramaHallazgo], BitacoraTratamiento]:
    regla = REGLAS[tratamiento]
    superficies = _validar_superficies(regla, superficies)
    a_abrir = _a_abrir(regla, resultado, superficies)

    if visita_id is not None:
        visita = await session.get(Visita, visita_id)
        if visita is None or visita.paciente_id != paciente_id:
            raise HTTPException(422, "La visita no existe o no es de este paciente.")
    if tratamiento_id is not None:
        trat = await session.get(Tratamiento, tratamiento_id)
        if trat is None or trat.paciente_id != paciente_id:
            raise HTTPException(422, "El tratamiento no existe o no es de este paciente.")

    activos = list(
        (
            await session.execute(
                select(OdontogramaHallazgo).where(
                    OdontogramaHallazgo.paciente_id == paciente_id,
                    OdontogramaHallazgo.numero_diente == numero_diente,
                    OdontogramaHallazgo.resuelto.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    por_id = {h.id: h for h in activos}
    if cierra_ids is None:
        a_cerrar = [
            h
            for h in activos
            if h.tipo_hallazgo in regla.cierra
            and (not regla.cierra_en_superficies or h.superficie in superficies)
        ]
    else:
        faltan = [i for i in dict.fromkeys(cierra_ids) if i not in por_id]
        if faltan:
            raise HTTPException(
                422, "Un hallazgo a cerrar no está activo en este diente o no es de este paciente."
            )
        a_cerrar = [por_id[i] for i in dict.fromkeys(cierra_ids)]

    for h in a_cerrar:
        if fecha < h.fecha:
            raise HTTPException(
                422,
                f"La fecha no puede ser anterior a la del hallazgo que se cierra: "
                f"{_texto_hallazgo(h)}, desde {h.fecha.strftime('%d/%m/%Y')}.",
            )

    # Todo en una transaccion: si algo falla (duplicado, puente activo) no se guarda nada.
    abiertos: list[OdontogramaHallazgo] = []
    for tipo, superficie in a_abrir:
        abiertos.append(
            await aplicar_hallazgo(
                session,
                paciente_id,
                numero_diente,
                OdontogramaHallazgoCreate(
                    numero_diente=numero_diente,
                    visita_id=visita_id,
                    tipo_hallazgo=tipo,
                    superficie=superficie,
                    fecha=fecha,
                    notas=None,
                    tratamiento_id=tratamiento_id,
                ),
                usuario_id,
                commit=False,
            )
        )

    cerrados: list[OdontogramaHallazgo] = []
    for h in a_cerrar:
        if h.resuelto:  # ya lo cerro la exclusividad al abrir el nuevo (p. ej. ausente)
            cerrados.append(h)
            continue
        h.resuelto = True
        h.resuelto_fecha = fecha
        h.resuelto_por_hallazgo_id = abiertos[0].id if abiertos else None
        h.actualizado_en = ahora()
        h.actualizado_por = usuario_id
        cerrados.append(h)

    texto = descripcion.strip() if descripcion and descripcion.strip() else None
    if texto is None:
        partes = [f"{regla.nombre}, diente {numero_diente}"]
        if abiertos:
            partes.append("queda: " + ", ".join(_texto_hallazgo(h) for h in abiertos))
        if cerrados:
            partes.append("se cierra: " + ", ".join(_texto_hallazgo(h) for h in cerrados))
        texto = ". ".join(partes) + "."
    entrada = BitacoraTratamiento(
        paciente_id=paciente_id,
        visita_id=visita_id,
        fecha=fecha,
        responsable=usuario_id,
        descripcion=texto,
        numero_diente=numero_diente,
        tratamiento_id=tratamiento_id,
        creado_por=usuario_id,
    )
    session.add(entrada)
    await session.flush()
    session.add(BitacoraDiente(bitacora_id=entrada.id, numero_diente=numero_diente, creado_por=usuario_id))

    await session.commit()
    for h in abiertos + cerrados:
        await session.refresh(h)
    return cerrados, abiertos, entrada


def catalogo() -> list[dict]:
    """Las reglas, para que la pantalla no tenga su propia copia."""
    return [
        {
            "codigo": codigo.value,
            "nombre": regla.nombre,
            "superficies": regla.superficies,
            "resultados": [r.value for r in regla.resultados],
            "abre": [t.value for t in regla.abre],
            "cierra_por_defecto": [t.value for t in regla.cierra],
            "cierra_en_superficies": regla.cierra_en_superficies,
        }
        for codigo, regla in REGLAS.items()
    ]
