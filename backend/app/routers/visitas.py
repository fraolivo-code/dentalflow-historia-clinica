from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_usuario, get_session, requerir_dra
from app.enums import RolUsuario
from app.models.common import ahora
from app.models.usuario import Usuario
from app.models.visita import Visita
from app.routers.pacientes import obtener_paciente_o_404
from app.schemas.visita import VisitaCreate, VisitaRead, VisitaUpdate

# POST ya no esta bloqueado a dra por completo (20/09/2026): asistente puede
# crear una visita liviana (fecha+motivo_consulta) via el mismo POST, dra
# la completa clinicamente despues con PATCH /visitas/{id}. GET sigue
# restringido a dra por endpoint (sin cambios de alcance pedidos ahi). El
# PATCH es exclusivo dra tambien, por endpoint.
router = APIRouter(tags=["visitas"])

# Todo lo que no sea fecha/motivo_consulta se considera "campo clinico":
# asistente no puede mandar ninguno con valor no-default.
_CAMPOS_CLINICOS_OPCIONALES = (
    "examen_extraoral_atm",
    "examen_extraoral_ganglios",
    "examen_extraoral_otros",
    "tejidos_blandos",
    "examen_otras",
    "hallazgos",
)
_CAMPOS_CLINICOS_BOOL = (
    "examen_rx_periapical",
    "examen_ex_pc",
    "examen_rx_panoramica",
    "examen_rutina_quirurgica",
    "examen_tomografia",
)


def _validar_visita_liviana_si_asistente(datos: VisitaCreate, usuario: Usuario) -> None:
    if usuario.rol != RolUsuario.asistente:
        return
    trae_campo_clinico = (
        datos.higiene is not None
        or any(getattr(datos, campo) is not None for campo in _CAMPOS_CLINICOS_OPCIONALES)
        or any(getattr(datos, campo) for campo in _CAMPOS_CLINICOS_BOOL)
    )
    if trae_campo_clinico:
        raise HTTPException(
            422, "el rol asistente solo puede registrar fecha y motivo de consulta"
        )


@router.post("/pacientes/{paciente_id}/visitas", response_model=VisitaRead, status_code=201)
async def crear_visita(
    paciente_id: UUID,
    datos: VisitaCreate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    _validar_visita_liviana_si_asistente(datos, usuario)
    await obtener_paciente_o_404(paciente_id, session)
    # responsable = el usuario autenticado que crea la visita (dra o
    # asistente) — si en el futuro alguien distinto atiende bajo la cuenta
    # de otro usuario, este campo deja de alcanzar y hay que revisarlo.
    visita = Visita(
        paciente_id=paciente_id,
        **datos.model_dump(),
        responsable=usuario.id,
        creado_por=usuario.id,
    )
    session.add(visita)
    await session.commit()
    await session.refresh(visita)
    return visita


@router.get(
    "/pacientes/{paciente_id}/visitas",
    response_model=list[VisitaRead],
    dependencies=[Depends(requerir_dra)],
)
async def listar_visitas_de_paciente(
    paciente_id: UUID, session: AsyncSession = Depends(get_session)
):
    resultado = await session.execute(select(Visita).where(Visita.paciente_id == paciente_id))
    return resultado.scalars().all()


@router.get(
    "/visitas/{visita_id}", response_model=VisitaRead, dependencies=[Depends(requerir_dra)]
)
async def obtener_visita(visita_id: UUID, session: AsyncSession = Depends(get_session)):
    visita = await session.get(Visita, visita_id)
    if visita is None:
        raise HTTPException(404, "Visita no encontrada")
    return visita


@router.patch(
    "/visitas/{visita_id}", response_model=VisitaRead, dependencies=[Depends(requerir_dra)]
)
async def actualizar_visita(
    visita_id: UUID,
    datos: VisitaUpdate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    """Completa la fase clinica de una visita liviana creada por asistente."""
    visita = await session.get(Visita, visita_id)
    if visita is None:
        raise HTTPException(404, "Visita no encontrada")

    cambios = datos.model_dump(exclude_unset=True)
    for campo, valor in cambios.items():
        setattr(visita, campo, valor)
    visita.actualizado_en = ahora()
    visita.actualizado_por = usuario.id

    await session.commit()
    await session.refresh(visita)
    return visita
