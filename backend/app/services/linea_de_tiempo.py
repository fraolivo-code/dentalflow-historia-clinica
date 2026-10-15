# app/services/linea_de_tiempo.py — Cronologia del paciente (flujo de visitas, fase 4, 15/10/2026).
# Une en una sola lista, de la mas reciente a la mas antigua, lo que ya existe en varias
# tablas: visitas, bitacora, hallazgos del odontograma (cuando se marcan y cuando se
# resuelven), lesiones apicales, puentes, examenes y tratamientos. Con `diente` solo trae lo
# de ese diente (el comportamiento de un diente reparado puede tener otra incidencia).
# Es solo lectura: no hay tabla nueva ni migracion.

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import EstadoExamen, EstadoTratamiento, TipoExamen, TipoVisita
from app.models.bitacora_tratamiento import BitacoraDiente, BitacoraTratamiento
from app.models.examen import ExamenSolicitado
from app.models.odontograma import (
    OdontogramaHallazgo,
    OdontogramaLesionApical,
    PuenteFijo,
    PuenteFijoDiente,
)
from app.models.tratamiento import Tratamiento, TratamientoDiente
from app.models.visita import Visita
from app.services import etiquetas
from app.services.odontograma_logic import orden_anatomico

TIPO_VISITA = {
    TipoVisita.evaluacion: "Evaluación",
    TipoVisita.tratamiento: "Tratamiento",
    TipoVisita.control_limpieza: "Control y limpieza",
    TipoVisita.emergencia: "Emergencia",
    TipoVisita.otra: "Otra",
}
TIPO_EXAMEN = {
    TipoExamen.rx_periapical: "Rx periapical",
    TipoExamen.rx_panoramica: "Rx panorámica",
    TipoExamen.tomografia: "Tomografía",
    TipoExamen.otro: "Examen",
}

# Dentro de un mismo dia: primero la visita, luego tratamientos y examenes, la bitacora, y
# al final lo que cambio en el odontograma (en la lista, de arriba abajo).
_ORDEN = {
    "visita": 0,
    "tratamiento_inicio": 1,
    "tratamiento_fin": 1,
    "examen_indicado": 2,
    "examen_traido": 2,
    "bitacora": 3,
    "hallazgo": 4,
    "hallazgo_resuelto": 5,
    "lesion": 4,
    "lesion_resuelta": 5,
    "puente": 4,
    "puente_desarmado": 5,
}


def _evento(tipo: str, id_, fecha: date, titulo: str, detalle: str | None, dientes, momento: datetime | None):
    return {
        "id": f"{tipo}:{id_}",
        "tipo": tipo,
        "fecha": fecha,
        "titulo": titulo,
        "detalle": detalle,
        "dientes": sorted(set(dientes), key=orden_anatomico),
        "momento": momento,
    }


def _dmy(d: date) -> str:
    return d.strftime("%d/%m/%Y")


