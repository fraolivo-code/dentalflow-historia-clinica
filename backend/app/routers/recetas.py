from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_usuario, get_session, requerir_dra
from app.models.profesional_tratante import ProfesionalTratante
from app.models.receta import Medicamento, Receta, RecetaMedicamento
from app.models.tratamiento import Tratamiento
from app.models.usuario import Usuario
from app.models.visita import Visita
from app.routers.constancias_asistencia import profesional_del_usuario
from app.routers.medicamentos import medicamento_por_nombre, obtener_medicamento_o_404
from app.routers.pacientes import obtener_paciente_o_404
from app.schemas.receta import RecetaCreate, RecetaRead
from app.services.fechas import hoy_venezuela
from app.services.pdf import generar_pdf

# Documento clinico emitido por la Dra.: solo dra.
router = APIRouter(tags=["recetas"], dependencies=[Depends(requerir_dra)])


def _fecha(d) -> str:
    return d.strftime("%d/%m/%Y")


async def _con_medicamentos(session: AsyncSession, recetas: list[Receta]) -> list[Receta]:
    """Carga las lineas (con su medicamento) de todas las recetas en una consulta."""
    if not recetas:
        return recetas
    resultado = await session.execute(
        select(RecetaMedicamento, Medicamento)
        .join(Medicamento, Medicamento.id == RecetaMedicamento.medicamento_id)
        .where(RecetaMedicamento.receta_id.in_([r.id for r in recetas]))
        .order_by(RecetaMedicamento.orden)
    )
    lineas: dict[UUID, list[RecetaMedicamento]] = {r.id: [] for r in recetas}
    for linea, medicamento in resultado.all():
        linea.medicamento = medicamento  # atributo dinamico, no mapeado
        lineas[linea.receta_id].append(linea)
    for receta in recetas:
        receta.medicamentos = lineas[receta.id]  # idem
    return recetas


@router.post("/pacientes/{paciente_id}/recetas", response_model=RecetaRead, status_code=201)
async def crear_receta(
    paciente_id: UUID,
    datos: RecetaCreate,
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
    receta = Receta(
        paciente_id=paciente_id,
        visita_id=datos.visita_id,
        tratamiento_id=datos.tratamiento_id,
        fecha=fecha,
        notas_generales=datos.notas_generales,
        emitida_por=profesional.id,
        creado_por=usuario.id,
    )
    session.add(receta)
    await session.flush()

    # Medicamentos nuevos (texto libre) y receta entran en la misma
    # transaccion: si algo falla, no queda un medicamento agregado a medias.
    for orden, linea in enumerate(datos.medicamentos, start=1):
        if linea.medicamento_id is not None:
            medicamento = await obtener_medicamento_o_404(linea.medicamento_id, session)
        else:
            medicamento = await medicamento_por_nombre(linea.medicamento_nombre, session)
        session.add(
            RecetaMedicamento(
                receta_id=receta.id,
                orden=orden,
                medicamento_id=medicamento.id,
                medicamento_nombre_impreso=medicamento.nombre,
                presentacion_impresa=medicamento.presentacion_default,
                **linea.model_dump(exclude={"medicamento_id", "medicamento_nombre"}),
            )
        )
    await session.commit()
    await session.refresh(receta)
    return (await _con_medicamentos(session, [receta]))[0]


@router.get("/pacientes/{paciente_id}/recetas", response_model=list[RecetaRead])
async def listar_recetas(paciente_id: UUID, session: AsyncSession = Depends(get_session)):
    """Mas reciente primero (por fecha, y por carga dentro del mismo dia)."""
    await obtener_paciente_o_404(paciente_id, session)
    resultado = await session.execute(
        select(Receta)
        .where(Receta.paciente_id == paciente_id)
        .order_by(Receta.fecha.desc(), Receta.creado_en.desc())
    )
    return await _con_medicamentos(session, list(resultado.scalars().all()))


async def _pdf_de_receta(
    paciente_id: UUID, receta_id: UUID, session: AsyncSession, plantilla: str, prefijo: str
) -> Response:
    """
    Una misma receta genera 2 documentos (practica real de la Dra.): el
    recipe para la farmacia y las indicaciones de medicamentos para el
    paciente. Mismos datos, distinta plantilla.
    """
    paciente = await obtener_paciente_o_404(paciente_id, session)
    receta = await session.get(Receta, receta_id)
    if receta is None or receta.paciente_id != paciente_id:
        raise HTTPException(404, "Récipe no encontrado")
    await _con_medicamentos(session, [receta])
    profesional = await session.get(ProfesionalTratante, receta.emitida_por)

    pdf = await generar_pdf(
        plantilla,
        {
            "profesional": profesional,
            "paciente_nombre": paciente.nombre_completo,
            "paciente_cedula": paciente.cedula,
            "fecha": receta.fecha,
            "medicamentos": receta.medicamentos,
            "notas_generales": receta.notas_generales,
        },
    )
    # Sin tildes: el nombre de archivo va en un header HTTP (solo ASCII).
    nombre = f"{prefijo}-{paciente.numero_historia}-{receta.fecha.isoformat()}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre}"'},
    )


@router.get("/pacientes/{paciente_id}/recetas/{receta_id}/pdf")
async def pdf_receta(
    paciente_id: UUID,
    receta_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Recipe (para la farmacia): solo nombre y presentacion de cada medicamento."""
    return await _pdf_de_receta(paciente_id, receta_id, session, "receta.html", "recipe")


@router.get("/pacientes/{paciente_id}/recetas/{receta_id}/pdf-indicaciones")
async def pdf_indicaciones_medicamentos(
    paciente_id: UUID,
    receta_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Indicaciones de medicamentos (para el paciente): posologia completa y notas generales."""
    return await _pdf_de_receta(
        paciente_id, receta_id, session, "indicaciones_medicamentos.html", "indicaciones-medicamentos"
    )
