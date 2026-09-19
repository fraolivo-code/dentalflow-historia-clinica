from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_usuario, get_session
from app.models.profesional_tratante import ProfesionalTratante
from app.schemas.profesional_tratante import ProfesionalTratanteCreate, ProfesionalTratanteRead

# Catalogo de nombres de referencia, no dato clinico del paciente ->
# accesible a ambos roles, solo exige estar autenticado. Asuncion: no estaba
# en la lista explicita de endpoints exclusivos de dra.
router = APIRouter(
    tags=["profesionales-tratantes"], dependencies=[Depends(get_current_usuario)]
)


async def obtener_profesional_tratante_o_404(
    profesional_tratante_id: UUID, session: AsyncSession
) -> ProfesionalTratante:
    profesional = await session.get(ProfesionalTratante, profesional_tratante_id)
    if profesional is None:
        raise HTTPException(404, "Profesional tratante no encontrado")
    return profesional


@router.get("/profesionales-tratantes", response_model=list[ProfesionalTratanteRead])
async def listar_profesionales_tratantes(
    buscar: str | None = None, session: AsyncSession = Depends(get_session)
):
    """
    `buscar` habilita el autocompletar de texto libre (seccion 6: "sugiere
    coincidencias existentes pero no bloquea texto nuevo") sin forzar un
    desplegable cerrado.
    """
    consulta = select(ProfesionalTratante).order_by(ProfesionalTratante.nombre)
    if buscar:
        consulta = consulta.where(ProfesionalTratante.nombre.ilike(f"%{buscar}%"))
    resultado = await session.execute(consulta)
    return resultado.scalars().all()


@router.post("/profesionales-tratantes", response_model=ProfesionalTratanteRead, status_code=201)
async def crear_profesional_tratante(
    datos: ProfesionalTratanteCreate, session: AsyncSession = Depends(get_session)
):
    """
    Se crea al vuelo cuando la Dra. escribe un nombre nuevo al remitir un
    tratamiento — no hace falta una pantalla aparte (seccion 6).
    """
    profesional = ProfesionalTratante(**datos.model_dump())
    session.add(profesional)
    await session.commit()
    await session.refresh(profesional)
    return profesional
