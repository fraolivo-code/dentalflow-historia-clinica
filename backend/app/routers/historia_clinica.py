# app/routers/historia_clinica.py — Documento 5 de 5 de la Etapa 5 (PDF):
# historia clinica completa del paciente (derecho de acceso / Habeas Data).
# Junta en un solo PDF todo lo registrado en las secciones de texto.

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_usuario, get_session, requerir_dra
from app.enums import TipoObservacion
from app.models.antecedente import Antecedente, PacienteAntecedente
from app.models.bitacora_tratamiento import BitacoraTratamiento
from app.models.consentimiento import Consentimiento
from app.models.observacion import Observacion
from app.models.profesional_tratante import ProfesionalTratante
from app.models.tratamiento import Tratamiento, TratamientoDiente
from app.models.usuario import Usuario
from app.models.visita import Visita
from app.routers.constancias_asistencia import profesional_del_usuario
from app.routers.pacientes import obtener_paciente_o_404
from app.services import etiquetas
from app.services.fechas import hoy_venezuela
from app.services.pdf import generar_pdf

# Documento clinico completo: solo dra.
router = APIRouter(tags=["historia-clinica"], dependencies=[Depends(requerir_dra)])

# Las administrativas (pagos, incidencias de conducta) no son parte de la
# historia clinica: quedan afuera por privacidad. Entran clinica y otra
# (decision del 26/09/2026).
TIPOS_OBSERVACION_EN_HISTORIA = (TipoObservacion.clinica, TipoObservacion.otra)


def _edad(nacimiento: date, hoy: date) -> int:
    return hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))


def _nombre_tratamiento(t: Tratamiento) -> str:
    """Como se nombra un tratamiento cuando otra seccion lo referencia."""
    return f"{t.tipo} (inicio {t.fecha_inicio.strftime('%d/%m/%Y')})"


async def _todos(session: AsyncSession, consulta) -> list:
    return list((await session.execute(consulta)).scalars().all())


@router.get("/pacientes/{paciente_id}/pdf/historia-completa")
async def pdf_historia_completa(
    paciente_id: UUID,
    session: AsyncSession = Depends(get_session),
    usuario: Usuario = Depends(get_current_usuario),
):
    """
    Todo en orden cronologico (lo mas antiguo primero): en un documento
    impreso se lee como un relato. En pantalla los historiales siguen mas
    reciente primero.
    """
    paciente = await obtener_paciente_o_404(paciente_id, session)
    profesional = await profesional_del_usuario(usuario, session)
    hoy = hoy_venezuela()

    antecedentes = (
        await session.execute(
            select(Antecedente.nombre, PacienteAntecedente.detalle)
            .join(Antecedente, Antecedente.id == PacienteAntecedente.antecedente_id)
            .where(PacienteAntecedente.paciente_id == paciente_id, PacienteAntecedente.presente.is_(True))
            .order_by(Antecedente.nombre)
        )
    ).all()

    visitas = await _todos(
        session,
        select(Visita).where(Visita.paciente_id == paciente_id).order_by(Visita.fecha, Visita.creado_en),
    )

    tratamientos = await _todos(
        session,
        select(Tratamiento)
        .where(Tratamiento.paciente_id == paciente_id)
        .order_by(Tratamiento.fecha_inicio, Tratamiento.creado_en),
    )
    por_id = {t.id: t for t in tratamientos}
    dientes: dict[UUID, list[int]] = {t.id: [] for t in tratamientos}
    if tratamientos:
        for fila in await _todos(
            session,
            select(TratamientoDiente)
            .where(TratamientoDiente.tratamiento_id.in_(por_id))
            .order_by(TratamientoDiente.numero_diente),
        ):
            dientes[fila.tratamiento_id].append(fila.numero_diente)
    profesionales = {
        p.id: p
        for p in await _todos(
            session,
            select(ProfesionalTratante).where(
                ProfesionalTratante.id.in_({t.profesional_tratante_id for t in tratamientos})
            ),
        )
    }

    bitacora = await _todos(
        session,
        select(BitacoraTratamiento)
        .where(BitacoraTratamiento.paciente_id == paciente_id)
        .order_by(BitacoraTratamiento.fecha, BitacoraTratamiento.creado_en),
    )
    # Quien registro cada entrada: el nombre del profesional vinculado al
    # usuario (ej. "Leonor Granados"), no el nombre de login ("dra.granados").
    ids_responsables = {e.responsable for e in bitacora}
    responsables = {
        u.id: u.nombre
        for u in await _todos(session, select(Usuario).where(Usuario.id.in_(ids_responsables)))
    }
    responsables |= {
        p.usuario_id: p.nombre
        for p in await _todos(
            session, select(ProfesionalTratante).where(ProfesionalTratante.usuario_id.in_(ids_responsables))
        )
    }

    observaciones = await _todos(
        session,
        select(Observacion)
        .where(Observacion.paciente_id == paciente_id, Observacion.tipo.in_(TIPOS_OBSERVACION_EN_HISTORIA))
        .order_by(Observacion.fecha, Observacion.creado_en),
    )

    consentimientos = await _todos(
        session,
        select(Consentimiento)
        .where(Consentimiento.paciente_id == paciente_id)
        .order_by(Consentimiento.fecha, Consentimiento.creado_en),
    )

    pdf = await generar_pdf(
        "historia_clinica.html",
        {
            "profesional": profesional,
            "paciente": paciente,
            "edad": _edad(paciente.fecha_nacimiento, hoy) if paciente.fecha_nacimiento else None,
            "fecha_emision": hoy,
            "antecedentes": antecedentes,
            "visitas": [
                {
                    "v": v,
                    "higiene": etiquetas.HIGIENE.get(v.higiene),
                    "examenes": [txt for campo, txt in etiquetas.EXAMENES_COMPLEMENTARIOS if getattr(v, campo)],
                }
                for v in visitas
            ],
            "tratamientos": [
                {
                    "t": t,
                    "estado": etiquetas.ESTADO_TRATAMIENTO[t.estado],
                    "origen": etiquetas.ORIGEN_TRATAMIENTO[t.origen],
                    "profesional": profesionales[t.profesional_tratante_id].nombre,
                    "dientes": dientes[t.id],
                }
                for t in tratamientos
            ],
            "bitacora": [
                {
                    "e": e,
                    "hallazgo": etiquetas.HALLAZGO.get(e.tipo_hallazgo),
                    "superficie": etiquetas.SUPERFICIE.get(e.superficie),
                    "tratamiento": _nombre_tratamiento(por_id[e.tratamiento_id]) if e.tratamiento_id else None,
                    "responsable": responsables.get(e.responsable),
                }
                for e in bitacora
            ],
            "observaciones": [
                {"o": o, "tipo": etiquetas.TIPO_OBSERVACION[o.tipo]} for o in observaciones
            ],
            "consentimientos": [
                {
                    "c": c,
                    "tipo": etiquetas.TIPO_CONSENTIMIENTO[c.tipo],
                    "tratamiento": _nombre_tratamiento(por_id[c.tratamiento_id]) if c.tratamiento_id else None,
                }
                for c in consentimientos
            ],
        },
    )
    nombre = f"historia-clinica-{paciente.numero_historia}-{hoy.isoformat()}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre}"'},
    )
