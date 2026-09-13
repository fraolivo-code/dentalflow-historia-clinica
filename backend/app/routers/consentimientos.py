from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.models.consentimiento import Consentimiento
from app.routers.pacientes import obtener_paciente_o_404
from app.schemas.consentimiento import ConsentimientoCreate, ConsentimientoRead

router = APIRouter(tags=["consentimientos"])


@router.post(
    "/pacientes/{paciente_id}/consentimientos",
    response_model=ConsentimientoRead,
    status_code=201,
)
async def crear_consentimiento(
    paciente_id: UUID, datos: ConsentimientoCreate, session: AsyncSession = Depends(get_session)
):
    await obtener_paciente_o_404(paciente_id, session)
    consentimiento = Consentimiento(paciente_id=paciente_id, **datos.model_dump())
    session.add(consentimiento)
    await session.commit()
    await session.refresh(consentimiento)
    return consentimiento


@router.get(
    "/pacientes/{paciente_id}/consentimientos", response_model=list[ConsentimientoRead]
)
async def listar_consentimientos_de_paciente(
    paciente_id: UUID, session: AsyncSession = Depends(get_session)
):
    resultado = await session.execute(
        select(Consentimiento).where(Consentimiento.paciente_id == paciente_id)
    )
    return resultado.scalars().all()
