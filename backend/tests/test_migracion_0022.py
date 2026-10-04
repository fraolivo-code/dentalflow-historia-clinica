# La migracion 0022 corre aqui sobre SQLite: se arman las tablas previas
# minimas con entradas de bitacora (con y sin diente), se aplica upgrade, se
# revisa la copia de datos y se hace downgrade. No sustituye a correrla una vez
# en Postgres real.

import importlib.util
import pathlib
import uuid

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql

VERSIONES = pathlib.Path(__file__).parent.parent / "alembic" / "versions"
COLUMNAS = {
    "id", "bitacora_id", "numero_diente", "creado_en", "creado_por", "actualizado_en", "actualizado_por"
}


def _cargar(archivo: str, nombre: str):
    spec = importlib.util.spec_from_file_location(nombre, VERSIONES / archivo)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ejecutar(conn, funcion):
    with Operations.context(MigrationContext.configure(conn)):
        funcion()


def test_upgrade_copia_los_dientes_existentes_y_downgrade_revierte():
    mig = _cargar("0022_bitacora_diente.py", "mig0022")
    assert (mig.revision, mig.down_revision) == ("0022", "0021")
    assert _cargar("0021_paciente_cambio.py", "mig0021b").revision == mig.down_revision

    engine = sa.create_engine("sqlite://")
    meta = sa.MetaData()
    uuid_t = postgresql.UUID(as_uuid=True)
    sa.Table("usuario", meta, sa.Column("id", uuid_t, primary_key=True))
    sa.Table("diente_anatomia", meta, sa.Column("numero_diente", sa.SmallInteger, primary_key=True))
    sa.Table(
        "bitacora_tratamiento",
        meta,
        sa.Column("id", uuid_t, primary_key=True),
        sa.Column("numero_diente", sa.SmallInteger, nullable=True),
        sa.Column("descripcion", sa.Text, nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creado_por", uuid_t, nullable=False),
    )
    usuario = uuid.uuid4().hex
    con_diente, con_diente2, sin_diente = (uuid.uuid4().hex for _ in range(3))
    with engine.begin() as conn:
        meta.create_all(conn)
        conn.execute(sa.text("INSERT INTO usuario (id) VALUES (:i)"), {"i": usuario})
        for n in (11, 36):
            conn.execute(sa.text("INSERT INTO diente_anatomia (numero_diente) VALUES (:n)"), {"n": n})
        for id_, diente, texto in (
            (con_diente, 11, "uno"),
            (con_diente2, 36, "dos"),
            (sin_diente, None, "sin diente"),
        ):
            conn.execute(
                sa.text(
                    "INSERT INTO bitacora_tratamiento (id, numero_diente, descripcion, creado_en, creado_por) "
                    "VALUES (:id, :d, :t, '2025-03-04 10:00:00', :u)"
                ),
                {"id": id_, "d": diente, "t": texto, "u": usuario},
            )

        _ejecutar(conn, mig.upgrade)

        insp = sa.inspect(conn)
        assert {c["name"] for c in insp.get_columns("bitacora_diente")} == COLUMNAS
        assert {f["referred_table"] for f in insp.get_foreign_keys("bitacora_diente")} == {
            "bitacora_tratamiento", "diente_anatomia", "usuario",
        }
        assert any(
            set(u["column_names"]) == {"bitacora_id", "numero_diente"}
            for u in insp.get_unique_constraints("bitacora_diente")
        )
        filas = conn.execute(
            sa.text("SELECT bitacora_id, numero_diente, creado_en, creado_por FROM bitacora_diente")
        ).fetchall()
        assert sorted((f.bitacora_id, f.numero_diente) for f in filas) == sorted(
            [(con_diente, 11), (con_diente2, 36)]
        )  # la entrada sin diente no genera fila
        assert all(f.creado_por == usuario and str(f.creado_en).startswith("2025-03-04") for f in filas)
        # Las entradas originales quedan intactas, con su columna numero_diente.
        originales = conn.execute(
            sa.text("SELECT id, numero_diente FROM bitacora_tratamiento")
        ).fetchall()
        assert sorted((o.id, o.numero_diente) for o in originales if o.numero_diente) == sorted(
            [(con_diente, 11), (con_diente2, 36)]
        )
        assert len(originales) == 3

        _ejecutar(conn, mig.downgrade)
        tablas = sa.inspect(conn).get_table_names()
        assert "bitacora_diente" not in tablas and "bitacora_tratamiento" in tablas
        assert conn.execute(sa.text("SELECT count(*) FROM bitacora_tratamiento")).scalar_one() == 3


def test_upgrade_sin_entradas_no_falla():
    mig = _cargar("0022_bitacora_diente.py", "mig0022b")
    engine = sa.create_engine("sqlite://")
    meta = sa.MetaData()
    uuid_t = postgresql.UUID(as_uuid=True)
    sa.Table("usuario", meta, sa.Column("id", uuid_t, primary_key=True))
    sa.Table("diente_anatomia", meta, sa.Column("numero_diente", sa.SmallInteger, primary_key=True))
    sa.Table(
        "bitacora_tratamiento",
        meta,
        sa.Column("id", uuid_t, primary_key=True),
        sa.Column("numero_diente", sa.SmallInteger, nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creado_por", uuid_t, nullable=False),
    )
    with engine.begin() as conn:
        meta.create_all(conn)
        _ejecutar(conn, mig.upgrade)
        assert conn.execute(sa.text("SELECT count(*) FROM bitacora_diente")).scalar_one() == 0
