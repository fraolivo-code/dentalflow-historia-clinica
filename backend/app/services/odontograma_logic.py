# app/services/odontograma_logic.py — Logica de interaccion validada en el
# prototipo (seccion 3 de la especificacion): reglas de exclusividad (3.1/3.3),
# orden anatomico real para modo puente (3.2), y calculo de
# periapical vs. periimplantitis (1.3).

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import (
    CONDICION_INDIVIDUAL_PUENTE_VALIDAS,
    GRUPO_CONDICION,
    GRUPO_ENDO,
    GRUPO_EXCLUSIVE,
    CondicionIndividualPuente,
    OrigenHallazgo,
    SuperficieDental,
    TipoHallazgo,
    TipoLesionApical,
)
from app.models.common import ahora
from app.models.odontograma import DienteAnatomia, OdontogramaHallazgo, OdontogramaLesionApical
from app.schemas.odontograma import OdontogramaHallazgoCreate


def grupo_de(tipo: TipoHallazgo) -> str:
    if tipo in GRUPO_EXCLUSIVE:
        return "exclusive"
    if tipo in GRUPO_ENDO:
        return "endo"
    if tipo in GRUPO_CONDICION:
        return "condicion"
    return "independent"


async def buscar_duplicado_activo(
    session: AsyncSession,
    paciente_id: UUID,
    numero_diente: int,
    tipo: TipoHallazgo,
    superficie: SuperficieDental | None,
) -> OdontogramaHallazgo | None:
    """
    Hallazgo activo identico (mismo diente + tipo + superficie) al que se
    quiere crear, o None (23/09/2026). superficie se compara con
    IS NOT DISTINCT FROM, asi dos superficies NULL cuentan como iguales.
    """
    resultado = await session.execute(
        select(OdontogramaHallazgo)
        .where(
            OdontogramaHallazgo.paciente_id == paciente_id,
            OdontogramaHallazgo.numero_diente == numero_diente,
            OdontogramaHallazgo.tipo_hallazgo == tipo,
            OdontogramaHallazgo.superficie.is_not_distinct_from(superficie),
            OdontogramaHallazgo.resuelto.is_(False),
        )
        .limit(1)
    )
    return resultado.scalar_one_or_none()


async def aplicar_hallazgo(
    session: AsyncSession,
    paciente_id: UUID,
    numero_diente: int,
    datos: OdontogramaHallazgoCreate,
    creado_por: UUID,
) -> OdontogramaHallazgo:
    """
    Crea un hallazgo aplicando las reglas de exclusividad de la seccion 3.3:
    - exclusive desactiva cualquier otro hallazgo activo del diente.
    - endo desactiva los demas endo activos, pero no los independent.
    - independent (y endo) desactivan cualquier exclusive activo.
    - condicion (diastema) no desactiva nada, y ningun hallazgo nuevo la
      desactiva a ella — ni siquiera un exclusive.

    Si ya existe un hallazgo activo identico (buscar_duplicado_activo),
    responde 409 sin crear ni cerrar nada.

    Lesiones apicales (23/09/2026, cerrar_lesiones_por_hallazgo): son
    independientes de la exclusividad, salvo que el diente pierda la raiz
    natural o el implante — ver esa funcion.

    "Desactivar" = resuelto=True (cierra el hallazgo sin borrar el historico,
    seccion 1.2), nunca DELETE. Ademas registra resuelto_fecha y
    resuelto_por_hallazgo_id (Etapa 3, seccion 7).

    El INSERT del nuevo hallazgo se hace (via flush) antes de los UPDATE que
    lo referencian en resuelto_por_hallazgo_id: es una FK autorreferencial
    sin `relationship()` declarada, asi que SQLAlchemy no sabe ordenarlos
    solo — si no se fuerza el orden, el UPDATE puede viajar antes que el
    INSERT y Postgres lo rechaza (la fila referenciada todavia no existe).
    """
    duplicado = await buscar_duplicado_activo(
        session, paciente_id, numero_diente, datos.tipo_hallazgo, datos.superficie
    )
    if duplicado is not None:
        detalle_superficie = f" ({duplicado.superficie.value})" if duplicado.superficie else ""
        raise HTTPException(
            409,
            detail={
                "mensaje": (
                    f"El diente {numero_diente} ya tiene un hallazgo activo de "
                    f"{datos.tipo_hallazgo.value}{detalle_superficie}"
                ),
                "hallazgo_existente_id": str(duplicado.id),
            },
        )

    grupo_nuevo = grupo_de(datos.tipo_hallazgo)

    resultado = await session.execute(
        select(OdontogramaHallazgo).where(
            OdontogramaHallazgo.paciente_id == paciente_id,
            OdontogramaHallazgo.numero_diente == numero_diente,
            OdontogramaHallazgo.resuelto.is_(False),
        )
    )
    activos = list(resultado.scalars().all())

    a_desactivar = []
    for existente in activos:
        grupo_existente = grupo_de(existente.tipo_hallazgo)
        # Un grupo_nuevo "condicion" no cumple ninguna rama: no cierra nada.
        debe_desactivar = grupo_existente != "condicion" and (
            grupo_nuevo == "exclusive"
            or (grupo_nuevo == "endo" and grupo_existente in ("exclusive", "endo"))
            or (grupo_nuevo == "independent" and grupo_existente == "exclusive")
        )
        if debe_desactivar:
            a_desactivar.append(existente)

    nuevo = OdontogramaHallazgo(
        paciente_id=paciente_id,
        numero_diente=numero_diente,
        visita_id=datos.visita_id,
        tipo_hallazgo=datos.tipo_hallazgo,
        superficie=datos.superficie,
        fecha=datos.fecha,
        resuelto=False,
        # Todo lo creado por esta API se origina en este consultorio; el caso
        # "externo" (paciente remitido) se resuelve manualmente, sin pasar
        # por esta funcion.
        origen=OrigenHallazgo.aqui,
        tratamiento_id=datos.tratamiento_id,
        notas=datos.notas,
        creado_por=creado_por,
    )
    session.add(nuevo)
    await session.flush()  # inserta `nuevo` antes de que algo lo referencie

    for existente in a_desactivar:
        existente.resuelto = True
        existente.resuelto_fecha = datos.fecha
        existente.resuelto_por_hallazgo_id = nuevo.id
        existente.actualizado_en = ahora()
        existente.actualizado_por = creado_por

    await cerrar_lesiones_por_hallazgo(
        session,
        paciente_id,
        numero_diente,
        nuevo,
        cierra_implante=any(h.tipo_hallazgo == TipoHallazgo.implante for h in a_desactivar),
        creado_por=creado_por,
    )

    await session.commit()
    await session.refresh(nuevo)
    return nuevo


