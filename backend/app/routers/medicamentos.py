from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, requerir_dra
from app.models.receta import Medicamento
from app.schemas.receta import MedicamentoCreate, MedicamentoRead, MedicamentoUpdate

# Catalogo de la Dra.: solo dra. Sin DELETE a proposito: un medicamento en
# desuso se deja de usar, y las recetas ya emitidas lo siguen referenciando.
router = APIRouter(
    prefix="/medicamentos",
    tags=["medicamentos"],
    dependencies=[Depends(requerir_dra)],
)


async def obtener_medicamento_o_404(medicamento_id: UUID, session: AsyncSession) -> Medicamento:
    medicamento = await session.get(Medicamento, medicamento_id)
    if medicamento is None:
        raise HTTPException(404, "Medicamento no encontrado en el catalogo")
    return medicamento


async def medicamento_por_nombre(nombre: str, session: AsyncSession) -> Medicamento:
    """
    Texto libre al transcribir una receta: reusa el medicamento si ya existe
    (sin distinguir mayusculas) y si no, lo agrega al catalogo al vuelo — mismo
    principio que profesional_tratante (seccion 6: sugiere, no bloquea texto
    nuevo). No hace commit: queda en la misma transaccion que la receta.
    """
    resultado = await session.execute(
        select(Medicamento).where(func.lower(Medicamento.nombre) == nombre.lower())
    )
    medicamento = resultado.scalar_one_or_none()
    if medicamento is None:
        medicamento = Medicamento(nombre=nombre, es_favorito=False)
        session.add(medicamento)
        await session.flush()
    return medicamento


async def _guardar(session: AsyncSession, medicamento: Medicamento) -> Medicamento:
    nombre = medicamento.nombre  # tras el rollback el objeto queda expirado
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, f'Ya existe un medicamento llamado "{nombre}"')
    await session.refresh(medicamento)
    return medicamento


@router.get("", response_model=list[MedicamentoRead])
async def listar_medicamentos(buscar: str | None = None, session: AsyncSession = Depends(get_session)):
    """Favoritos primero, luego alfabetico. `buscar` es para el autocompletar."""
    consulta = select(Medicamento).order_by(
        Medicamento.es_favorito.desc(), func.lower(Medicamento.nombre)
    )
    if buscar:
        consulta = consulta.where(Medicamento.nombre.ilike(f"%{buscar}%"))
    resultado = await session.execute(consulta)
    return resultado.scalars().all()


@router.get("/{medicamento_id}", response_model=MedicamentoRead)
async def obtener_medicamento(medicamento_id: UUID, session: AsyncSession = Depends(get_session)):
    return await obtener_medicamento_o_404(medicamento_id, session)


@router.post("", response_model=MedicamentoRead, status_code=201)
async def crear_medicamento(datos: MedicamentoCreate, session: AsyncSession = Depends(get_session)):
    medicamento = Medicamento(**datos.model_dump())
    session.add(medicamento)
    return await _guardar(session, medicamento)


@router.patch("/{medicamento_id}", response_model=MedicamentoRead)
async def actualizar_medicamento(
    medicamento_id: UUID,
    datos: MedicamentoUpdate,
    session: AsyncSession = Depends(get_session),
):
    medicamento = await obtener_medicamento_o_404(medicamento_id, session)
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(medicamento, campo, valor)
    return await _guardar(session, medicamento)
