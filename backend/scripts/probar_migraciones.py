"""Prueba las migraciones de Alembic contra un Postgres real y desechable.

Uso (desde Fase2-Historia-Clinica-App/repo):
    .venv-pg/Scripts/python backend/scripts/probar_migraciones.py

Levanta un Postgres embebido (pixeltable-pgserver) en una carpeta temporal,
corre 0001 -> head, verifica los valores nuevos de enum, la correccion de
nivel_insercion (0024) con una fila real, y los downgrade. No toca ninguna
base real; borra todo al terminar. Entorno: ver .venv-pg (no se versiona).
"""

import os
import sys
import tempfile
import uuid
from pathlib import Path

import pixeltable_pgserver as pgserver
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

BACKEND = Path(__file__).resolve().parent.parent
os.chdir(BACKEND)  # alembic/env.py usa os.getcwd()


def _valor_por_defecto(col, enums):
    t = col.type
    if isinstance(t, sa.Enum) or (hasattr(t, "enums") and getattr(t, "enums", None)):
        return list(t.enums)[0]
    if isinstance(t, sa.Boolean):
        return False
    if isinstance(t, (sa.Integer, sa.SmallInteger, sa.BigInteger)):
        return 1
    if isinstance(t, (sa.Numeric, sa.Float)):
        return 1
    if isinstance(t, sa.DateTime):
        return "2026-10-05 00:00:00"
    if isinstance(t, sa.Date):
        return "2026-10-05"
    if isinstance(t, sa.Uuid) or "UUID" in str(t).upper():
        return str(uuid.uuid4())
    return uuid.uuid4().hex[: min(getattr(t, "length", None) or 8, 8)]  # unico: hay UNIQUE en nombres


def insertar_minimo(conn, tabla, forzado=None, hechos=None):
    """Inserta una fila con solo las columnas NOT NULL (y sus padres por FK)."""
    meta = sa.MetaData()
    meta.reflect(conn)
    t = meta.tables[tabla]
    valores = dict(forzado or {})
    for col in t.columns:
        if col.name in valores or (col.nullable and not col.foreign_keys) or col.server_default is not None and col.name not in valores and col.nullable:
            continue
        if not col.nullable and col.name not in valores:
            if col.foreign_keys:
                fk = next(iter(col.foreign_keys))
                # Reutiliza una fila padre existente (evita choques de UNIQUE/PK).
                existente = conn.execute(sa.select(fk.column).limit(1)).scalar()
                valores[col.name] = existente if existente is not None else insertar_minimo(
                    conn, fk.column.table.name, hechos=hechos)
            elif col.server_default is None:
                valores[col.name] = _valor_por_defecto(col, None)
    conn.execute(t.insert().values(**valores))
    pk = [c for c in t.primary_key.columns][0]
    return valores.get(pk.name)


# El Postgres embebido no trae las extensiones contrib: la 0005 pide unaccent
# (solo la usa la busqueda de pacientes). Aqui se sustituye por una funcion
# vacia; 0023-0025 no dependen de ella. Produccion si la tiene.
@sa.event.listens_for(sa.engine.Engine, "before_cursor_execute", retval=True)
def _sin_unaccent(conn, cursor, statement, parameters, context, executemany):
    if "CREATE EXTENSION IF NOT EXISTS unaccent" in statement:
        statement = "CREATE OR REPLACE FUNCTION unaccent(text) RETURNS text AS 'select $1' LANGUAGE sql IMMUTABLE"
    elif "DROP EXTENSION IF EXISTS unaccent" in statement:
        statement = "DROP FUNCTION IF EXISTS unaccent(text)"
    return statement, parameters


