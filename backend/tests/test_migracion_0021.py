# La migracion 0021 corre aqui sobre SQLite (tablas previas minimas: usuario y
# paciente), con upgrade, revision y downgrade. No sustituye a correrla una vez
# en Postgres real.

import importlib.util
import pathlib
import uuid

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql

VERSIONES = pathlib.Path(__file__).parent.parent / "alembic" / "versions"

COLUMNAS = {"id", "paciente_id", "fecha", "actor_id", "campo", "valor_anterior", "valor_nuevo"}


def _cargar(archivo: str, nombre: str):
    spec = importlib.util.spec_from_file_location(nombre, VERSIONES / archivo)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ejecutar(conn, funcion):
    with Operations.context(MigrationContext.configure(conn)):
        funcion()


def test_upgrade_crea_paciente_cambio_y_downgrade_la_borra():
    mig = _cargar("0021_paciente_cambio.py", "mig0021")
    assert (mig.revision, mig.down_revision) == ("0021", "0020")
    assert _cargar("0020_numeracion_y_seguro.py", "mig0020b").revision == mig.down_revision

    engine = sa.create_engine("sqlite://")
    meta = sa.MetaData()
    uuid_t = postgresql.UUID(as_uuid=True)
    sa.Table("usuario", meta, sa.Column("id", uuid_t, primary_key=True))
    sa.Table("paciente", meta, sa.Column("id", uuid_t, primary_key=True))
    with engine.begin() as conn:
        meta.create_all(conn)
        usuario, paciente = uuid.uuid4().hex, uuid.uuid4().hex
        conn.execute(sa.text("INSERT INTO usuario (id) VALUES (:i)"), {"i": usuario})
        conn.execute(sa.text("INSERT INTO paciente (id) VALUES (:i)"), {"i": paciente})

        _ejecutar(conn, mig.upgrade)
        insp = sa.inspect(conn)
        columnas = {c["name"]: c for c in insp.get_columns("paciente_cambio")}
        assert set(columnas) == COLUMNAS
        assert columnas["valor_anterior"]["nullable"] and columnas["valor_nuevo"]["nullable"]
        assert not columnas["campo"]["nullable"] and not columnas["actor_id"]["nullable"]
        assert {f["referred_table"] for f in insp.get_foreign_keys("paciente_cambio")} == {
            "paciente",
            "usuario",
        }
        assert any(i["column_names"] == ["paciente_id"] for i in insp.get_indexes("paciente_cambio"))

        conn.execute(
            sa.text(
                "INSERT INTO paciente_cambio (id, paciente_id, fecha, actor_id, campo) "
                "VALUES ('c1', :p, '2026-10-05 10:00:00', :u, 'movil')"
            ),
            {"p": paciente, "u": usuario},
        )

        _ejecutar(conn, mig.downgrade)
        tablas = sa.inspect(conn).get_table_names()
        assert "paciente_cambio" not in tablas
        assert {"usuario", "paciente"} <= set(tablas)
