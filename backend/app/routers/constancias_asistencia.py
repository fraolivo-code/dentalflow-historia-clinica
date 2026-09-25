from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_usuario, get_session, requerir_dra
from app.models.constancia_asistencia import ConstanciaAsistencia
from app.models.profesional_tratante import ProfesionalTratante
from app.models.usuario import Usuario
from app.models.visita import Visita
from app.routers.pacientes import obtener_paciente_o_404
from app.schemas.constancia_asistencia import ConstanciaAsistenciaCreate, ConstanciaAsistenciaRead
from app.services.fechas import hoy_venezuela
from app.services.pdf import generar_pdf

# Documento emitido por la Dra.: solo dra (mismo criterio que el resto de los
# documentos clinicos, especificacion del 19/09/2026).
router = APIRouter(tags=["constancias-asistencia"], dependencies=[Depends(requerir_dra)])

# Lugar de emision que se imprime en la formula de cierre ("se expide en ...").
CIUDAD_EMISION = "Caracas"


def _fecha(d) -> str:
    return d.strftime("%d/%m/%Y")


async def _profesional_del_usuario(usuario: Usuario, session: AsyncSession) -> ProfesionalTratante:
    resultado = await session.execute(
        select(ProfesionalTratante).where(ProfesionalTratante.usuario_id == usuario.id)
    )
    profesional = resultado.scalar_one_or_none()
    if profesional is None:
        raise HTTPException(
            409,
            "Su usuario no esta vinculado a un profesional tratante: no se puede "
            "emitir la constancia a su nombre.",
        )
    return profesional


@router.post(
    "/pacientes/{paciente_id}/constancias-asistencia",
    response_model=ConstanciaAsistenciaRead,
    status_code=201,
)
async def crear_constancia_asistencia(
    paciente_id: UUID,
    datos: ConstanciaAsistenciaCreate,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    await obtener_paciente_o_404(paciente_id, session)
    visita = await session.get(Visita, datos.visita_id)
    if visita is None or visita.paciente_id != paciente_id:
        raise HTTPException(404, "Visita no encontrada para este paciente")

    hoy = hoy_venezuela()
    fecha_emision = datos.fecha_emision or hoy
    if fecha_emision < visita.fecha:
        raise HTTPException(
            422,
            f"La fecha de emision ({_fecha(fecha_emision)}) no puede ser anterior "
            f"a la visita ({_fecha(visita.fecha)}).",
        )
    if fecha_emision > hoy:
        raise HTTPException(
            422, f"La fecha de emision ({_fecha(fecha_emision)}) no puede ser posterior a hoy."
        )

    profesional = await _profesional_del_usuario(usuario, session)
    constancia = ConstanciaAsistencia(
        paciente_id=paciente_id,
        **datos.model_dump(exclude={"fecha_emision"}),
        fecha_emision=fecha_emision,
        emitida_por=profesional.id,
        creado_por=usuario.id,
    )
    session.add(constancia)
    await session.commit()
    await session.refresh(constancia)
    return constancia


@router.get("/pacientes/{paciente_id}/constancias-asistencia/{constancia_id}/pdf")
async def pdf_constancia_asistencia(
    paciente_id: UUID,
    constancia_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """
    A proposito solo usa nombre del paciente, fecha de la visita y lo cargado
    en la constancia: nada de motivo, diagnostico ni odontograma.
    """
    paciente = await obtener_paciente_o_404(paciente_id, session)
    constancia = await session.get(ConstanciaAsistencia, constancia_id)
    if constancia is None or constancia.paciente_id != paciente_id:
        raise HTTPException(404, "Constancia no encontrada")
    visita = await session.get(Visita, constancia.visita_id)
    profesional = await session.get(ProfesionalTratante, constancia.emitida_por)

    pdf = await generar_pdf(
        "constancia_asistencia.html",
        {
            "profesional": profesional,
            "paciente_nombre": paciente.nombre_completo,
            "fecha_visita": visita.fecha,
            "hora_inicio": constancia.hora_inicio,
            "hora_fin": constancia.hora_fin,
            "texto_adicional": constancia.texto_adicional,
            "fecha_emision": constancia.fecha_emision,
            "ciudad": CIUDAD_EMISION,
        },
    )
    nombre = f"constancia-asistencia-{paciente.numero_historia}-{constancia.fecha_emision.isoformat()}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre}"'},
    )
