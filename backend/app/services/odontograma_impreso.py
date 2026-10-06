# app/services/odontograma_impreso.py — Datos del odontograma para imprimir
# (04/10/2026): estado activo del paciente, leyenda por diente (lo mismo que ve
# la historia completa), lineas por diente y plan de tratamiento en gris.

from collections import defaultdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import EstadoTratamiento
from app.models.odontograma import (
    DienteAnatomia,
    OdontogramaHallazgo,
    OdontogramaLesionApical,
    PuenteFijo,
    PuenteFijoDiente,
)
from app.models.tratamiento import Tratamiento, TratamientoDiente
from app.services import etiquetas
from app.services.odontograma_logic import orden_anatomico
from app.services.odontograma_svg import ARCO_INFERIOR, ARCO_SUPERIOR

SEPARADOR = " · "
ESTADOS_ACTIVOS = (EstadoTratamiento.indicado, EstadoTratamiento.en_curso)


async def _todos(session: AsyncSession, consulta) -> list:
    return list((await session.execute(consulta)).scalars().all())


async def raices_por_diente(session: AsyncSession) -> dict[int, list[str]]:
    return {d.numero_diente: list(d.nombres_raices) for d in await _todos(session, select(DienteAnatomia))}


async def cargar_estado(session: AsyncSession, paciente_id: UUID) -> dict:
    """
    Todo lo registrado del odontograma del paciente: hallazgos, lesiones y
    puentes (activos y resueltos), los dientes de cada puente en orden
    anatomico y las raices por diente.
    """
    hallazgos = await _todos(
        session,
        select(OdontogramaHallazgo)
        .where(OdontogramaHallazgo.paciente_id == paciente_id)
        .order_by(OdontogramaHallazgo.fecha, OdontogramaHallazgo.creado_en),
    )
    lesiones = await _todos(
        session,
        select(OdontogramaLesionApical)
        .where(OdontogramaLesionApical.paciente_id == paciente_id)
        .order_by(OdontogramaLesionApical.fecha, OdontogramaLesionApical.creado_en),
    )
    puentes = await _todos(
        session,
        select(PuenteFijo).where(PuenteFijo.paciente_id == paciente_id).order_by(PuenteFijo.fecha),
    )
    dientes_de: dict[UUID, list] = {p.id: [] for p in puentes}
    if puentes:
        for dp in await _todos(session, select(PuenteFijoDiente).where(PuenteFijoDiente.puente_id.in_(dientes_de))):
            dientes_de[dp.puente_id].append(dp)
    for lista in dientes_de.values():
        lista.sort(key=lambda dp: orden_anatomico(dp.numero_diente))
    return {
        "hallazgos": hallazgos,
        "lesiones": lesiones,
        "puentes": puentes,
        "dientes_de": dientes_de,
        "raices": await raices_por_diente(session),
    }


def leyenda_por_diente(activos, lesiones_activas, puentes_activos) -> dict[int, list[str]]:
    """Texto de lo activo en cada diente (el titulo/tooltip de cada diente en pantalla)."""
    leyenda = defaultdict(list)
    for p, dientes in puentes_activos:
        secuencia = "-".join(str(dp.numero_diente) for dp in dientes)
        for dp in dientes:
            leyenda[dp.numero_diente].append(
                f"Puente {secuencia} ({etiquetas.ESTADO_PUENTE[p.estado_general]}): "
                f"{etiquetas.ROL_PUENTE[dp.rol]}, {etiquetas.HALLAZGO[dp.condicion_individual].lower()}"
            )
    for h in activos:
        leyenda[h.numero_diente].append(etiquetas.etiqueta_hallazgo(h.tipo_hallazgo, h.superficie, h.numero_diente))
    for l in lesiones_activas:
        leyenda[l.numero_diente].append(etiquetas.etiqueta_lesion(l.tipo, l.raiz))
    return leyenda


def lineas_por_diente(leyenda: dict[int, list[str]] | None = None) -> dict:
    """
    Las 32 lineas de la hoja, en el orden del papel: cuadrantes 1 y 2 arriba,
    4 y 3 abajo. Cada linea: (numero, texto en gris o ""). Sin `leyenda`
    (modo blanco) todos los textos quedan vacios.
    """
    leyenda = leyenda or {}

    def linea(n: int) -> tuple[int, str]:
        return n, SEPARADOR.join(leyenda.get(n, []))

    return {
        "superior": [linea(n) for n in ARCO_SUPERIOR],
        "inferior": [linea(n) for n in ARCO_INFERIOR],
    }


async def plan_de_tratamiento(session: AsyncSession, paciente_id: UUID) -> list[str]:
    """Tratamientos activos (indicado / en curso), uno por linea, con sus dientes."""
    tratamientos = await _todos(
        session,
        select(Tratamiento)
        .where(Tratamiento.paciente_id == paciente_id, Tratamiento.estado.in_(ESTADOS_ACTIVOS))
        .order_by(Tratamiento.fecha_inicio, Tratamiento.creado_en),
    )
    dientes: dict[UUID, list[int]] = {t.id: [] for t in tratamientos}
    if tratamientos:
        for fila in await _todos(
            session, select(TratamientoDiente).where(TratamientoDiente.tratamiento_id.in_(dientes))
        ):
            dientes[fila.tratamiento_id].append(fila.numero_diente)
    lineas = []
    for t in tratamientos:
        numeros = sorted(dientes[t.id], key=orden_anatomico)
        donde = f" — dientes {', '.join(str(n) for n in numeros)}" if len(numeros) > 1 else (
            f" — diente {numeros[0]}" if numeros else ""
        )
        lineas.append(f"{t.tipo}{donde} ({etiquetas.ESTADO_TRATAMIENTO[t.estado]})")
    return lineas
