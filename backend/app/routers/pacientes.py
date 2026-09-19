from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_usuario, get_session
from app.models.paciente import Paciente
from app.schemas.paciente import PacienteCreate, PacienteRead

# Paciente basico: accesible para dra y asistente por igual (ambas necesitan
# poder ver/crear pacientes) — solo exige estar autenticado, sin rol especifico.
router = APIRouter(
    prefix="/pacientes", tags=["pacientes"], dependencies=[Depends(get_current_usuario)]
)


@router.post("", response_model=PacienteRead, status_code=201)
async def crear_paciente(datos: PacienteCreate, session: AsyncSession = Depends(get_session)):
    paciente = Paciente(**datos.model_dump())
    session.add(paciente)
    await session.commit()
    await session.refresh(paciente)
    return paciente


@router.get("", response_model=list[PacienteRead])
async def listar_pacientes(session: AsyncSession = Depends(get_session)):
    resultado = await session.execute(select(Paciente))
    return resultado.scalars().all()


@router.get("/{paciente_id}", response_model=PacienteRead)
async def obtener_paciente(paciente_id: UUID, session: AsyncSession = Depends(get_session)):
    paciente = await session.get(Paciente, paciente_id)
    if paciente is None:
        raise HTTPException(404, "Paciente no encontrado")
    return paciente


async def obtener_paciente_o_404(paciente_id: UUID, session: AsyncSession) -> Paciente:
    """Usado por otros routers (visitas, odontograma, etc.) que cuelgan de /pacientes/{id}."""
    paciente = await session.get(Paciente, paciente_id)
    if paciente is None:
        raise HTTPException(404, "Paciente no encontrado")
    return paciente
