from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, requerir_dra
from app.models.periodontograma import PeriodontogramaDienteResumen, PeriodontogramaRegistro
from app.models.visita import Visita
from app.schemas.periodontograma import PeriodontogramaVisitaCreate, PeriodontogramaVisitaRead

router = APIRouter(tags=["periodontograma"], dependencies=[Depends(requerir_dra)])


async def _obtener_visita_o_404(visita_id: UUID, session: AsyncSession) -> Visita:
    visita = await session.get(Visita, visita_id)
    if visita is None:
        raise HTTPException(404, "Visita no encontrada")
    return visita


@router.post(
    "/visitas/{visita_id}/periodontograma",
    response_model=PeriodontogramaVisitaRead,
    status_code=201,
)
async def cargar_periodontograma(
    visita_id: UUID,
    datos: PeriodontogramaVisitaCreate,
    session: AsyncSession = Depends(get_session),
):
    """
    Carga completa de un levantamiento periodontal (1.5): visita_id es
    obligatorio en ambas tablas (no nullable, a diferencia de
    odontograma_hallazgo) porque siempre ocurre dentro de una visita formal.
    """
    visita = await _obtener_visita_o_404(visita_id, session)

    registros = [
        PeriodontogramaRegistro(
            paciente_id=visita.paciente_id,
            visita_id=visita_id,
            creado_por=datos.creado_por,
            **r.model_dump(),
        )
        for r in datos.registros
    ]
    resumenes = [
        PeriodontogramaDienteResumen(
            paciente_id=visita.paciente_id,
            visita_id=visita_id,
            creado_por=datos.creado_por,
            **r.model_dump(),
        )
        for r in datos.resumenes
    ]
    session.add_all(registros)
    session.add_all(resumenes)
    await session.commit()
    for r in registros:
        await session.refresh(r)
    for r in resumenes:
        await session.refresh(r)
    return PeriodontogramaVisitaRead(registros=registros, resumenes=resumenes)


@router.get("/visitas/{visita_id}/periodontograma", response_model=PeriodontogramaVisitaRead)
async def obtener_periodontograma(visita_id: UUID, session: AsyncSession = Depends(get_session)):
    await _obtener_visita_o_404(visita_id, session)
    registros = (
        await session.execute(
            select(PeriodontogramaRegistro).where(PeriodontogramaRegistro.visita_id == visita_id)
        )
    ).scalars().all()
    resumenes = (
        await session.execute(
            select(PeriodontogramaDienteResumen).where(
                PeriodontogramaDienteResumen.visita_id == visita_id
            )
        )
    ).scalars().all()
    return PeriodontogramaVisitaRead(registros=registros, resumenes=resumenes)
