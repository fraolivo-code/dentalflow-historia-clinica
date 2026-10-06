# La migracion 0023 (ALTER TYPE ... ADD VALUE) solo existe en Postgres: aqui se
# verifica el SQL que emite (modo offline, sin base) y el downgrade sobre
# SQLite. No sustituye a correrla una vez en un Postgres real.

import importlib.util
import io
import pathlib

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.enums import SuperficieDental
from app.models import BitacoraTratamiento, OdontogramaHallazgo

VERSIONES = pathlib.Path(__file__).parent.parent / "alembic" / "versions"


def _cargar():
    spec = importlib.util.spec_from_file_location("mig0023", VERSIONES / "0023_superficie_palatino_lingual.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_revision_encadenada_a_0022():
    mig = _cargar()
    assert (mig.revision, mig.down_revision) == ("0023", "0022")


def test_upgrade_agrega_el_valor_fuera_de_la_transaccion():
    mig = _cargar()
    salida = io.StringIO()
    ctx = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": salida, "transactional_ddl": True}
    )
    with Operations.context(ctx):
        mig.upgrade()
    sql = salida.getvalue()
    alter = "ALTER TYPE superficie_dental ADD VALUE IF NOT EXISTS 'palatino_lingual'"
    assert alter in sql
    # Bloque autocommit: se cierra la transaccion antes del ALTER y se abre otra despues.
    assert "COMMIT" in sql[: sql.index(alter)]
    assert "BEGIN" in sql[sql.index(alter):]


def _tablas(conn, con_fila: str | None = None):
    meta = sa.MetaData()
    for nombre in ("odontograma_hallazgo", "bitacora_tratamiento"):
        sa.Table(nombre, meta, sa.Column("id", sa.Integer, primary_key=True), sa.Column("superficie", sa.String))
    meta.create_all(conn)
    if con_fila:
        conn.execute(sa.text(f"INSERT INTO {con_fila} (id, superficie) VALUES (1, 'palatino_lingual')"))


def test_downgrade_solo_verifica_y_pasa_sin_filas():
    mig = _cargar()
    with sa.create_engine("sqlite://").begin() as conn:
        _tablas(conn)
        conn.execute(sa.text("INSERT INTO odontograma_hallazgo (id, superficie) VALUES (1, 'oclusal')"))
        with Operations.context(MigrationContext.configure(conn)):
            mig.downgrade()
        assert conn.execute(sa.text("SELECT count(*) FROM odontograma_hallazgo")).scalar_one() == 1


@pytest.mark.parametrize("tabla", ["odontograma_hallazgo", "bitacora_tratamiento"])
def test_downgrade_falla_si_hay_filas_con_el_valor(tabla):
    mig = _cargar()
    with sa.create_engine("sqlite://").begin() as conn:
        _tablas(conn, con_fila=tabla)
        with Operations.context(MigrationContext.configure(conn)):
            with pytest.raises(RuntimeError, match=f"{tabla}.*palatino_lingual"):
                mig.downgrade()
        assert conn.execute(sa.text(f"SELECT count(*) FROM {tabla}")).scalar_one() == 1  # no toco nada


def test_los_modelos_conocen_el_valor_nuevo():
    assert SuperficieDental.palatino_lingual.value == "palatino_lingual"
    # SQLAlchemy enlaza el enum por NOMBRE: debe coincidir con el valor de Postgres.
    for columna in (OdontogramaHallazgo.__table__.c.superficie, BitacoraTratamiento.__table__.c.superficie):
        assert "palatino_lingual" in columna.type.enums
