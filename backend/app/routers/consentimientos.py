from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import ROLES_ACCESO_TOTAL, get_current_usuario, get_session
from app.enums import TipoConsentimiento
from app.models.consentimiento import Consentimiento
from app.models.tratamiento import Tratamiento
from app.models.usuario import Usuario
from app.routers.pacientes import obtener_paciente_o_404
from app.schemas.consentimiento import ConsentimientoCreate, ConsentimientoRead

# Permisos (04/10/2026): el consentimiento de TRATAMIENTO es de acceso total y
# va siempre ligado a un tratamiento del paciente; el de almacenamiento digital
# (papeleo de ingreso) tambien lo registra la asistente, sin tratamiento. La
# asistente solo ve estos ultimos.
router = APIRouter(tags=["consentimientos"], dependencies=[Depends(get_current_usuario)])


@router.post(
    "/pacientes/{paciente_id}/consentimientos",
    response_model=ConsentimientoRead,
    status_code=201,
)
async def crear_consentimiento(
    paciente_id: UUID,
    datos: ConsentimientoCreate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    if datos.tipo == TipoConsentimiento.tratamiento:
        if usuario.rol not in ROLES_ACCESO_TOTAL:
            raise HTTPException(403, "Solo puede registrar el consentimiento de tratamiento el acceso total.")
        if datos.tratamiento_id is None:
            raise HTTPException(422, "El consentimiento de tratamiento necesita el tratamiento.")
    elif datos.tratamiento_id is not None:
        raise HTTPException(422, "El consentimiento de almacenamiento digital no lleva tratamiento.")

    await obtener_paciente_o_404(paciente_id, session)
    if datos.tratamiento_id is not None:
        tratamiento = await session.get(Tratamiento, datos.tratamiento_id)
        if tratamiento is None or tratamiento.paciente_id != paciente_id:
            raise HTTPException(404, "Tratamiento no encontrado para este paciente")
    consentimiento = Consentimiento(
        paciente_id=paciente_id, **datos.model_dump(), creado_por=usuario.id
    )
    session.add(consentimiento)
    await session.commit()
    await session.refresh(consentimiento)
    return consentimiento


@router.get(
    "/pacientes/{paciente_id}/consentimientos", response_model=list[ConsentimientoRead]
)
async def listar_consentimientos_de_paciente(
    paciente_id: UUID,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    consulta = select(Consentimiento).where(Consentimiento.paciente_id == paciente_id)
    if usuario.rol not in ROLES_ACCESO_TOTAL:
        consulta = consulta.where(Consentimiento.tipo == TipoConsentimiento.almacenamiento_digital)
    resultado = await session.execute(consulta)
    return resultado.scalars().all()
