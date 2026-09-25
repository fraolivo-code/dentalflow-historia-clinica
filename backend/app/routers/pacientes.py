from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_usuario, get_session, requerir_dra
from app.models.common import ahora
from app.models.paciente import Paciente
from app.models.usuario import Usuario
from app.schemas.paciente import PacienteCreate, PacienteRead, PacienteUpdate
from app.services.correlativos import generar_numero_historia

# Paciente basico: accesible para dra y asistente por igual (ambas necesitan
# poder ver/crear pacientes) — solo exige estar autenticado, sin rol especifico.
router = APIRouter(
    prefix="/pacientes", tags=["pacientes"], dependencies=[Depends(get_current_usuario)]
)


@router.post("", response_model=PacienteRead, status_code=201)
async def crear_paciente(
    datos: PacienteCreate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    numero_historia = await generar_numero_historia(session)
    paciente = Paciente(
        **datos.model_dump(),
        numero_historia=numero_historia,
        creado_por=usuario.id,
    )
    session.add(paciente)
    await session.commit()
    await session.refresh(paciente)
    return paciente


@router.get("", response_model=list[PacienteRead])
async def listar_pacientes(q: str | None = None, session: AsyncSession = Depends(get_session)):
    """
    q busca por nombre_completo (parcial, sin distinguir mayusculas/acentos
    via la extension unaccent de Postgres — migracion 0005) o por
    numero_historia (parcial). Regla de negocio: seccion 4 de
    especificacion-tecnica-formularios-fase2.md.
    """
    query = select(Paciente)
    if q:
        patron = f"%{q}%"
        query = query.where(
            or_(
                func.unaccent(Paciente.nombre_completo).ilike(func.unaccent(patron)),
                Paciente.numero_historia.ilike(patron),
            )
        )
    resultado = await session.execute(query.order_by(Paciente.nombre_completo))
    return resultado.scalars().all()


@router.get("/{paciente_id}", response_model=PacienteRead)
async def obtener_paciente(paciente_id: UUID, session: AsyncSession = Depends(get_session)):
    paciente = await session.get(Paciente, paciente_id)
    if paciente is None:
        raise HTTPException(404, "Paciente no encontrado")
    return paciente


@router.patch(
    "/{paciente_id}", response_model=PacienteRead, dependencies=[Depends(requerir_dra)]
)
async def actualizar_paciente(
    paciente_id: UUID,
    datos: PacienteUpdate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    """
    Correccion parcial de los datos de alta (25/09/2026): solo dra, aunque
    crear y ver pacientes lo puede hacer tambien asistente.
    """
    paciente = await obtener_paciente_o_404(paciente_id, session)
    cambios = datos.model_dump(exclude_unset=True)
    for campo, valor in cambios.items():
        setattr(paciente, campo, valor)
    paciente.actualizado_en = ahora()
    paciente.actualizado_por = usuario.id

    await session.commit()
    await session.refresh(paciente)
    return paciente


async def obtener_paciente_o_404(paciente_id: UUID, session: AsyncSession) -> Paciente:
    """Usado por otros routers (visitas, odontograma, etc.) que cuelgan de /pacientes/{id}."""
    paciente = await session.get(Paciente, paciente_id)
    if paciente is None:
        raise HTTPException(404, "Paciente no encontrado")
    return paciente
