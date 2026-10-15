from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_usuario, get_session, requerir_dra
from app.enums import EstadoExamen, TipoExamen
from app.models.common import ahora
from app.models.examen import ExamenSolicitado
from app.models.tratamiento import Tratamiento
from app.models.usuario import Usuario
from app.models.visita import Visita
from app.routers.pacientes import obtener_paciente_o_404
from app.schemas.examen import ExamenCreate, ExamenRead, ExamenTraido, ExamenUpdate

# Examenes solicitados (flujo de visitas, fase 3, 15/10/2026). Solo dra: son datos clinicos.
router = APIRouter(tags=["examenes"], dependencies=[Depends(requerir_dra)])


@router.post("/pacientes/{paciente_id}/examenes", response_model=ExamenRead, status_code=201)
async def indicar_examen(
    paciente_id: UUID,
    datos: ExamenCreate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    """La Dra. indica un examen (radiografia, tomografia...). Queda «indicado» hasta que el paciente lo trae."""
    await obtener_paciente_o_404(paciente_id, session)
    if datos.tipo == TipoExamen.otro and datos.descripcion is None:
        raise HTTPException(422, "Indique cuál es el examen.")
    if datos.visita_id is not None:
        visita = await session.get(Visita, datos.visita_id)
        if visita is None or visita.paciente_id != paciente_id:
            raise HTTPException(422, "La visita no existe o no es de este paciente.")
    if datos.tratamiento_id is not None:
        tratamiento = await session.get(Tratamiento, datos.tratamiento_id)
        if tratamiento is None or tratamiento.paciente_id != paciente_id:
            raise HTTPException(422, "El tratamiento no existe o no es de este paciente.")
    examen = ExamenSolicitado(
        paciente_id=paciente_id,
        **datos.model_dump(),
        estado=EstadoExamen.indicado,
        creado_por=usuario.id,
    )
    session.add(examen)
    await session.commit()
    await session.refresh(examen)
    return examen


@router.get("/pacientes/{paciente_id}/examenes", response_model=list[ExamenRead])
async def listar_examenes(paciente_id: UUID, session: AsyncSession = Depends(get_session)):
    """Pendientes de traer primero; dentro de cada grupo, el mas reciente primero."""
    await obtener_paciente_o_404(paciente_id, session)
    filas = (
        await session.execute(select(ExamenSolicitado).where(ExamenSolicitado.paciente_id == paciente_id))
    ).scalars().all()
    return sorted(
        filas,
        key=lambda e: (e.estado != EstadoExamen.indicado, -e.fecha_indicacion.toordinal()),
    )


async def _obtener(session: AsyncSession, examen_id: UUID) -> ExamenSolicitado:
    examen = await session.get(ExamenSolicitado, examen_id)
    if examen is None:
        raise HTTPException(404, "Examen no encontrado")
    return examen


@router.patch("/examenes/{examen_id}/traido", response_model=ExamenRead)
async def registrar_que_lo_trajo(
    examen_id: UUID,
    datos: ExamenTraido,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    """El paciente trajo el examen: fecha y hallazgos si existen (no se guarda la imagen)."""
    examen = await _obtener(session, examen_id)
    if examen.estado == EstadoExamen.traido:
        raise HTTPException(409, "Este examen ya estaba registrado como traído.")
    if datos.fecha_traido < examen.fecha_indicacion:
        raise HTTPException(422, "La fecha no puede ser anterior a la de la indicación.")
    examen.estado = EstadoExamen.traido
    examen.fecha_traido = datos.fecha_traido
    examen.hallazgos = datos.hallazgos
    examen.actualizado_en = ahora()
    examen.actualizado_por = usuario.id
    await session.commit()
    await session.refresh(examen)
    return examen


@router.patch("/examenes/{examen_id}", response_model=ExamenRead)
async def corregir_examen(
    examen_id: UUID,
    datos: ExamenUpdate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    """Corrige el texto (descripcion o hallazgos) de un examen ya indicado o traido."""
    examen = await _obtener(session, examen_id)
    cambios = datos.model_dump(exclude_unset=True)
    if not cambios:
        raise HTTPException(422, "No hay ningún campo para corregir")
    if examen.tipo == TipoExamen.otro and "descripcion" in cambios and cambios["descripcion"] is None:
        raise HTTPException(422, "Indique cuál es el examen.")
    if "hallazgos" in cambios and examen.estado != EstadoExamen.traido:
        raise HTTPException(409, "Los hallazgos se registran cuando el paciente trae el examen.")
    for campo, valor in cambios.items():
        setattr(examen, campo, valor)
    examen.actualizado_en = ahora()
    examen.actualizado_por = usuario.id
    await session.commit()
    await session.refresh(examen)
    return examen