async def cerrar_lesiones_por_hallazgo(
    session: AsyncSession,
    paciente_id: UUID,
    numero_diente: int,
    nuevo: OdontogramaHallazgo,
    cierra_implante: bool,
    creado_por: UUID,
) -> None:
    """
    Cierre automatico de lesiones apicales (opcion A, confirmada 23/09/2026),
    en la misma transaccion que el hallazgo nuevo:
    - "ausente" cierra todas las lesiones activas del diente (periapicales y
      periimplantitis: ya no hay ni raiz ni implante).
    - "implante" cierra las periapicales (el diente ya no tiene raiz natural).
    - Si el hallazgo nuevo cierra un "implante" activo (por exclusividad),
      se cierra tambien la periimplantitis.
    Ningun otro hallazgo toca las lesiones — "sano" o un endo no las cierran.
    """
    tipos_a_cerrar: set[TipoLesionApical] = set()
    if nuevo.tipo_hallazgo == TipoHallazgo.ausente:
        tipos_a_cerrar = {TipoLesionApical.periapical, TipoLesionApical.periimplantitis}
    elif nuevo.tipo_hallazgo == TipoHallazgo.implante:
        tipos_a_cerrar = {TipoLesionApical.periapical}
    if cierra_implante:
        tipos_a_cerrar.add(TipoLesionApical.periimplantitis)
    if not tipos_a_cerrar:
        return

    resultado = await session.execute(
        select(OdontogramaLesionApical).where(
            OdontogramaLesionApical.paciente_id == paciente_id,
            OdontogramaLesionApical.numero_diente == numero_diente,
            OdontogramaLesionApical.resuelto.is_(False),
            OdontogramaLesionApical.tipo.in_(tipos_a_cerrar),
        )
    )
    for lesion in resultado.scalars().all():
        lesion.resuelto = True
        lesion.resuelto_fecha = nuevo.fecha
        lesion.resuelto_por_hallazgo_id = nuevo.id
        lesion.actualizado_en = ahora()
        lesion.actualizado_por = creado_por


async def buscar_lesion_duplicada_activa(
    session: AsyncSession, paciente_id: UUID, numero_diente: int, raiz: str
) -> OdontogramaLesionApical | None:
    """Lesion activa en el mismo diente y la misma raiz (23/09/2026)."""
    resultado = await session.execute(
        select(OdontogramaLesionApical)
        .where(
            OdontogramaLesionApical.paciente_id == paciente_id,
            OdontogramaLesionApical.numero_diente == numero_diente,
            OdontogramaLesionApical.raiz == raiz,
            OdontogramaLesionApical.resuelto.is_(False),
        )
        .limit(1)
    )
    return resultado.scalar_one_or_none()