async def construir(session: AsyncSession, paciente_id: UUID, diente: int | None = None) -> list[dict]:
    eventos: list[dict] = []
    todos = diente is None

    # --- visitas (sin diente: solo en la linea general)
    if todos:
        for v in (await session.execute(select(Visita).where(Visita.paciente_id == paciente_id))).scalars():
            titulo = "Visita" + (f" — {TIPO_VISITA[v.tipo]}" if v.tipo else "")
            eventos.append(_evento("visita", v.id, v.fecha, titulo, v.motivo_consulta, [], v.creado_en))

    # --- bitacora
    entradas = list(
        (await session.execute(select(BitacoraTratamiento).where(BitacoraTratamiento.paciente_id == paciente_id)))
        .scalars()
        .all()
    )
    dientes_de: dict[UUID, list[int]] = {e.id: [] for e in entradas}
    if entradas:
        filas = await session.execute(
            select(BitacoraDiente.bitacora_id, BitacoraDiente.numero_diente).where(
                BitacoraDiente.bitacora_id.in_([e.id for e in entradas])
            )
        )
        for bitacora_id, numero in filas:
            dientes_de[bitacora_id].append(numero)
    for e in entradas:
        # Una entrada anterior a la migracion 0022 no tiene filas en bitacora_diente.
        lista = dientes_de[e.id] or ([e.numero_diente] if e.numero_diente is not None else [])
        if todos or diente in lista:
            eventos.append(_evento("bitacora", e.id, e.fecha, "Bitácora", e.descripcion, lista, e.creado_en))

    # --- hallazgos del odontograma: cuando se marcan y cuando se resuelven
    consulta = select(OdontogramaHallazgo).where(OdontogramaHallazgo.paciente_id == paciente_id)
    if not todos:
        consulta = consulta.where(OdontogramaHallazgo.numero_diente == diente)
    hallazgos = list((await session.execute(consulta)).scalars().all())
    por_id = {h.id: h for h in hallazgos}
    for h in hallazgos:
        nombre = etiquetas.etiqueta_hallazgo(h.tipo_hallazgo, h.superficie, h.numero_diente)
        eventos.append(
            _evento("hallazgo", h.id, h.fecha, f"Se marcó: {nombre}", None, [h.numero_diente], h.creado_en)
        )
        if h.resuelto and h.resuelto_fecha:
            if h.resuelto_por_hallazgo_id and h.resuelto_por_hallazgo_id in por_id:
                causa = por_id[h.resuelto_por_hallazgo_id]
                detalle = "Reemplazado por " + etiquetas.etiqueta_hallazgo(
                    causa.tipo_hallazgo, causa.superficie, causa.numero_diente
                )
            else:
                detalle = "Cerrado manualmente"
            detalle += f" · marcado el {_dmy(h.fecha)}"
            eventos.append(
                _evento("hallazgo_resuelto", h.id, h.resuelto_fecha, f"Se resolvió: {nombre}", detalle,
                        [h.numero_diente], h.actualizado_en or h.creado_en)
            )

    # --- lesiones apicales
    consulta = select(OdontogramaLesionApical).where(OdontogramaLesionApical.paciente_id == paciente_id)
    if not todos:
        consulta = consulta.where(OdontogramaLesionApical.numero_diente == diente)
    for l in (await session.execute(consulta)).scalars():
        nombre = etiquetas.etiqueta_lesion(l.tipo, l.raiz)
        eventos.append(_evento("lesion", l.id, l.fecha, f"Se marcó: {nombre}", None, [l.numero_diente], l.creado_en))
        if l.resuelto and l.resuelto_fecha:
            eventos.append(
                _evento("lesion_resuelta", l.id, l.resuelto_fecha, f"Se resolvió: {nombre}",
                        f"Marcada el {_dmy(l.fecha)}", [l.numero_diente], l.actualizado_en or l.creado_en)
            )

    # --- puentes
    puentes = list((await session.execute(select(PuenteFijo).where(PuenteFijo.paciente_id == paciente_id))).scalars())
    if puentes:
        filas = await session.execute(
            select(PuenteFijoDiente.puente_id, PuenteFijoDiente.numero_diente).where(
                PuenteFijoDiente.puente_id.in_([p.id for p in puentes])
            )
        )
        dientes_puente: dict[UUID, list[int]] = {p.id: [] for p in puentes}
        for puente_id, numero in filas:
            dientes_puente[puente_id].append(numero)
        for p in puentes:
            lista = sorted(dientes_puente[p.id], key=orden_anatomico)
            if not todos and diente not in lista:
                continue
            secuencia = "-".join(str(n) for n in lista)
            estado = etiquetas.ESTADO_PUENTE[p.estado_general]
            eventos.append(
                _evento("puente", p.id, p.fecha, f"Se armó el puente {secuencia}", f"Prótesis {estado}", lista, p.creado_en)
            )
            if p.resuelto and p.resuelto_fecha:
                eventos.append(
                    _evento("puente_desarmado", p.id, p.resuelto_fecha, f"Se desarmó el puente {secuencia}", None,
                            lista, p.actualizado_en or p.creado_en)
                )

    # --- tratamientos
    trats = list((await session.execute(select(Tratamiento).where(Tratamiento.paciente_id == paciente_id))).scalars())
    if trats:
        filas = await session.execute(
            select(TratamientoDiente.tratamiento_id, TratamientoDiente.numero_diente).where(
                TratamientoDiente.tratamiento_id.in_([t.id for t in trats])
            )
        )
        dientes_trat: dict[UUID, list[int]] = {t.id: [] for t in trats}
        for tratamiento_id, numero in filas:
            dientes_trat[tratamiento_id].append(numero)
        for t in trats:
            lista = dientes_trat[t.id]
            if not todos and diente not in lista:
                continue
            eventos.append(_evento("tratamiento_inicio", t.id, t.fecha_inicio, f"Inició el tratamiento: {t.tipo}",
                                   t.notas_relevantes, lista, t.creado_en))
            if t.fecha_fin and t.estado in (EstadoTratamiento.completado, EstadoTratamiento.suspendido):
                eventos.append(
                    _evento("tratamiento_fin", t.id, t.fecha_fin,
                            f"{etiquetas.ESTADO_TRATAMIENTO[t.estado]}: {t.tipo}", None, lista,
                            t.actualizado_en or t.creado_en)
                )

    # --- examenes (sin diente: solo en la linea general)
    if todos:
        for x in (await session.execute(select(ExamenSolicitado).where(ExamenSolicitado.paciente_id == paciente_id))).scalars():
            nombre = TIPO_EXAMEN[x.tipo] + (f" — {x.descripcion}" if x.descripcion else "")
            eventos.append(_evento("examen_indicado", x.id, x.fecha_indicacion, f"Examen indicado: {nombre}",
                                   None, [], x.creado_en))
            if x.estado == EstadoExamen.traido and x.fecha_traido:
                eventos.append(
                    _evento("examen_traido", x.id, x.fecha_traido, f"Examen traído: {nombre}",
                            x.hallazgos or "Sin hallazgos registrados.", [], x.actualizado_en or x.creado_en)
                )

    # Mas reciente primero; en un mismo dia, el orden de _ORDEN y luego el momento de la carga.
    eventos.sort(key=lambda e: (e["momento"].timestamp() if e["momento"] else 0), reverse=True)
    eventos.sort(key=lambda e: _ORDEN[e["tipo"]])
    eventos.sort(key=lambda e: e["fecha"], reverse=True)
    for e in eventos:
        e.pop("momento")
    return eventos
