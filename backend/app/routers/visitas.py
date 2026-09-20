from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_usuario, get_session, requerir_dra
from app.models.usuario import Usuario
from app.models.visita import Visita
from app.routers.pacientes import obtener_paciente_o_404
from app.schemas.visita import VisitaCreate, VisitaRead

# Bloqueado a dra por completo por ahora: el unico endpoint de creacion exige
# el examen clinico completo (higiene, examenes, hallazgos) en un solo POST,
# no existe todavia una version liviana de "iniciar visita" con solo
# motivo_consulta para asistente. Esa version liviana se define junto con el
# resto del flujo clinico de asistente, en una tarea aparte (confirmado).
router = APIRouter(tags=["visitas"], dependencies=[Depends(requerir_dra)])


@router.post("/pacientes/{paciente_id}/visitas", response_model=VisitaRead, status_code=201)
async def crear_visita(
    paciente_id: UUID,
    datos: VisitaCreate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    await obtener_paciente_o_404(paciente_id, session)
    # responsable = el mismo dra autenticado hoy (unico rol con acceso a este
    # endpoint) — si en el futuro un dra distinto atiende bajo la cuenta de
    # otro usuario, este campo deja de alcanzar y hay que revisarlo.
    visita = Visita(
        paciente_id=paciente_id,
        **datos.model_dump(),
        responsable=usuario.id,
        creado_por=usuario.id,
    )
    session.add(visita)
    await session.commit()
    await session.refresh(visita)
    return visita


@router.get("/pacientes/{paciente_id}/visitas", response_model=list[VisitaRead])
async def listar_visitas_de_paciente(
    paciente_id: UUID, session: AsyncSession = Depends(get_session)
):
    resultado = await session.execute(select(Visita).where(Visita.paciente_id == paciente_id))
    return resultado.scalars().all()


@router.get("/visitas/{visita_id}", response_model=VisitaRead)
async def obtener_visita(visita_id: UUID, session: AsyncSession = Depends(get_session)):
    visita = await session.get(Visita, visita_id)
    if visita is None:
        raise HTTPException(404, "Visita no encontrada")
    return visita
