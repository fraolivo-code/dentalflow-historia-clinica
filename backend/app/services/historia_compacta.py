# app/services/historia_compacta.py — Historia del paciente en una linea por hecho (15/10/2026).
# La Dra. pidio verla por dia: lo que se encontro, lo que se hizo y las notas, sin repetir el mismo
# hecho en varias tarjetas (marcar, resolver, bitacora automatica). Ademas, un resumen «se encontro /
# estado» de lo que hay que tratar (pendiente o tratado). Solo lectura: no hay tabla nueva.
#
# Un dia es un bloque (lo que importa es la fecha, no a que visita quedo enlazado cada registro).

from collections import defaultdict
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import TipoHallazgo
from app.models.odontograma import OdontogramaHallazgo
from app.services import etiquetas, linea_de_tiempo
from app.services.odontograma_logic import orden_anatomico
from app.services.tratamiento_realizado import REGLAS

# Lo que un «Tratamiento realizado» puede cerrar = lo que hay que tratar.
POR_TRATAR = frozenset(t for regla in REGLAS.values() for t in regla.cierra)
# Resultados de un tratamiento: solo cuentan como «lo hecho» si cerraron algo o tienen su entrada automatica.
RESULTADOS = frozenset(t for regla in REGLAS.values() for t in regla.abre)
_NOMBRES_REGLAS = tuple(regla.nombre for regla in REGLAS.values())
# Tipos de evento de la linea de tiempo que se muestran tal cual en «otros» del dia.
_OTROS = frozenset({"examen_indicado", "examen_traido", "tratamiento_inicio", "tratamiento_fin",
                    "lesion", "lesion_resuelta", "puente", "puente_desarmado"})


def _es_entrada_automatica(texto: str, diente: int) -> bool:
    """La entrada que escribe «Tratamiento realizado» cuando la Dra. no escribe nada: «<Tratamiento>, diente N»."""
    return any(texto.startswith(f"{nombre}, diente {diente}") for nombre in _NOMBRES_REGLAS)


def _etiqueta(h: OdontogramaHallazgo) -> str:
    return etiquetas.etiqueta_hallazgo(h.tipo_hallazgo, h.superficie, h.numero_diente)


async def construir(session: AsyncSession, paciente_id: UUID) -> dict:
    eventos = await linea_de_tiempo.construir(session, paciente_id)
    hallazgos = list(
        (await session.execute(select(OdontogramaHallazgo).where(OdontogramaHallazgo.paciente_id == paciente_id)))
        .scalars()
        .all()
    )
    por_id = {h.id: h for h in hallazgos}
    cerrados_por: dict[UUID, list[OdontogramaHallazgo]] = defaultdict(list)
    for h in hallazgos:
        if h.resuelto and h.resuelto_por_hallazgo_id:
            cerrados_por[h.resuelto_por_hallazgo_id].append(h)

    # ------------------------------------------------------------------ resumen
    resumen = []
    for h in sorted(hallazgos, key=lambda x: (orden_anatomico(x.numero_diente), x.fecha)):
        if h.tipo_hallazgo not in POR_TRATAR:
            continue
        causa = por_id.get(h.resuelto_por_hallazgo_id) if h.resuelto_por_hallazgo_id else None
        if not h.resuelto:
            estado, fecha_estado, con = "pendiente", None, None
        elif causa is not None:
            estado, fecha_estado, con = "tratado", h.resuelto_fecha, _etiqueta(causa)
        else:
            estado, fecha_estado, con = "quitado", h.resuelto_fecha, None
        resumen.append({
            "diente": h.numero_diente, "hallazgo": _etiqueta(h), "fecha": h.fecha,
            "estado": estado, "fecha_estado": fecha_estado, "con": con,
        })
    resumen.sort(key=lambda r: r["estado"] != "pendiente")  # pendientes primero (estable: sigue el orden del arco)

    # ------------------------------------------------------------------- por dia
    dias: dict[date, dict] = defaultdict(lambda: {"visitas": [], "hallazgos": [], "realizado": [], "quitados": [],
                                                  "notas": [], "otros": []})
    entradas = [e for e in eventos if e["tipo"] == "bitacora"]
    for e in eventos:
        if e["tipo"] == "visita":
            tipo = e["titulo"].removeprefix("Visita").removeprefix(" — ") or None
            dias[e["fecha"]]["visitas"].append({"tipo": tipo, "motivo": e["detalle"]})
        elif e["tipo"] in _OTROS:
            dias[e["fecha"]]["otros"].append(e["titulo"] + (f": {e['detalle']}" if e["detalle"] else ""))

    usadas: set[str] = set()  # entradas de bitacora ya absorbidas por una linea de «se hizo»
    for fecha in sorted({h.fecha for h in hallazgos}):
        del_dia = [h for h in hallazgos if h.fecha == fecha]
        auto = {d for e in entradas if e["fecha"] == fecha for d in e["dientes"]
                if _es_entrada_automatica(e["detalle"] or "", d)}
        hechos = [
            h for h in del_dia
            if cerrados_por.get(h.id) or (h.tipo_hallazgo in RESULTADOS and h.numero_diente in auto)
        ]
        ids_hechos = {h.id for h in hechos}
        for h in del_dia:
            if h.id not in ids_hechos:
                dias[fecha]["hallazgos"].append({"diente": h.numero_diente, "etiqueta": _etiqueta(h)})
        por_diente: dict[int, list[OdontogramaHallazgo]] = defaultdict(list)
        for h in hechos:
            por_diente[h.numero_diente].append(h)
        for diente in sorted(por_diente, key=orden_anatomico):
            abiertos = por_diente[diente]
            antes = [_etiqueta(x) for h in abiertos for x in cerrados_por.get(h.id, [])]
            nota = None
            for e in entradas:
                if e["fecha"] == fecha and e["dientes"] == [diente] and e["id"] not in usadas:
                    usadas.add(e["id"])
                    if not _es_entrada_automatica(e["detalle"] or "", diente):
                        nota = e["detalle"]
                    break
            dias[fecha]["realizado"].append(
                {"diente": diente, "antes": antes, "despues": [_etiqueta(h) for h in abiertos], "nota": nota}
            )

    for h in hallazgos:  # quitados a mano (sin un resultado que los reemplace)
        if h.resuelto and h.resuelto_fecha and not h.resuelto_por_hallazgo_id:
            dias[h.resuelto_fecha]["quitados"].append({"diente": h.numero_diente, "etiqueta": _etiqueta(h)})

    for e in entradas:  # notas: lo que no se absorbio en una linea de «se hizo» ni es automatico
        if e["id"] in usadas:
            continue
        if len(e["dientes"]) == 1 and _es_entrada_automatica(e["detalle"] or "", e["dientes"][0]):
            continue
        dias[e["fecha"]]["notas"].append({"dientes": e["dientes"], "texto": e["detalle"] or ""})

    bloques = [{"fecha": fecha, **datos} for fecha, datos in dias.items() if any(datos.values())]
    bloques.sort(key=lambda b: b["fecha"], reverse=True)
    return {"resumen": resumen, "dias": bloques}
