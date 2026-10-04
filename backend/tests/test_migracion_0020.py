# La migracion 0020 corre aqui sobre SQLite: se arma el estado previo (tabla
# paciente minima + la 0019 real), se aplica upgrade, se revisa y se hace
# downgrade. No sustituye a correrla una vez en Postgres real.

import importlib.util
import pathlib
import uuid

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql

VERSIONES = pathlib.Path(__file__).parent.parent / "alembic" / "versions"


def _cargar(archivo: str, nombre: str):
    spec = importlib.util.spec_from_file_location(nombre, VERSIONES / archivo)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ejecutar(conn, funcion):
    with Operations.context(MigrationContext.configure(conn)):
        funcion()


def _columnas(conn, tabla):
    return {c["name"]: c for c in sa.inspect(conn).get_columns(tabla)}


def test_upgrade_agrega_ancho_y_seguro_y_downgrade_revierte():
    m19 = _cargar("0019_configuracion_consultorio.py", "mig0019")
    m20 = _cargar("0020_numeracion_y_seguro.py", "mig0020")
    assert (m20.revision, m20.down_revision) == ("0020", "0019")
    assert m20.down_revision == m19.revision

    engine = sa.create_engine("sqlite://")
    meta = sa.MetaData()
    sa.Table("usuario", meta, sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True))
    sa.Table(
        "paciente",
        meta,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("numero_historia", sa.String(50), nullable=False),
    )
    with engine.begin() as conn:
        meta.create_all(conn)
        conn.execute(sa.text("INSERT INTO usuario (id) VALUES (:id)"), {"id": uuid.uuid4().hex})
        conn.execute(sa.text("INSERT INTO paciente (id, numero_historia) VALUES ('p1', '0001')"))
        _ejecutar(conn, m19.upgrade)

        _ejecutar(conn, m20.upgrade)
        ancho = _columnas(conn, "configuracion_consultorio")["numero_ancho"]
        assert ancho["nullable"] is False
        # la fila unica ya existente queda con el ancho por defecto
        valor = conn.execute(sa.text("SELECT numero_ancho FROM configuracion_consultorio"))
        assert valor.scalar_one() == 4
        seguro = _columnas(conn, "paciente")["seguro"]
        assert seguro["nullable"] is True and seguro["type"].length == 120
        # los pacientes existentes quedan sin seguro
        assert conn.execute(sa.text("SELECT seguro FROM paciente WHERE id = 'p1'")).scalar_one() is None

        _ejecutar(conn, m20.downgrade)
        assert "numero_ancho" not in _columnas(conn, "configuracion_consultorio")
        assert "seguro" not in _columnas(conn, "paciente")
        assert "numero_historia" in _columnas(conn, "paciente")