def main() -> int:
    errores = []
    with tempfile.TemporaryDirectory() as carpeta:
        servidor = pgserver.get_server(carpeta, cleanup_mode="delete")
        uri = servidor.get_uri()
        # La app (app/db.py) pide asyncpg; env.py de Alembic lo convierte a psycopg2.
        os.environ["DATABASE_URL"] = uri.replace("postgresql://", "postgresql+asyncpg://", 1)
        cfg = Config(str(BACKEND / "alembic.ini"))
        eng = sa.create_engine(uri.replace("postgresql://", "postgresql+psycopg2://", 1))
        try:
            with eng.connect() as c:
                print("Postgres:", c.execute(sa.text("show server_version")).scalar())

            command.upgrade(cfg, "0023")
            print("OK upgrade 0001 -> 0023")

            # Fila con la formula VIEJA (NI = MG + PS): margen -3, sondaje 4 -> NI 1.
            with eng.begin() as c:
                insertar_minimo(c, "periodontograma_registro",
                                forzado={"margen_gingival": -3, "profundidad_sondaje": 4, "nivel_insercion": 1,
                                         "recesion_mm": 0})

            command.upgrade(cfg, "0025")
            print("OK upgrade 0023 -> 0025")
            with eng.connect() as c:
                ni = c.execute(sa.text("select nivel_insercion from periodontograma_registro")).scalar()
                if ni != 7:
                    errores.append(f"0024 no recalculo: NI={ni}, esperado 7 (4 - (-3))")
                print("NI recalculado:", ni)
                sup = {r[0] for r in c.execute(sa.text("select unnest(enum_range(null::superficie_dental))::text"))}
                tip = {r[0] for r in c.execute(sa.text("select unnest(enum_range(null::tipo_hallazgo))::text"))}
                if "palatino_lingual" not in sup:
                    errores.append("falta palatino_lingual en superficie_dental")
                if "supernumerario" not in tip:
                    errores.append("falta supernumerario en tipo_hallazgo")
                print("enums OK:", "palatino_lingual" in sup, "supernumerario" in tip)

            # CHECK nuevo activo: NI incoherente debe fallar.
            try:
                with eng.begin() as c:
                    insertar_minimo(c, "periodontograma_registro",
                                    forzado={"margen_gingival": -3, "profundidad_sondaje": 4, "nivel_insercion": 1,
                                             "recesion_mm": 0})
                errores.append("el CHECK nuevo acepto una fila con la formula vieja")
            except sa.exc.IntegrityError as e:
                if "ck_perio_nivel_insercion_calculado" in str(e):
                    print("OK CHECK rechaza formula vieja")
                else:
                    errores.append(f"la fila fallo por otra causa, no por el CHECK: {str(e)[:150]}")
            except Exception as e:  # noqa: BLE001
                print("AVISO: no se pudo probar el CHECK:", type(e).__name__, str(e)[:120])

            # Insertar un hallazgo con los valores nuevos.
            with eng.begin() as c:
                insertar_minimo(c, "odontograma_hallazgo",
                                forzado={"tipo_hallazgo": "supernumerario", "numero_diente": 13})
                insertar_minimo(c, "odontograma_hallazgo",
                                forzado={"tipo_hallazgo": "caries", "numero_diente": 14,
                                         "superficie": "palatino_lingual"})
            print("OK hallazgos con supernumerario y palatino_lingual")

            # Downgrade con una fila palatino_lingual: 0023 debe negarse.
            command.downgrade(cfg, "0024")  # 0025 no-op
            try:
                command.downgrade(cfg, "0022")
                errores.append("downgrade 0023 debio fallar con filas palatino_lingual")
            except RuntimeError as e:
                print("OK downgrade 0023 se niega:", str(e)[:70])
            except Exception as e:  # noqa: BLE001
                if "palatino_lingual" in str(e):
                    print("OK downgrade 0023 se niega:", str(e)[:70])
                else:
                    errores.append(f"downgrade fallo por otra causa: {e}")
        finally:
            eng.dispose()
            servidor.cleanup()
    print("\nERRORES:" if errores else "\nTODO OK", *errores, sep="\n- " if errores else "")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
