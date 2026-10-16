from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, requerir_dra
from app.enums import NUMEROS_DIENTE_VALIDOS
from app.routers.pacientes import obtener_paciente_o_404
from app.services import historia_compacta, linea_de_tiempo

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


class FilaResumen(BaseModel):
    diente: int
    hallazgo: str
    fecha: date
    estado: str  # pendiente | tratado | quitado
    fecha_estado: date | None
    con: str | None


class VisitaDelDia(BaseModel):
    tipo: str | None
    motivo: str | None


class HallazgoDelDia(BaseModel):
    diente: int
    etiqueta: str


class HechoDelDia(BaseModel):
    diente: int
    antes: list[str]
    despues: list[str]
    nota: str | None


class NotaDelDia(BaseModel):
    dientes: list[int]
    texto: str


class DiaDeLaHistoria(BaseModel):
    fecha: date
    visitas: list[VisitaDelDia]
    hallazgos: list[HallazgoDelDia]
    realizado: list[HechoDelDia]
    quitados: list[HallazgoDelDia]
    notas: list[NotaDelDia]
    otros: list[str]


class HistoriaCompacta(BaseModel):
    resumen: list[FilaResumen]
    dias: list[DiaDeLaHistoria]


@router.get("/pacientes/{paciente_id}/historia-compacta", response_model=HistoriaCompacta)
async def obtener_historia_compacta(paciente_id: UUID, session: AsyncSession = Depends(get_session)):
    """La historia por dia en una linea por hecho, y el resumen «se encontro / estado» (15/10/2026)."""
    await obtener_paciente_o_404(paciente_id, session)
    return await historia_compacta.construir(session, paciente_id)
