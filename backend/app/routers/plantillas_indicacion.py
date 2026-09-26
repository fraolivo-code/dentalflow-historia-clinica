from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_usuario, get_session, requerir_dra
from app.models.common import ahora
from app.models.indicacion import PlantillaIndicacion
from app.models.usuario import Usuario
from app.schemas.indicacion import (
    PlantillaIndicacionCreate,
    PlantillaIndicacionRead,
    PlantillaIndicacionUpdate,
)

# Catalogo de la Dra.: solo dra. Sin DELETE a proposito: una plantilla
# obsoleta se deja de usar, y las indicaciones ya entregadas guardan su copia.
router = APIRouter(
    prefix="/plantillas-indicacion",
    tags=["plantillas-indicacion"],
    dependencies=[Depends(requerir_dra)],
)


async def obtener_plantilla_o_404(plantilla_id: UUID, session: AsyncSession) -> PlantillaIndicacion:
    plantilla = await session.get(PlantillaIndicacion, plantilla_id)
    if plantilla is None:
        raise HTTPException(404, "Plantilla de indicacion no encontrada")
    return plantilla


async def _guardar(session: AsyncSession, plantilla: PlantillaIndicacion) -> PlantillaIndicacion:
    nombre = plantilla.nombre  # tras el rollback el objeto queda expirado
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, f'Ya existe una plantilla llamada "{nombre}"')
    await session.refresh(plantilla)
    return plantilla


@router.get("", response_model=list[PlantillaIndicacionRead])
async def listar_plantillas_indicacion(
    tipo_tratamiento: str | None = None, session: AsyncSession = Depends(get_session)
):
    consulta = select(PlantillaIndicacion).order_by(PlantillaIndicacion.nombre)
    if tipo_tratamiento:
        consulta = consulta.where(PlantillaIndicacion.tipo_tratamiento.ilike(f"%{tipo_tratamiento}%"))
    resultado = await session.execute(consulta)
    return resultado.scalars().all()


@router.get("/{plantilla_id}", response_model=PlantillaIndicacionRead)
async def obtener_plantilla_indicacion(plantilla_id: UUID, session: AsyncSession = Depends(get_session)):
    return await obtener_plantilla_o_404(plantilla_id, session)


@router.post("", response_model=PlantillaIndicacionRead, status_code=201)
async def crear_plantilla_indicacion(
    datos: PlantillaIndicacionCreate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    plantilla = PlantillaIndicacion(**datos.model_dump(), creado_por=usuario.id)
    session.add(plantilla)
    return await _guardar(session, plantilla)


@router.patch("/{plantilla_id}", response_model=PlantillaIndicacionRead)
async def actualizar_plantilla_indicacion(
    plantilla_id: UUID,
    datos: PlantillaIndicacionUpdate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    """No toca las indicaciones ya entregadas: cada una guarda su contenido_final."""
    plantilla = await obtener_plantilla_o_404(plantilla_id, session)
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(plantilla, campo, valor)
    plantilla.actualizado_en = ahora()
    plantilla.actualizado_por = usuario.id
    return await _guardar(session, plantilla)
