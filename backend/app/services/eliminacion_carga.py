# app/services/eliminacion_carga.py — Eliminar UN registro cargado por error en una historia
# «en carga» (procedimiento de carga, 15/10/2026). Solo se usa mientras la historia no esta
# aprobada: una historia oficial no se elimina, se corrige con trazabilidad.
#
# Recorre las claves foraneas del modelo (como borrado_paciente): lo que apunta al registro con
# una columna opcional se desvincula (queda sin visita / sin tratamiento), las tablas «hijas
# propias» (dientes de una entrada, tratamientos de una visita) se borran con el, y si algo mas
# depende de el (una constancia, un periodontograma...) no se elimina y se dice que hay que
# quitar primero.

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

import app.models  # noqa: F401 — registra todas las tablas
from app.db import Base
from app.enums import EstadoHistoria
from app.models.odontograma import OdontogramaHallazgo, OdontogramaLesionApical
from app.models.paciente import Paciente
from app.services.borrado_paciente import _tablas_existentes

# Se borran junto con el registro que las posee.
HIJAS_PROPIAS = {"visita_tratamiento", "tratamiento_diente", "bitacora_diente", "puente_fijo_diente"}

NOMBRES = {
    "constancia_asistencia": "una constancia de asistencia",
    "periodontograma_registro": "un periodontograma",
    "periodontograma_diente_resumen": "un periodontograma",
    "receta": "una receta",
    "indicacion_tratamiento": "unas indicaciones de tratamiento",
    "consentimiento": "un consentimiento",
}


async def exigir_en_carga(session: AsyncSession, paciente_id: UUID) -> Paciente:
    paciente = await session.get(Paciente, paciente_id)
    if paciente is None:
        raise HTTPException(404, "Paciente no encontrado")
    if paciente.estado_historia != EstadoHistoria.en_carga:
        raise HTTPException(
            409,
            "Esta historia ya está aprobada: no se eliminan registros. Corríjalo con «Quitar» "
            "o avise a Francisco.",
        )
    return paciente


async def eliminar_registro(session: AsyncSession, modelo, registro_id: UUID) -> None:
    """Elimina `registro_id` de `modelo` y desvincula o borra lo que apuntaba a el. Confirma al final."""
    tabla = modelo.__table__
    existentes = await _tablas_existentes(session)
    bloqueos: set[str] = set()
    acciones = []
    for t in Base.metadata.sorted_tables:
        if t.name not in existentes:
            continue
        for fk in t.foreign_keys:
            if fk.column.table is not tabla:
                continue
            col = fk.parent
            n = (await session.execute(select(func.count()).select_from(t).where(col == registro_id))).scalar_one()
            if not n:
                continue
            if t.name in HIJAS_PROPIAS:
                acciones.append(delete(t).where(col == registro_id))
            elif col.nullable:
                acciones.append(update(t).where(col == registro_id).values({col.name: None}))
            else:
                bloqueos.add(NOMBRES.get(t.name, t.name))
    if bloqueos:
        raise HTTPException(
            409,
            "No se puede eliminar: tiene vinculado " + " y ".join(sorted(bloqueos)) + ". Elimínelo primero.",
        )
    for accion in acciones:
        await session.execute(accion)
    await session.execute(delete(tabla).where(tabla.c.id == registro_id))
    await session.commit()


async def reabrir_lo_que_cerro(session: AsyncSession, hallazgo_id: UUID) -> None:
    """Deshacer un hallazgo: lo que se cerro al agregarlo (reemplazo) vuelve a estar activo."""
    for modelo in (OdontogramaHallazgo, OdontogramaLesionApical):
        await session.execute(
            update(modelo)
            .where(modelo.resuelto_por_hallazgo_id == hallazgo_id)
            .values(resuelto=False, resuelto_fecha=None, resuelto_por_hallazgo_id=None)
        )
