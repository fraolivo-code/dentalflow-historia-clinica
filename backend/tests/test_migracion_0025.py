# La migracion 0025 (ALTER TYPE ... ADD VALUE) solo existe en Postgres: aqui se
# verifica el SQL que emite (modo offline). No sustituye a correrla en un Postgres real.

import importlib.util
import io
import pathlib

from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.enums import GRUPO_CONDICION, TipoHallazgo
from app.models import OdontogramaHallazgo

VERSIONES = pathlib.Path(__file__).parent.parent / "alembic" / "versions"


def _cargar():
    spec = importlib.util.spec_from_file_location("mig0025", VERSIONES / "0025_hallazgo_supernumerario.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_revision_encadenada_a_0024():
    mig = _cargar()
    assert (mig.revision, mig.down_revision) == ("0025", "0024")


def test_upgrade_agrega_el_valor_fuera_de_la_transaccion():
    mig = _cargar()
    salida = io.StringIO()
    ctx = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": salida, "transactional_ddl": True}
    )
    with Operations.context(ctx):
        mig.upgrade()
    sql = salida.getvalue()
    alter = "ALTER TYPE tipo_hallazgo ADD VALUE IF NOT EXISTS 'supernumerario'"
    assert alter in sql
    assert "COMMIT" in sql[: sql.index(alter)]
    assert "BEGIN" in sql[sql.index(alter):]


def test_el_modelo_conoce_el_valor_y_es_de_grupo_condicion():
    assert "supernumerario" in OdontogramaHallazgo.__table__.c.tipo_hallazgo.type.enums
    assert TipoHallazgo.supernumerario in GRUPO_CONDICION
