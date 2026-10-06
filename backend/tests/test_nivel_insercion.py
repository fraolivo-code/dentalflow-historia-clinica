# Nivel de insercion del periodontograma (05/10/2026): NI = PS - MG. La Dra.
# anota el margen gingival en NEGATIVO cuando hay recesion (Berna / perio-tools).

import importlib.util
import pathlib

import pytest
import pytest_asyncio
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app import security
from app.enums import RolUsuario
from app.models import Usuario
from app.models.periodontograma import PeriodontogramaRegistro
from app.services.periodontograma import calcular_nivel_insercion

VERSIONES = pathlib.Path(__file__).parent.parent / "alembic" / "versions"
# (margen gingival, profundidad de sondaje, nivel de insercion esperado)
EJEMPLOS = [(2, 2, 0), (5, 5, 0), (2, 7, 5), (-4, 2, 6)]


@pytest.mark.parametrize("mg,ps,ni", EJEMPLOS)
def test_calculo(mg, ps, ni):
    assert calcular_nivel_insercion(mg, ps) == ni


# --- por la API ------------------------------------------------------------------


@pytest_asyncio.fixture
async def h_dra(session_factory):
    async with session_factory() as s:
        u = Usuario(nombre="doctora", rol=RolUsuario.dra, password_hash="x", email="doctora@e.com")
        s.add(u)
        await s.commit()
        uid = u.id
    # Las tablas del periodontograma no estan en el fixture comun (usan ARRAY/FK a catalogos).
    async with session_factory.kw["bind"].begin() as conn:
        await conn.run_sync(PeriodontogramaRegistro.__table__.create, checkfirst=True)
        from app.models.periodontograma import PeriodontogramaDienteResumen

        await conn.run_sync(PeriodontogramaDienteResumen.__table__.create, checkfirst=True)
    return {"Authorization": f"Bearer {security.crear_access_token(uid, 'dra')}"}


async def _visita(client, h):
    p = await client.post(
        "/pacientes", headers=h,
        json={"movil": "04141234567", "nombre_completo": "Paciente Perio", "fecha_registro": "2026-10-05",
              "fecha_primera_consulta_real": "2012-04-01"},
    )
    assert p.status_code == 201, p.text
    pid = p.json()["id"]
    v = await client.post(f"/pacientes/{pid}/visitas", headers=h, json={"fecha": "2026-10-05", "paciente_id": pid})
    assert v.status_code == 201, v.text
    return pid, v.json()["id"]


async def test_alta_y_correccion_calculan_ni_como_ps_menos_mg(client, h_dra):
    pid, vid = await _visita(client, h_dra)
    sitios = ["mesiovestibular", "vestibular", "distovestibular", "distopalatino_lingual"]
    registros = [
        {"numero_diente": 11, "sitio": sitio, "margen_gingival": mg, "profundidad_sondaje": ps}
        for sitio, (mg, ps, _) in zip(sitios, EJEMPLOS)
    ] + [  # el alta exige los 6 sitios del diente
        {"numero_diente": 11, "sitio": sitio, "margen_gingival": 0, "profundidad_sondaje": 2}
        for sitio in ("palatino_lingual", "mesiopalatino_lingual")
    ]
    r = await client.post(
        f"/visitas/{vid}/periodontograma", headers=h_dra,
        json={"registros": registros, "resumenes": [{"numero_diente": 11, "movilidad": 0}]},
    )
    assert r.status_code == 201, r.text
    creados = {x["sitio"]: x for x in r.json()["registros"]}
    for sitio, (mg, ps, ni) in zip(sitios, EJEMPLOS):
        assert creados[sitio]["nivel_insercion"] == ni, (mg, ps)

    # PATCH: el NI se recalcula con la formula nueva (MG -4 / PS 2 -> 6; luego PS 3 -> 7).
    registro = creados["distopalatino_lingual"]
    r = await client.patch(
        f"/pacientes/{pid}/periodontograma/registros/{registro['id']}", headers=h_dra,
        json={"profundidad_sondaje": 3},
    )
    assert r.status_code == 200, r.text
    assert r.json()["nivel_insercion"] == 7


# --- migracion 0024 (sobre SQLite: no sustituye correrla una vez en Postgres) ------


def _cargar():
    spec = importlib.util.spec_from_file_location("mig0024", VERSIONES / "0024_nivel_insercion_ps_menos_mg.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tabla(conn, formula):
    meta = sa.MetaData()
    sa.Table(
        "periodontograma_registro", meta,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("margen_gingival", sa.SmallInteger, nullable=False),
        sa.Column("profundidad_sondaje", sa.SmallInteger, nullable=False),
        sa.Column("nivel_insercion", sa.SmallInteger, nullable=False),
        sa.CheckConstraint(formula, name="ck_perio_nivel_insercion_calculado"),
    )
    meta.create_all(conn)


def _ni(conn):
    return [f.ni for f in conn.execute(sa.text("SELECT nivel_insercion AS ni FROM periodontograma_registro ORDER BY id"))]


def test_la_migracion_recalcula_las_filas_existentes_y_es_reversible():
    mig = _cargar()
    assert (mig.revision, mig.down_revision) == ("0024", "0023")
    with sa.create_engine("sqlite://").begin() as conn:
        _tabla(conn, "nivel_insercion = margen_gingival + profundidad_sondaje")  # formula vieja
        for i, (mg, ps, _) in enumerate(EJEMPLOS, 1):
            conn.execute(sa.text("INSERT INTO periodontograma_registro VALUES (:i, :mg, :ps, :ni)"),
                         {"i": i, "mg": mg, "ps": ps, "ni": mg + ps})
        contexto = MigrationContext.configure(conn)
        with Operations.context(contexto):
            mig.upgrade()
        assert _ni(conn) == [ni for _, _, ni in EJEMPLOS]
        # El CHECK nuevo rige: una fila con la formula vieja se rechaza.
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(sa.text("INSERT INTO periodontograma_registro VALUES (9, -4, 2, -2)"))
        with Operations.context(MigrationContext.configure(conn)):
            mig.downgrade()
        assert _ni(conn) == [mg + ps for mg, ps, _ in EJEMPLOS]
        assert [(f.mg, f.ps) for f in conn.execute(sa.text(
            "SELECT margen_gingival AS mg, profundidad_sondaje AS ps FROM periodontograma_registro ORDER BY id"))] == [
            (mg, ps) for mg, ps, _ in EJEMPLOS]  # MG y PS intactos
