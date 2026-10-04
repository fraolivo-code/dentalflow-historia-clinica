# La migracion 0018 corre aqui sobre SQLite (usa batch_alter_table, sin funciones
# de Postgres): se arma la tabla usuario "vieja", se aplica upgrade y se revisa;
# despues downgrade. No sustituye a correrla una vez en Postgres real.

import importlib.util
import pathlib
import uuid

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql

RUTA = (
    pathlib.Path(__file__).parent.parent
    / "alembic"
    / "versions"
    / "0018_gestion_usuarios_claves.py"
)

COLUMNAS_NUEVAS = {
    "email",
    "debe_cambiar_clave",
    "clave_cambiada_en",
    "intentos_fallidos",
    "bloqueado_hasta",
    "ultimo_login",
    "creado_por",
    "actualizado_en",
}


def _cargar():
    spec = importlib.util.spec_from_file_location("mig0018", RUTA)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tabla_vieja(conn, nombres):
    meta = sa.MetaData()
    viejo = sa.Table(
        "usuario",
        meta,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("nombre", sa.String(200), nullable=False, unique=True),
        sa.Column("rol", sa.String(20), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=True),
    )
    meta.create_all(conn)
    conn.execute(
        viejo.insert(),
        [
            {"id": uuid.uuid4(), "nombre": n, "rol": "dra", "password_hash": "x", "activo": True}
            for n in nombres
        ],
    )


def _ejecutar(conn, funcion):
    with Operations.context(MigrationContext.configure(conn)):
        funcion()


def _columnas(conn, tabla):
    return {c["name"] for c in sa.inspect(conn).get_columns(tabla)}


def test_encadenado_a_0017():
    mig = _cargar()
    assert (mig.revision, mig.down_revision) == ("0018", "0017")


def test_upgrade_y_downgrade():
    mig = _cargar()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        _tabla_vieja(conn, ["Dra.Granados", " Asistente "])

        _ejecutar(conn, mig.upgrade)

        assert COLUMNAS_NUEVAS <= _columnas(conn, "usuario")
        assert {"token_recuperacion", "auditoria_usuario"} <= set(sa.inspect(conn).get_table_names())
        indices = {i["name"]: i for i in sa.inspect(conn).get_indexes("usuario")}
        assert indices["uq_usuario_email"]["unique"]
        # Nombres a minusculas y sin espacios en los bordes; el resto no cambia.
        filas = conn.execute(
            sa.text("SELECT nombre, debe_cambiar_clave, intentos_fallidos, email FROM usuario ORDER BY nombre")
        ).all()
        assert filas == [("asistente", 0, 0, None), ("dra.granados", 0, 0, None)]

        # Correo unico entre los no nulos; varios NULL conviven.
        conn.execute(sa.text("UPDATE usuario SET email = 'a@e.com' WHERE nombre = 'asistente'"))
        with pytest.raises(sa.exc.IntegrityError):
            with conn.begin_nested():
                conn.execute(
                    sa.text("UPDATE usuario SET email = 'a@e.com' WHERE nombre = 'dra.granados'")
                )

        _ejecutar(conn, mig.downgrade)

        assert _columnas(conn, "usuario") == {
            "id", "nombre", "rol", "password_hash", "activo", "creado_en"
        }
        assert not {"token_recuperacion", "auditoria_usuario"} & set(sa.inspect(conn).get_table_names())
        assert "uq_usuario_email" not in {i["name"] for i in sa.inspect(conn).get_indexes("usuario")}
        # Los usuarios siguen ahi (los nombres quedan en minusculas).
        assert conn.execute(sa.text("SELECT count(*) FROM usuario")).scalar() == 2


def test_nombres_que_solo_difieren_en_mayusculas_detienen_la_migracion():
    mig = _cargar()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        _tabla_vieja(conn, ["Maria", "MARIA", "otra"])

        with pytest.raises(RuntimeError) as error:
            _ejecutar(conn, mig.upgrade)

        mensaje = str(error.value)
        assert "mayusculas" in mensaje and "'Maria'" in mensaje and "'MARIA'" in mensaje
        assert "No se modifico nada" in mensaje
        # No se fusiono ni se renombro nada, y no se agrego ninguna columna.
        assert sorted(conn.execute(sa.text("SELECT nombre FROM usuario")).scalars()) == [
            "MARIA", "Maria", "otra"
        ]
        assert not COLUMNAS_NUEVAS & _columnas(conn, "usuario")
        assert "token_recuperacion" not in sa.inspect(conn).get_table_names()
