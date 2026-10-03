# La migracion 0016 corre aqui sobre SQLite (no usa funciones de Postgres): se
# arma la tabla paciente "vieja" (sin la columna), se inserta, se aplica upgrade
# y se revisa; despues downgrade. No sustituye a correrla una vez en Postgres real.

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
    / "0016_paciente_movil_normalizado.py"
)


def _cargar():
    spec = importlib.util.spec_from_file_location("mig0016", RUTA)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_upgrade_calcula_existentes_y_downgrade_revierte():
    mig = _cargar()
    assert (mig.revision, mig.down_revision) == ("0016", "0015")
    engine = sa.create_engine("sqlite://")
    meta = sa.MetaData()
    viejo = sa.Table(
        "paciente",
        meta,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("movil", sa.String(50), nullable=False),
    )
    moviles = [
        "0414-123.45.67",
        "+58 424 7654321",
        "4121112233",
        "+1 305 555 1234",
        "123",
        "584141234567",
    ]
    with engine.begin() as conn:
        meta.create_all(conn)
        conn.execute(viejo.insert(), [{"id": uuid.uuid4(), "movil": m} for m in moviles])

        with Operations.context(MigrationContext.configure(conn)):
            mig.upgrade()
        insp = sa.inspect(conn)
        assert "movil_normalizado" in [c["name"] for c in insp.get_columns("paciente")]
        assert "ix_paciente_movil_normalizado" in [i["name"] for i in insp.get_indexes("paciente")]
        filas = dict(conn.execute(sa.text("SELECT movil, movil_normalizado FROM paciente")).all())
        assert filas == {
            "0414-123.45.67": "584141234567",
            "+58 424 7654321": "584247654321",
            "4121112233": "584121112233",
            "+1 305 555 1234": None,
            "123": None,
            "584141234567": "584141234567",
        }

        with Operations.context(MigrationContext.configure(conn)):
            mig.downgrade()
        insp = sa.inspect(conn)
        assert "movil_normalizado" not in [c["name"] for c in insp.get_columns("paciente")]
        assert not insp.get_indexes("paciente")
