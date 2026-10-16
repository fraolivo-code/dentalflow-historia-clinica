from collections import defaultdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_usuario, get_session, requerir_dra
from app.enums import RolUsuario, TipoVisita
from app.models.common import ahora
from app.models.tratamiento import Tratamiento
from app.models.usuario import Usuario
from app.models.visita import Visita, VisitaTratamiento
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
        datos.tipo is not None
        or bool(datos.tratamiento_ids)
        or datos.higiene is not None
        or any(getattr(datos, campo) is not None for campo in _CAMPOS_CLINICOS_OPCIONALES)
        or any(getattr(datos, campo) for campo in _CAMPOS_CLINICOS_BOOL)
    )
    if trae_campo_clinico:
        raise HTTPException(
            422, "el rol asistente solo puede registrar fecha y motivo de consulta"
        )


async def _tratamientos_validos(
    session: AsyncSession, paciente_id: UUID, ids: list[UUID]
) -> list[UUID]:
    """Sin repetidos y todos del mismo paciente."""
    ids = list(dict.fromkeys(ids))
    if ids:
        encontrados = (
            await session.execute(
                select(Tratamiento.id).where(
                    Tratamiento.id.in_(ids), Tratamiento.paciente_id == paciente_id
                )
            )
        ).scalars().all()
        if len(encontrados) != len(ids):
            raise HTTPException(422, "Algún tratamiento no existe o no es de este paciente.")
    return ids


async def _leer(session: AsyncSession, visitas: list[Visita]) -> list[VisitaRead]:
    """VisitaRead con los tratamientos vinculados (una sola consulta)."""
    vinculos: dict[UUID, list[UUID]] = defaultdict(list)
    if visitas:
        filas = await session.execute(
            select(VisitaTratamiento.visita_id, VisitaTratamiento.tratamiento_id).where(
                VisitaTratamiento.visita_id.in_([v.id for v in visitas])
            )
        )
        for visita_id, tratamiento_id in filas:
            vinculos[visita_id].append(tratamiento_id)
    return [
        VisitaRead.model_validate(v).model_copy(update={"tratamiento_ids": vinculos[v.id]})
        for v in visitas
    ]


@router.post("/pacientes/{paciente_id}/visitas", response_model=VisitaRead, status_code=201)
async def crear_visita(
    paciente_id: UUID,
    datos: VisitaCreate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    _validar_visita_liviana_si_asistente(datos, usuario)
    await obtener_paciente_o_404(paciente_id, session)
    tratamiento_ids = await _tratamientos_validos(session, paciente_id, datos.tratamiento_ids)
    # responsable = el usuario autenticado que crea la visita (dra o
    # asistente) — si en el futuro alguien distinto atiende bajo la cuenta
    # de otro usuario, este campo deja de alcanzar y hay que revisarlo.
    visita = Visita(
        paciente_id=paciente_id,
        **datos.model_dump(exclude={"tratamiento_ids"}),
        responsable=usuario.id,
        creado_por=usuario.id,
    )
    session.add(visita)
    await session.flush()
    for tratamiento_id in tratamiento_ids:
        session.add(VisitaTratamiento(visita_id=visita.id, tratamiento_id=tratamiento_id))
    await session.commit()
    await session.refresh(visita)
    return (await _leer(session, [visita]))[0]


@router.get(
    "/pacientes/{paciente_id}/visitas",
    response_model=list[VisitaRead],
    dependencies=[Depends(requerir_dra)],
)
async def listar_visitas_de_paciente(
    paciente_id: UUID, session: AsyncSession = Depends(get_session)
):
    resultado = await session.execute(select(Visita).where(Visita.paciente_id == paciente_id))
    return await _leer(session, list(resultado.scalars().all()))


@router.get(
    "/visitas/{visita_id}", response_model=VisitaRead, dependencies=[Depends(requerir_dra)]
)
async def obtener_visita(visita_id: UUID, session: AsyncSession = Depends(get_session)):
    visita = await session.get(Visita, visita_id)
    if visita is None:
        raise HTTPException(404, "Visita no encontrada")
    return (await _leer(session, [visita]))[0]


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
    nuevos = cambios.pop("tratamiento_ids", None)
    actuales = (
        await session.execute(
            select(VisitaTratamiento.tratamiento_id).where(VisitaTratamiento.visita_id == visita.id)
        )
    ).scalars().all()
    if nuevos is not None:
        nuevos = await _tratamientos_validos(session, visita.paciente_id, nuevos)

    for campo, valor in cambios.items():
        setattr(visita, campo, valor)
    if nuevos is not None:
        await session.execute(delete(VisitaTratamiento).where(VisitaTratamiento.visita_id == visita.id))
        for tratamiento_id in nuevos:
            session.add(VisitaTratamiento(visita_id=visita.id, tratamiento_id=tratamiento_id))
    visita.actualizado_en = ahora()
    visita.actualizado_por = usuario.id

    await session.commit()
    await session.refresh(visita)
    return (await _leer(session, [visita]))[0]
