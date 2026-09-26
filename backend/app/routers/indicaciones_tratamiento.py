from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_usuario, get_session, requerir_dra
from app.models.indicacion import IndicacionTratamiento
from app.models.profesional_tratante import ProfesionalTratante
from app.models.tratamiento import Tratamiento
from app.models.usuario import Usuario
from app.models.visita import Visita
from app.routers.constancias_asistencia import profesional_del_usuario
from app.routers.pacientes import obtener_paciente_o_404
from app.routers.plantillas_indicacion import obtener_plantilla_o_404
from app.schemas.indicacion import IndicacionTratamientoCreate, IndicacionTratamientoRead
from app.services.fechas import hoy_venezuela
from app.services.pdf import generar_pdf

# Documento clinico emitido por la Dra.: solo dra.
router = APIRouter(tags=["indicaciones-tratamiento"], dependencies=[Depends(requerir_dra)])


def _fecha(d) -> str:
    return d.strftime("%d/%m/%Y")


@router.post(
    "/pacientes/{paciente_id}/indicaciones-tratamiento",
    response_model=IndicacionTratamientoRead,
    status_code=201,
)
async def crear_indicacion_tratamiento(
    paciente_id: UUID,
    datos: IndicacionTratamientoCreate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    await obtener_paciente_o_404(paciente_id, session)

    visita = None
    if datos.visita_id is not None:
        visita = await session.get(Visita, datos.visita_id)
        if visita is None or visita.paciente_id != paciente_id:
            raise HTTPException(404, "Visita no encontrada para este paciente")
    if datos.tratamiento_id is not None:
        tratamiento = await session.get(Tratamiento, datos.tratamiento_id)
        if tratamiento is None or tratamiento.paciente_id != paciente_id:
            raise HTTPException(404, "Tratamiento no encontrado para este paciente")

    contenido_final = datos.contenido_final
    if datos.plantilla_id is not None:
        plantilla = await obtener_plantilla_o_404(datos.plantilla_id, session)
        # Copia al momento de emitir: cambios posteriores a la plantilla no
        # alteran esta indicacion.
        if contenido_final is None:
            contenido_final = plantilla.contenido

    hoy = hoy_venezuela()
    fecha = datos.fecha or hoy
    if fecha > hoy:
        raise HTTPException(422, f"La fecha ({_fecha(fecha)}) no puede ser posterior a hoy.")
    if visita is not None and fecha < visita.fecha:
        raise HTTPException(
            422,
            f"La fecha ({_fecha(fecha)}) no puede ser anterior a la visita ({_fecha(visita.fecha)}).",
        )

    profesional = await profesional_del_usuario(usuario, session)
    indicacion = IndicacionTratamiento(
        paciente_id=paciente_id,
        visita_id=datos.visita_id,
        tratamiento_id=datos.tratamiento_id,
        plantilla_id=datos.plantilla_id,
        contenido_final=contenido_final,
        fecha=fecha,
        emitida_por=profesional.id,
        creado_por=usuario.id,
    )
    session.add(indicacion)
    await session.commit()
    await session.refresh(indicacion)
    return indicacion


@router.get(
    "/pacientes/{paciente_id}/indicaciones-tratamiento",
    response_model=list[IndicacionTratamientoRead],
)
async def listar_indicaciones_tratamiento(
    paciente_id: UUID, session: AsyncSession = Depends(get_session)
):
    """Mas reciente primero (por fecha, y por carga dentro del mismo dia)."""
    await obtener_paciente_o_404(paciente_id, session)
    resultado = await session.execute(
        select(IndicacionTratamiento)
        .where(IndicacionTratamiento.paciente_id == paciente_id)
        .order_by(IndicacionTratamiento.fecha.desc(), IndicacionTratamiento.creado_en.desc())
    )
    return resultado.scalars().all()


@router.get("/pacientes/{paciente_id}/indicaciones-tratamiento/{indicacion_id}/pdf")
async def pdf_indicacion_tratamiento(
    paciente_id: UUID,
    indicacion_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    paciente = await obtener_paciente_o_404(paciente_id, session)
    indicacion = await session.get(IndicacionTratamiento, indicacion_id)
    if indicacion is None or indicacion.paciente_id != paciente_id:
        raise HTTPException(404, "Indicacion no encontrada")
    profesional = await session.get(ProfesionalTratante, indicacion.emitida_por)

    pdf = await generar_pdf(
        "indicacion_tratamiento.html",
        {
            "profesional": profesional,
            "paciente_nombre": paciente.nombre_completo,
            "fecha": indicacion.fecha,
            "contenido": indicacion.contenido_final,
        },
    )
    nombre = f"indicaciones-{paciente.numero_historia}-{indicacion.fecha.isoformat()}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre}"'},
    )
