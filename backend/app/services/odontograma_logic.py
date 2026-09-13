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
    GRUPO_ENDO,
    GRUPO_EXCLUSIVE,
    CondicionIndividualPuente,
    TipoHallazgo,
    TipoLesionApical,
)
from app.models.common import ahora
from app.models.odontograma import DienteAnatomia, OdontogramaHallazgo
from app.schemas.odontograma import OdontogramaHallazgoCreate


def grupo_de(tipo: TipoHallazgo) -> str:
    if tipo in GRUPO_EXCLUSIVE:
        return "exclusive"
    if tipo in GRUPO_ENDO:
        return "endo"
    return "independent"


async def aplicar_hallazgo(
    session: AsyncSession,
    paciente_id: UUID,
    numero_diente: int,
    datos: OdontogramaHallazgoCreate,
) -> OdontogramaHallazgo:
    """
    Crea un hallazgo aplicando las reglas de exclusividad de la seccion 3.3:
    - exclusive desactiva cualquier otro hallazgo activo del diente.
    - endo desactiva los demas endo activos, pero no los independent.
    - independent (y endo) desactivan cualquier exclusive activo.

    "Desactivar" = activo=False (cierra el hallazgo sin borrar el historico,
    seccion 1.2), nunca DELETE.
    """
    grupo_nuevo = grupo_de(datos.tipo_hallazgo)

    resultado = await session.execute(
        select(OdontogramaHallazgo).where(
            OdontogramaHallazgo.paciente_id == paciente_id,
            OdontogramaHallazgo.numero_diente == numero_diente,
            OdontogramaHallazgo.activo.is_(True),
        )
    )
    activos = list(resultado.scalars().all())

    for existente in activos:
        grupo_existente = grupo_de(existente.tipo_hallazgo)
        debe_desactivar = (
            grupo_nuevo == "exclusive"
            or (grupo_nuevo == "endo" and grupo_existente in ("exclusive", "endo"))
            or (grupo_nuevo == "independent" and grupo_existente == "exclusive")
        )
        if debe_desactivar:
            existente.activo = False
            existente.actualizado_en = ahora()
            existente.actualizado_por = datos.creado_por

    nuevo = OdontogramaHallazgo(
        paciente_id=paciente_id,
        numero_diente=numero_diente,
        visita_id=datos.visita_id,
        tipo_hallazgo=datos.tipo_hallazgo,
        superficie=datos.superficie,
        fecha=datos.fecha,
        activo=True,
        notas=datos.notas,
        creado_por=datos.creado_por,
    )
    session.add(nuevo)
    await session.commit()
    await session.refresh(nuevo)
    return nuevo


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
            OdontogramaHallazgo.activo.is_(True),
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
