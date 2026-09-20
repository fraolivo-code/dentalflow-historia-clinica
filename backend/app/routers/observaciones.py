from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_usuario, get_session, requerir_dra
from app.models.observacion import Observacion
from app.models.usuario import Usuario
from app.routers.pacientes import obtener_paciente_o_404
from app.schemas.observacion import ObservacionCreate, ObservacionRead

# Bloqueado a dra por completo por ahora, aunque el modelo ya distingue
# tipo_observacion (clinica/administrativa/otra): filtrar por tipo para dejar
# pasar solo las administrativas a asistente es un cambio propio, mas grande
# (validar en POST, filtrar en GET), que queda para otra tarea (confirmado).
router = APIRouter(tags=["observaciones"], dependencies=[Depends(requerir_dra)])


@router.post(
    "/pacientes/{paciente_id}/observaciones", response_model=ObservacionRead, status_code=201
)
async def crear_observacion(
    paciente_id: UUID,
    datos: ObservacionCreate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    """No depende de una visita activa (seccion 9: "su propio espacio")."""
    await obtener_paciente_o_404(paciente_id, session)
    observacion = Observacion(paciente_id=paciente_id, **datos.model_dump(), creado_por=usuario.id)
    session.add(observacion)
    await session.commit()
    await session.refresh(observacion)
    return observacion


@router.get("/pacientes/{paciente_id}/observaciones", response_model=list[ObservacionRead])
async def listar_observaciones_de_paciente(
    paciente_id: UUID, session: AsyncSession = Depends(get_session)
):
    """Mas reciente primero (seccion 9)."""
    resultado = await session.execute(
        select(Observacion)
        .where(Observacion.paciente_id == paciente_id)
        .order_by(Observacion.fecha.desc())
    )
    return resultado.scalars().all()


@router.get("/observaciones/{observacion_id}", response_model=ObservacionRead)
async def obtener_observacion(observacion_id: UUID, session: AsyncSession = Depends(get_session)):
    observacion = await session.get(Observacion, observacion_id)
    if observacion is None:
        raise HTTPException(404, "Observacion no encontrada")
    return observacion
