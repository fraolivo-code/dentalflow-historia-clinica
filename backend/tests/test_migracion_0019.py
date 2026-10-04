# La migracion 0019 corre aqui sobre SQLite (sin funciones de Postgres): se arma
# la tabla usuario (la FK apunta a ella), se aplica upgrade y se revisa; despues
# downgrade. No sustituye a correrla una vez en Postgres real.

import importlib.util
import pathlib
import uuid

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql

RUTA = (
    pathlib.Path(__file__).parent.parent
    / "alembic"
    / "versions"
    / "0019_configuracion_consultorio.py"
)

COLUMNAS = {
    "id",
    "nombre",
    "frase",
    "imagen",
    "imagen_tipo",
    "imagen_actualizada_en",
    "actualizado_por",
    "actualizado_en",
}


def _cargar():
    spec = importlib.util.spec_from_file_location("mig0019", RUTA)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ejecutar(conn, funcion):
    with Operations.context(MigrationContext.configure(conn)):
        funcion()


def test_upgrade_crea_la_fila_unica_vacia_y_downgrade_revierte():
    mig = _cargar()
    assert (mig.revision, mig.down_revision) == ("0019", "0018")
    engine = sa.create_engine("sqlite://")
    meta = sa.MetaData()
    sa.Table("usuario", meta, sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True))
    with engine.begin() as conn:
        meta.create_all(conn)
        conn.execute(sa.text("INSERT INTO usuario (id) VALUES (:id)"), {"id": uuid.uuid4().hex})

        _ejecutar(conn, mig.upgrade)

        insp = sa.inspect(conn)
        assert {c["name"] for c in insp.get_columns("configuracion_consultorio")} == COLUMNAS
        filas = conn.execute(sa.text("SELECT * FROM configuracion_consultorio")).mappings().all()
        assert len(filas) == 1 and filas[0]["id"] == 1
        assert all(filas[0][c] is None for c in COLUMNAS - {"id"})  # creada vacia

        # Una sola fila: el id fijo impide una segunda.
        try:
            conn.execute(sa.text("INSERT INTO configuracion_consultorio (id) VALUES (1)"))
            raise AssertionError("debio rechazar un segundo id=1")
        except sa.exc.IntegrityError:
            pass

        _ejecutar(conn, mig.downgrade)
        assert "configuracion_consultorio" not in sa.inspect(conn).get_table_names()
        assert "usuario" in sa.inspect(conn).get_table_names()
