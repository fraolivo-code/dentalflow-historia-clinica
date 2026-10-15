from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, requerir_dra
from app.enums import NUMEROS_DIENTE_VALIDOS
from app.routers.pacientes import obtener_paciente_o_404
from app.services import linea_de_tiempo

# Cronologia del paciente (flujo de visitas, fase 4, 15/10/2026). Solo lectura y solo dra:
# mezcla datos clinicos de varias tablas.
router = APIRouter(tags=["linea-de-tiempo"], dependencies=[Depends(requerir_dra)])


class EventoLineaTiempo(BaseModel):
    id: str
    tipo: str
    fecha: date
    titulo: str
    detalle: str | None
    dientes: list[int]


@router.get("/pacientes/{paciente_id}/linea-de-tiempo", response_model=list[EventoLineaTiempo])
async def obtener_linea_de_tiempo(
    paciente_id: UUID,
    diente: int | None = Query(default=None, description="Solo lo de este diente (numeracion FDI)"),
    session: AsyncSession = Depends(get_session),
):
    """De la mas reciente a la mas antigua. Con `diente`, solo lo que le pasó a ese diente."""
    if diente is not None and diente not in NUMEROS_DIENTE_VALIDOS:
        raise HTTPException(400, f"{diente} no es un numero de diente valido (FDI)")
    await obtener_paciente_o_404(paciente_id, session)
    return await linea_de_tiempo.construir(session, paciente_id, diente)
