from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_usuario, get_session
from app.enums import RolUsuario, TipoObservacion
from app.models.observacion import Observacion
from app.models.usuario import Usuario
from app.routers.pacientes import obtener_paciente_o_404
from app.schemas.observacion import ObservacionCreate, ObservacionRead

# Ya no bloqueado a dra por completo (20/09/2026): el router solo exige
# autenticacion (cualquier rol), y cada endpoint filtra/valida por
# tipo_observacion segun el rol — asistente solo ve/crea "administrativa",
# dra sigue sin restriccion (ve/crea las 3: clinica/administrativa/otra).
router = APIRouter(tags=["observaciones"])


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
    if usuario.rol == RolUsuario.asistente and datos.tipo != TipoObservacion.administrativa:
        raise HTTPException(
            422, "el rol asistente solo puede crear observaciones administrativas"
        )
    await obtener_paciente_o_404(paciente_id, session)
    observacion = Observacion(paciente_id=paciente_id, **datos.model_dump(), creado_por=usuario.id)
    session.add(observacion)
    await session.commit()
    await session.refresh(observacion)
    return observacion


@router.get("/pacientes/{paciente_id}/observaciones", response_model=list[ObservacionRead])
async def listar_observaciones_de_paciente(
    paciente_id: UUID,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    """Mas reciente primero (seccion 9). Asistente solo ve administrativas."""
    consulta = select(Observacion).where(Observacion.paciente_id == paciente_id)
    if usuario.rol == RolUsuario.asistente:
        consulta = consulta.where(Observacion.tipo == TipoObservacion.administrativa)
    resultado = await session.execute(consulta.order_by(Observacion.fecha.desc()))
    return resultado.scalars().all()


@router.get("/observaciones/{observacion_id}", response_model=ObservacionRead)
async def obtener_observacion(
    observacion_id: UUID,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    observacion = await session.get(Observacion, observacion_id)
    # 404 (no 403) si es clinica/otra y pregunta asistente: no confirma que
    # la observacion existe, solo que "no esta disponible" (mismo mensaje).
    if observacion is None or (
        usuario.rol == RolUsuario.asistente
        and observacion.tipo != TipoObservacion.administrativa
    ):
        raise HTTPException(404, "Observacion no encontrada")
    return observacion
