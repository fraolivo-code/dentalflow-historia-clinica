from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.models.antecedente import Antecedente, PacienteAntecedente
from app.models.common import ahora
from app.routers.pacientes import obtener_paciente_o_404
from app.schemas.antecedente import (
    AntecedenteCreate,
    AntecedenteRead,
    PacienteAntecedenteRead,
    PacienteAntecedenteUpsert,
)

router = APIRouter(tags=["antecedentes"])


@router.get("/antecedentes", response_model=list[AntecedenteRead])
async def listar_catalogo_antecedentes(session: AsyncSession = Depends(get_session)):
    resultado = await session.execute(select(Antecedente).order_by(Antecedente.nombre))
    return resultado.scalars().all()


@router.post("/antecedentes", response_model=AntecedenteRead, status_code=201)
async def crear_antecedente(
    datos: AntecedenteCreate, session: AsyncSession = Depends(get_session)
):
    """Amplia el catalogo (seccion 2: "apertura a agregar categorias segun su experiencia clinica")."""
    existente = await session.execute(
        select(Antecedente).where(Antecedente.nombre == datos.nombre)
    )
    if existente.scalars().first() is not None:
        raise HTTPException(400, f"Ya existe un antecedente llamado '{datos.nombre}'")
    antecedente = Antecedente(**datos.model_dump())
    session.add(antecedente)
    await session.commit()
    await session.refresh(antecedente)
    return antecedente


@router.get(
    "/pacientes/{paciente_id}/antecedentes", response_model=list[PacienteAntecedenteRead]
)
async def listar_antecedentes_de_paciente(
    paciente_id: UUID, session: AsyncSession = Depends(get_session)
):
    await obtener_paciente_o_404(paciente_id, session)
    resultado = await session.execute(
        select(PacienteAntecedente).where(PacienteAntecedente.paciente_id == paciente_id)
    )
    return resultado.scalars().all()


@router.put(
    "/pacientes/{paciente_id}/antecedentes",
    response_model=PacienteAntecedenteRead,
)
async def registrar_antecedente_de_paciente(
    paciente_id: UUID,
    datos: PacienteAntecedenteUpsert,
    session: AsyncSession = Depends(get_session),
):
    """
    Crea o actualiza el estado de una categoria de antecedente para el
    paciente (upsert por paciente_id+antecedente_id) — asi se modela la
    revision periodica de la seccion 5 ("sigue igual" / "actualizar"), sin
    acumular filas duplicadas por la misma categoria.
    """
    await obtener_paciente_o_404(paciente_id, session)
    antecedente = await session.get(Antecedente, datos.antecedente_id)
    if antecedente is None:
        raise HTTPException(404, "Antecedente no encontrado en el catalogo")

    if datos.presente and antecedente.requiere_detalle and not (datos.detalle or "").strip():
        raise HTTPException(
            400, f"'{antecedente.nombre}' requiere un detalle cuando esta presente"
        )

    existente = await session.execute(
        select(PacienteAntecedente).where(
            PacienteAntecedente.paciente_id == paciente_id,
            PacienteAntecedente.antecedente_id == datos.antecedente_id,
        )
    )
    fila = existente.scalars().first()

    if fila is None:
        fila = PacienteAntecedente(
            paciente_id=paciente_id,
            antecedente_id=datos.antecedente_id,
            presente=datos.presente,
            detalle=datos.detalle,
            creado_por=datos.creado_por,
        )
        session.add(fila)
    else:
        fila.presente = datos.presente
        fila.detalle = datos.detalle
        fila.actualizado_en = ahora()
        fila.actualizado_por = datos.creado_por

    await session.commit()
    await session.refresh(fila)
    return fila