async def resolver_tipo_lesion_apical(
    session: AsyncSession, paciente_id: UUID, numero_diente: int, raiz: str
) -> TipoLesionApical:
    """
    Valida `raiz` y determina periapical vs. periimplantitis (seccion 1.3):
    el tipo se calcula segun si el diente tiene "implante" activo, nunca lo
    manda el cliente.
    """
    tiene_implante = await session.execute(
        select(OdontogramaHallazgo.id).where(
            OdontogramaHallazgo.paciente_id == paciente_id,
            OdontogramaHallazgo.numero_diente == numero_diente,
            OdontogramaHallazgo.tipo_hallazgo == TipoHallazgo.implante,
            OdontogramaHallazgo.resuelto.is_(False),
        )
    )
    es_implante = tiene_implante.scalar_one_or_none() is not None

    if es_implante:
        if raiz != "Periimplantitis":
            raise HTTPException(
                400, "El diente tiene implante activo: raiz debe ser 'Periimplantitis'"
            )
        return TipoLesionApical.periimplantitis

    anatomia = await session.get(DienteAnatomia, numero_diente)
    if anatomia is None:
        raise HTTPException(400, f"Diente {numero_diente} no existe en diente_anatomia")
    if raiz not in anatomia.nombres_raices:
        raise HTTPException(
            400,
            f"raiz '{raiz}' invalida para el diente {numero_diente}; "
            f"opciones: {anatomia.nombres_raices}",
        )
    return TipoLesionApical.periapical


def resolver_condicion_individual_puente(condicion: CondicionIndividualPuente) -> TipoHallazgo:
    """
    Convierte el enum angosto del schema (capa 1: 8 valores) al TipoHallazgo
    con el que se persiste (la columna reutiliza el enum tipo_hallazgo de
    Postgres, no duplica uno propio). Vuelve a chequear contra
    CONDICION_INDIVIDUAL_PUENTE_VALIDAS antes de convertir — capa 2, defensa
    en profundidad detras del schema; la capa 3 es el CHECK de la DB.
    """
    tipo = TipoHallazgo(condicion.value)
    if tipo not in CONDICION_INDIVIDUAL_PUENTE_VALIDAS:
        raise HTTPException(
            400,
            f"condicion_individual '{condicion.value}' no es valida dentro de un puente; "
            f"opciones: {sorted(c.value for c in CONDICION_INDIVIDUAL_PUENTE_VALIDAS)}",
        )
    return tipo


def orden_anatomico(numero_diente: int) -> tuple[int, int]:
    """
    Indice de posicion real en el arco (seccion 3.2): NO es el valor numerico
    del diente. Para cuadrantes 1 y 4, mesial (posicion 1) queda mas cerca de
    la linea media; para cuadrantes 2 y 3, tambien. Recorriendo el arco de
    posterior a posterior cruzando la linea media (ej. 18..11,21..28 arriba;
    48..41,31..38 abajo), el orden queda correcto incluso cuando el puente
    cruza de un cuadrante a otro (ej. 41->31), que es el bug que corrigio el
    prototipo.
    """
    cuadrante = numero_diente // 10
    posicion = numero_diente % 10
    arco = 0 if cuadrante in (1, 2) else 1  # 0 = superior, 1 = inferior
    if cuadrante in (1, 4):
        indice = 8 - posicion
    else:  # cuadrante in (2, 3)
        indice = 7 + posicion
    return (arco, indice)


def validar_contiguidad_puente(numeros_diente: list[int]) -> None:
    """
    Un puente fijo no puede tener saltos: cada posicion anatomica entre el
    primer y el ultimo diente debe estar representada por una fila en
    puente_fijo_diente (como pilar o como pontico/fantoma). Si falta una
    posicion intermedia, ese diente faltante no quedaria registrado en
    ninguna parte del puente.

    No estaba implementada hasta ahora — solo se validaba el minimo de 2
    dientes (seccion 3.2 / hueco identificado pendiente de cerrar).
    """
    if len(set(numeros_diente)) != len(numeros_diente):
        raise HTTPException(400, "Un puente fijo no puede repetir el mismo diente")

    posiciones = sorted(orden_anatomico(n) for n in numeros_diente)

    arcos = {p[0] for p in posiciones}
    if len(arcos) > 1:
        raise HTTPException(
            400, "Un puente fijo no puede cruzar del arco superior al inferior"
        )

    indices = [p[1] for p in posiciones]
    for anterior, siguiente in zip(indices, indices[1:]):
        if siguiente - anterior != 1:
            raise HTTPException(
                400,
                "Los dientes del puente deben ser anatomicamente contiguos, sin saltos "
                "(falta un diente pilar o pontico en una posicion intermedia)",
            )
