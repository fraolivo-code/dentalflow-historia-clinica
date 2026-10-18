from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_usuario, get_session, requerir_dra
from app.models.common import ahora
from app.models.paciente import Paciente
from app.models.recordatorio import Recordatorio
from app.models.usuario import Usuario
from app.models.visita import Visita
from app.routers.pacientes import obtener_paciente_o_404
from app.schemas.recordatorio import RecordatorioCreate, RecordatorioRead, RecordatorioUpdate

# Recordatorios con fecha (proximo control, Rx pan para tal fecha...). Solo dra: son datos clinicos.
router = APIRouter(tags=["recordatorios"], dependencies=[Depends(requerir_dra)])


@router.post("/pacientes/{paciente_id}/recordatorios", response_model=RecordatorioRead, status_code=201)
async def crear_recordatorio(
    paciente_id: UUID,
    datos: RecordatorioCreate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    await obtener_paciente_o_404(paciente_id, session)
    if datos.visita_id is not None:
        visita = await session.get(Visita, datos.visita_id)
        if visita is None or visita.paciente_id != paciente_id:
            raise HTTPException(422, "La visita no existe o no es de este paciente.")
    recordatorio = Recordatorio(paciente_id=paciente_id, **datos.model_dump(), creado_por=usuario.id)
    session.add(recordatorio)
    await session.commit()
    await session.refresh(recordatorio)
    return recordatorio


@router.get("/pacientes/{paciente_id}/recordatorios", response_model=list[RecordatorioRead])
async def listar_recordatorios_de_paciente(paciente_id: UUID, session: AsyncSession = Depends(get_session)):
    """Pendientes primero (el mas cercano arriba); luego los hechos, el mas reciente primero."""
    await obtener_paciente_o_404(paciente_id, session)
    filas = (
        await session.execute(select(Recordatorio).where(Recordatorio.paciente_id == paciente_id))
    ).scalars().all()
    return sorted(filas, key=lambda r: (r.hecho, -r.fecha.toordinal() if r.hecho else r.fecha.toordinal()))


@router.get("/recordatorios/vencidos", response_model=list[RecordatorioRead])
async def listar_vencidos(hasta: date | None = None, session: AsyncSession = Depends(get_session)):
    """Pendientes con fecha igual o anterior a `hasta` (hoy por defecto), de pacientes activos."""
    limite = hasta or date.today()
    return (
        await session.execute(
            select(Recordatorio)
            .join(Paciente, Paciente.id == Recordatorio.paciente_id)
            .where(Recordatorio.hecho.is_(False), Recordatorio.fecha <= limite, Paciente.activo.is_(True))
            .order_by(Recordatorio.fecha)
        )
    ).scalars().all()


@router.patch("/recordatorios/{recordatorio_id}", response_model=RecordatorioRead)
async def actualizar_recordatorio(
    recordatorio_id: UUID,
    datos: RecordatorioUpdate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    recordatorio = await session.get(Recordatorio, recordatorio_id)
    if recordatorio is None:
        raise HTTPException(404, "Recordatorio no encontrado")
    cambios = datos.model_dump(exclude_unset=True)
    if not cambios:
        raise HTTPException(422, "No hay ningún campo para corregir")
    if any(v is None for v in cambios.values()):
        raise HTTPException(422, "Ningún campo puede quedar vacío")
    if "hecho" in cambios:
        recordatorio.hecho_fecha = date.today() if cambios["hecho"] else None
    for campo, valor in cambios.items():
        setattr(recordatorio, campo, valor)
    recordatorio.actualizado_en = ahora()
    recordatorio.actualizado_por = usuario.id
    await session.commit()
    await session.refresh(recordatorio)
    return recordatorio
