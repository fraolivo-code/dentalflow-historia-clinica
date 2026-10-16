# app/services/enlazar_visita.py — Enlaza a una visita lo que se cargo con su fecha antes de que la
# pantalla enlazara por si sola (15/10/2026): entradas de bitacora y hallazgos del odontograma de ese
# dia que no tienen visita. Procedimiento aparte (scripts/enlazar_visita.py); no borra nada.

from datetime import date
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bitacora_tratamiento import BitacoraTratamiento
from app.models.odontograma import OdontogramaHallazgo
from app.models.visita import Visita


class SinVisitaUnica(Exception):
    """No hay exactamente una visita ese dia: no se sabe a cual enlazar."""


async def visita_del_dia(session: AsyncSession, paciente_id: UUID, fecha: date) -> Visita:
    visitas = list(
        (await session.execute(select(Visita).where(Visita.paciente_id == paciente_id, Visita.fecha == fecha)))
        .scalars()
        .all()
    )
    if len(visitas) != 1:
        raise SinVisitaUnica(
            f"Se esperaba una visita el {fecha.isoformat()} y hay {len(visitas)}. "
            "Cree la visita de ese dia (o deje una sola) y repita."
        )
    return visitas[0]


async def sueltos_del_dia(session: AsyncSession, paciente_id: UUID, fecha: date) -> dict:
    """Entradas de bitacora y hallazgos de ese dia que no estan enlazados a ninguna visita."""
    bitacora = (
        await session.execute(
            select(BitacoraTratamiento).where(
                BitacoraTratamiento.paciente_id == paciente_id,
                BitacoraTratamiento.fecha == fecha,
                BitacoraTratamiento.visita_id.is_(None),
            )
        )
    ).scalars().all()
    hallazgos = (
        await session.execute(
            select(OdontogramaHallazgo).where(
                OdontogramaHallazgo.paciente_id == paciente_id,
                OdontogramaHallazgo.fecha == fecha,
                OdontogramaHallazgo.visita_id.is_(None),
            )
        )
    ).scalars().all()
    return {"bitacora": list(bitacora), "hallazgos": list(hallazgos)}


async def enlazar(session: AsyncSession, paciente_id: UUID, fecha: date) -> dict:
    """Enlaza lo suelto de ese dia a la visita de ese dia. Confirma al final; devuelve cuantas filas."""
    visita = await visita_del_dia(session, paciente_id, fecha)
    sueltos = await sueltos_del_dia(session, paciente_id, fecha)
    for modelo, filas in ((BitacoraTratamiento, sueltos["bitacora"]), (OdontogramaHallazgo, sueltos["hallazgos"])):
        if filas:
            await session.execute(update(modelo).where(modelo.id.in_([f.id for f in filas])).values(visita_id=visita.id))
    await session.commit()
    return {"visita": visita.id, "bitacora": len(sueltos["bitacora"]), "hallazgos": len(sueltos["hallazgos"])}
