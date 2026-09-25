from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_usuario, get_session, requerir_dra
from app.models.common import ahora
from app.models.periodontograma import PeriodontogramaDienteResumen, PeriodontogramaRegistro
from app.models.usuario import Usuario
from app.models.visita import Visita
from app.routers.pacientes import obtener_paciente_o_404
from app.schemas.periodontograma import (
    PeriodontogramaDienteResumenRead,
    PeriodontogramaDienteResumenUpdate,
    PeriodontogramaHistorialItem,
    PeriodontogramaRegistroRead,
    PeriodontogramaRegistroUpdate,
    PeriodontogramaVisitaCreate,
    PeriodontogramaVisitaRead,
    validar_furcacion,
)

router = APIRouter(tags=["periodontograma"], dependencies=[Depends(requerir_dra)])


async def _obtener_visita_o_404(visita_id: UUID, session: AsyncSession) -> Visita:
    visita = await session.get(Visita, visita_id)
    if visita is None:
        raise HTTPException(404, "Visita no encontrada")
    return visita


def _conflicto_carga_existente(visita: Visita) -> HTTPException:
    return HTTPException(
        409,
        detail={
            "mensaje": (
                f"La visita del {visita.fecha.strftime('%d/%m/%Y')} ya tiene un periodontograma "
                "cargado. Para corregir un valor, edite el sitio o el diente."
            ),
            "visita_id": str(visita.id),
        },
    )


@router.post(
    "/visitas/{visita_id}/periodontograma",
    response_model=PeriodontogramaVisitaRead,
    status_code=201,
)
async def cargar_periodontograma(
    visita_id: UUID,
    datos: PeriodontogramaVisitaCreate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    """
    Carga completa de un levantamiento periodontal (1.5): visita_id es
    obligatorio en ambas tablas (no nullable, a diferencia de
    odontograma_hallazgo) porque siempre ocurre dentro de una visita formal.
    Una sola carga por visita (409 si ya existe; las correcciones van por
    PATCH). nivel_insercion lo calcula el backend (24/09/2026).
    """
    visita = await _obtener_visita_o_404(visita_id, session)
    ya_cargado = await session.execute(
        select(PeriodontogramaRegistro.id)
        .where(PeriodontogramaRegistro.visita_id == visita_id)
        .limit(1)
    )
    if ya_cargado.first() is not None:
        raise _conflicto_carga_existente(visita)

    registros = [
        PeriodontogramaRegistro(
            paciente_id=visita.paciente_id,
            visita_id=visita_id,
            nivel_insercion=r.margen_gingival + r.profundidad_sondaje,
            creado_por=usuario.id,
            **r.model_dump(),
        )
        for r in datos.registros
    ]
    resumenes = [
        PeriodontogramaDienteResumen(
            paciente_id=visita.paciente_id,
            visita_id=visita_id,
            creado_por=usuario.id,
            **r.model_dump(),
        )
        for r in datos.resumenes
    ]
    session.add_all(registros)
    session.add_all(resumenes)
    try:
        await session.commit()
    except IntegrityError:
        # Dos cargas simultaneas de la misma visita: la UNIQUE de la base
        # frena la segunda aunque haya pasado el chequeo de arriba.
        await session.rollback()
        raise _conflicto_carga_existente(visita)
    for r in registros:
        await session.refresh(r)
    for r in resumenes:
        await session.refresh(r)
    return PeriodontogramaVisitaRead(registros=registros, resumenes=resumenes)


@router.get("/visitas/{visita_id}/periodontograma", response_model=PeriodontogramaVisitaRead)
async def obtener_periodontograma(visita_id: UUID, session: AsyncSession = Depends(get_session)):
    """Levantamiento completo de una visita, ordenado por diente y por sitio."""
    await _obtener_visita_o_404(visita_id, session)
    registros = (
        await session.execute(
            select(PeriodontogramaRegistro)
            .where(PeriodontogramaRegistro.visita_id == visita_id)
            .order_by(PeriodontogramaRegistro.numero_diente, PeriodontogramaRegistro.sitio)
        )
    ).scalars().all()
    resumenes = (
        await session.execute(
            select(PeriodontogramaDienteResumen)
            .where(PeriodontogramaDienteResumen.visita_id == visita_id)
            .order_by(PeriodontogramaDienteResumen.numero_diente)
        )
    ).scalars().all()
    return PeriodontogramaVisitaRead(registros=registros, resumenes=resumenes)


@router.get(
    "/pacientes/{paciente_id}/periodontograma/visitas",
    response_model=list[PeriodontogramaHistorialItem],
)
async def listar_periodontogramas_de_paciente(
    paciente_id: UUID, session: AsyncSession = Depends(get_session)
):
    """
    Visitas del paciente con periodontograma cargado, la mas reciente primero
    (24/09/2026): base de la vista de evolucion, sin probar visita por visita.
    """
    await obtener_paciente_o_404(paciente_id, session)
    resultado = await session.execute(
        select(
            Visita.id.label("visita_id"),
            Visita.fecha,
            func.count(func.distinct(PeriodontogramaRegistro.numero_diente)).label("dientes"),
            func.min(PeriodontogramaRegistro.creado_en).label("cargado_en"),
        )
        .join(PeriodontogramaRegistro, PeriodontogramaRegistro.visita_id == Visita.id)
        .where(Visita.paciente_id == paciente_id)
        .group_by(Visita.id, Visita.fecha)
        .order_by(Visita.fecha.desc(), func.min(PeriodontogramaRegistro.creado_en).desc())
    )
    return [PeriodontogramaHistorialItem(**fila._mapping) for fila in resultado.all()]


@router.patch(
    "/pacientes/{paciente_id}/periodontograma/registros/{registro_id}",
    response_model=PeriodontogramaRegistroRead,
)
async def corregir_registro(
    paciente_id: UUID,
    registro_id: UUID,
    datos: PeriodontogramaRegistroUpdate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    """Correccion puntual de un sitio (24/09/2026). nivel_insercion se recalcula."""
    registro = await session.get(PeriodontogramaRegistro, registro_id)
    # Un registro de otro paciente responde igual que uno inexistente.
    if registro is None or registro.paciente_id != paciente_id:
        raise HTTPException(404, "Registro periodontal no encontrado")
    for campo in datos.model_fields_set:
        setattr(registro, campo, getattr(datos, campo))
    registro.nivel_insercion = registro.margen_gingival + registro.profundidad_sondaje
    registro.actualizado_en = ahora()
    registro.actualizado_por = usuario.id
    await session.commit()
    await session.refresh(registro)
    return registro


@router.patch(
    "/pacientes/{paciente_id}/periodontograma/resumenes/{resumen_id}",
    response_model=PeriodontogramaDienteResumenRead,
)
async def corregir_resumen(
    paciente_id: UUID,
    resumen_id: UUID,
    datos: PeriodontogramaDienteResumenUpdate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    """Correccion puntual de movilidad/furcacion de un diente (24/09/2026)."""
    resumen = await session.get(PeriodontogramaDienteResumen, resumen_id)
    if resumen is None or resumen.paciente_id != paciente_id:
        raise HTTPException(404, "Resumen periodontal no encontrado")
    if "furcacion" in datos.model_fields_set:
        try:
            validar_furcacion(resumen.numero_diente, datos.furcacion)
        except ValueError as e:
            raise HTTPException(422, str(e))
    for campo in datos.model_fields_set:
        setattr(resumen, campo, getattr(datos, campo))
    resumen.actualizado_en = ahora()
    resumen.actualizado_por = usuario.id
    await session.commit()
    await session.refresh(resumen)
    return resumen
