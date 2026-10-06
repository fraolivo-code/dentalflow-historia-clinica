# app/routers/historia_clinica.py — Documento 5 de 5 de la Etapa 5 (PDF):
# historia clinica completa del paciente (derecho de acceso / Habeas Data).
# Junta en un solo PDF todo lo registrado: secciones de texto, odontograma
# (dibujo del estado actual + leyenda + hallazgos ya resueltos) y todos los
# levantamientos de periodontograma.

from collections import defaultdict
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_usuario, get_session, requerir_dra
from app.enums import SitioPeriodontal, TipoObservacion, admite_furcacion
from app.models.antecedente import Antecedente, PacienteAntecedente
from app.models.bitacora_tratamiento import BitacoraTratamiento
from app.models.consentimiento import Consentimiento
from app.models.observacion import Observacion
from app.models.periodontograma import PeriodontogramaDienteResumen, PeriodontogramaRegistro
from app.models.profesional_tratante import ProfesionalTratante
from app.models.tratamiento import Tratamiento, TratamientoDiente
from app.models.usuario import Usuario
from app.models.visita import Visita
from app.routers.bitacora import con_dientes
from app.routers.constancias_asistencia import profesional_del_usuario
from app.routers.pacientes import obtener_paciente_o_404
from app.services import etiquetas
from app.services.fechas import hoy_venezuela
from app.services.odontograma_impreso import cargar_estado, leyenda_por_diente
from app.services.odontograma_svg import ARCO_INFERIOR, ARCO_SUPERIOR, odontograma_svg
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


async def _odontograma(session: AsyncSession, paciente_id: UUID) -> dict:
    """Dibujo del estado actual, leyenda por diente y lo ya resuelto."""
    estado = await cargar_estado(session, paciente_id)
    hallazgos, lesiones, puentes = estado["hallazgos"], estado["lesiones"], estado["puentes"]
    dientes_de = estado["dientes_de"]

    activos = [h for h in hallazgos if not h.resuelto]
    lesiones_activas = [l for l in lesiones if not l.resuelto]
    puentes_activos = [(p, dientes_de[p.id]) for p in puentes if not p.resuelto]

    # Leyenda: lo mismo que el titulo (tooltip) de cada diente en pantalla.
    leyenda = leyenda_por_diente(activos, lesiones_activas, puentes_activos)

    # Ya resueltos: el dibujo solo muestra el estado actual; esto conserva el pasado.
    resueltos = [
        {"fecha": h.fecha, "resuelto": h.resuelto_fecha, "dientes": str(h.numero_diente),
         "descripcion": etiquetas.etiqueta_hallazgo(h.tipo_hallazgo, h.superficie, h.numero_diente)}
        for h in hallazgos if h.resuelto
    ] + [
        {"fecha": l.fecha, "resuelto": l.resuelto_fecha, "dientes": str(l.numero_diente),
         "descripcion": etiquetas.etiqueta_lesion(l.tipo, l.raiz)}
        for l in lesiones if l.resuelto
    ] + [
        {"fecha": p.fecha, "resuelto": p.resuelto_fecha,
         "dientes": "-".join(str(dp.numero_diente) for dp in dientes_de[p.id]),
         "descripcion": f"Puente fijo ({etiquetas.ESTADO_PUENTE[p.estado_general]})"}
        for p in puentes if p.resuelto
    ]
    resueltos.sort(key=lambda r: (r["fecha"], r["resuelto"] or date.max))

    return {
        "svg": odontograma_svg(activos, lesiones_activas, puentes_activos, estado["raices"]),
        "leyenda": [(n, leyenda[n]) for n in ARCO_SUPERIOR + ARCO_INFERIOR if leyenda[n]],
        "resueltos": resueltos,
    }


# Sitios de cada cara en el orden en que se ven de frente: en los cuadrantes
# 1 y 4 (izquierda de la hoja) lo distal queda a la izquierda; en 2 y 3, lo mesial.
_VESTIBULAR = (SitioPeriodontal.distovestibular, SitioPeriodontal.vestibular, SitioPeriodontal.mesiovestibular)
_PALATINO = (
    SitioPeriodontal.distopalatino_lingual,
    SitioPeriodontal.palatino_lingual,
    SitioPeriodontal.mesiopalatino_lingual,
)


def _sitios_de_frente(numero: int, cara: tuple) -> tuple:
    return cara if numero // 10 in (1, 4) else tuple(reversed(cara))


async def _periodontogramas(session: AsyncSession, paciente_id: UUID) -> list[dict]:
    """Todos los levantamientos, del mas antiguo al mas nuevo (decision 26/09/2026)."""
    registros = await _todos(
        session, select(PeriodontogramaRegistro).where(PeriodontogramaRegistro.paciente_id == paciente_id)
    )
    resumenes = await _todos(
        session, select(PeriodontogramaDienteResumen).where(PeriodontogramaDienteResumen.paciente_id == paciente_id)
    )
    if not registros and not resumenes:
        return []
    por_visita: dict[UUID, dict] = defaultdict(lambda: {"sitios": {}, "resumen": {}})
    for r in registros:
        por_visita[r.visita_id]["sitios"][(r.numero_diente, r.sitio)] = r
    for r in resumenes:
        por_visita[r.visita_id]["resumen"][r.numero_diente] = r
    visitas = {v.id: v for v in await _todos(session, select(Visita).where(Visita.id.in_(por_visita)))}

    levantamientos = []
    for visita_id in sorted(por_visita, key=lambda v: (visitas[v].fecha, visitas[v].creado_en)):
        datos = por_visita[visita_id]
        arcos = []
        for nombre, cara_interna, dientes in (("Arco superior", "Palatino", ARCO_SUPERIOR),
                                               ("Arco inferior", "Lingual", ARCO_INFERIOR)):
            columnas = []
            for n in dientes:
                resumen = datos["resumen"].get(n)
                columnas.append({
                    "numero": n,
                    "medido": resumen is not None or any((n, s) in datos["sitios"] for s in SitioPeriodontal),
                    "vestibular": [datos["sitios"].get((n, s)) for s in _sitios_de_frente(n, _VESTIBULAR)],
                    "interna": [datos["sitios"].get((n, s)) for s in _sitios_de_frente(n, _PALATINO)],
                    "movilidad": resumen.movilidad if resumen else None,
                    "furcacion": resumen.furcacion.value if resumen and resumen.furcacion else None,
                    "admite_furcacion": admite_furcacion(n),
                })
            arcos.append({"nombre": nombre, "cara_interna": cara_interna, "dientes": columnas})
        levantamientos.append({"fecha": visitas[visita_id].fecha, "arcos": arcos})
    return levantamientos


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
    await con_dientes(session, bitacora)
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

    odontograma = await _odontograma(session, paciente_id)
    periodontogramas = await _periodontogramas(session, paciente_id)

    pdf = await generar_pdf(
        "historia_clinica.html",
        {
            "odontograma": odontograma,
            "periodontogramas": periodontogramas,
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
                    "superficie": etiquetas.etiqueta_superficie(e.superficie, e.dientes) if e.superficie else None,
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
