# app/services/borrado_paciente.py — Borrado de UN paciente con todo lo que depende de el.
#
# La aplicacion NO borra pacientes ni registros clinicos (a proposito). Esto existe solo para
# quitar pacientes de PRUEBA de produccion, con respaldo previo y ejecutado por Francisco
# desde la terminal (scripts/borrar_paciente.py). No lo usa ninguna ruta de la API.
#
# En vez de listar tablas a mano, recorre las claves foraneas del modelo: todo lo que apunta
# al paciente, directa o indirectamente (visitas, bitacora, hallazgos, examenes...), se borra
# de las hojas hacia la raiz. Lo que NO es hijo del paciente (usuarios, profesionales,
# catalogos) no se toca. Si manana se agrega una tabla nueva, entra sola.

from uuid import UUID

from sqlalchemy import Table, delete, func, inspect, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.models  # noqa: F401 — registra todas las tablas en Base.metadata
from app.db import Base
from app.models.paciente import Paciente


async def _tablas_existentes(session: AsyncSession) -> set[str]:
    conexion = await session.connection()
    return set(await conexion.run_sync(lambda c: inspect(c).get_table_names()))


async def calcular(
    session: AsyncSession, paciente_id: UUID
) -> tuple[dict[Table, set], dict[Table, list], dict[str, Table]]:
    """
    Devuelve (ids, hojas, tablas):
      ids    tabla -> ids de las filas que dependen del paciente (tablas con PK simple),
      hojas  tabla -> [(columna, tabla_padre)] para tablas de PK compuesta (solo se borran),
      tablas nombre -> Table (solo las que existen en la base).
    """
    existentes = await _tablas_existentes(session)
    tablas = {t.name: t for t in Base.metadata.sorted_tables if t.name in existentes}
    paciente = tablas["paciente"]
    ids: dict[Table, set] = {paciente: {paciente_id}}
    hojas: dict[Table, list] = {}
    cola = [paciente]
    while cola:
        padre = cola.pop(0)
        if not ids.get(padre):
            continue
        for t in tablas.values():
            if t is paciente:
                continue
            columnas = [fk.parent for fk in t.foreign_keys if fk.column.table is padre]
            if not columnas:
                continue
            pk = list(t.primary_key.columns)
            if len(pk) == 1:
                for c in columnas:
                    filas = (await session.execute(select(pk[0]).where(c.in_(ids[padre])))).scalars().all()
                    nuevos = set(filas) - ids.get(t, set())
                    if nuevos:
                        ids.setdefault(t, set()).update(nuevos)
                        if t not in cola:
                            cola.append(t)
            else:
                hojas.setdefault(t, []).extend((c, padre) for c in columnas)
    return ids, hojas, tablas


def _filtro_hoja(refs: list, ids: dict[Table, set]):
    return or_(*[c.in_(ids[padre]) for c, padre in refs if ids.get(padre)])


async def contar(session: AsyncSession, paciente_id: UUID) -> dict[str, int]:
    """Cuantas filas se borrarian en cada tabla (no borra nada)."""
    ids, hojas, _ = await calcular(session, paciente_id)
    cuentas = {t.name: len(v) for t, v in ids.items()}
    for t, refs in hojas.items():
        n = (await session.execute(select(func.count()).select_from(t).where(_filtro_hoja(refs, ids)))).scalar_one()
        if n:
            cuentas[t.name] = n
    return cuentas


async def borrar(session: AsyncSession, paciente_id: UUID) -> dict[str, int]:
    """
    Borra el paciente y todo lo que depende de el, en una sola transaccion (confirma al final).
    Devuelve las filas borradas por tabla.
    """
    ids, hojas, _ = await calcular(session, paciente_id)
    borradas: dict[str, int] = {}
    # sorted_tables va de los padres a los hijos: al reves, primero los hijos.
    for t in reversed(Base.metadata.sorted_tables):
        if t in hojas:
            filtro = _filtro_hoja(hojas[t], ids)
        elif t in ids and ids[t]:
            filtro = t.primary_key.columns.values()[0].in_(ids[t])
        else:
            continue
        resultado = await session.execute(delete(t).where(filtro))
        if resultado.rowcount:
            borradas[t.name] = resultado.rowcount
    await session.commit()
    return borradas


async def buscar_por_historia(session: AsyncSession, numero: str) -> Paciente | None:
    """El numero se compara por valor: '433' y '000433' son el mismo paciente."""
    if not numero.strip().isdecimal():
        return None
    buscado = int(numero)
    for p in (await session.execute(select(Paciente))).scalars():
        if p.numero_historia.isdecimal() and int(p.numero_historia) == buscado:
            return p
    return None
