# Flujo de visitas, fase 2 (15/10/2026): marcas nuevas del odontograma por la API.
# Especificacion: especificacion-tecnica-flujo-visitas-tratamientos.md, seccion 6.

from datetime import date as _date, timedelta as _timedelta

NAC_MENOR = (_date.today() - _timedelta(days=365 * 5)).isoformat()

import pytest
import pytest_asyncio

from app import security
from app.enums import RolUsuario
from app.models import Usuario


@pytest_asyncio.fixture
async def usuario_dra(session_factory):
    async with session_factory() as s:
        u = Usuario(nombre="doctora", rol=RolUsuario.dra, password_hash="x", email="d@e.com")
        s.add(u)
        await s.commit()
        return u.id


@pytest.fixture
def h_dra(usuario_dra):
    return {"Authorization": f"Bearer {security.crear_access_token(usuario_dra, 'dra')}"}


async def _paciente(client, h):
    r = await client.post(
        "/pacientes",
        headers=h,
        json={"movil": "04141234567", "nombre_completo": "Paciente Prueba", "fecha_registro": "2026-10-05", "fecha_nacimiento": NAC_MENOR},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _marca(client, h, pid, diente, tipo, superficie=None, fecha="2026-10-10"):
    return await client.post(
        f"/pacientes/{pid}/dientes/{diente}/hallazgos",
        headers=h,
        json={"numero_diente": diente, "tipo_hallazgo": tipo, "superficie": superficie, "fecha": fecha},
    )


async def _activos(client, h, pid, diente):
    r = await client.get(f"/pacientes/{pid}/odontograma", headers=h)
    return sorted(x["tipo_hallazgo"] for x in r.json() if x["numero_diente"] == diente)


@pytest.mark.parametrize("tipo", ["perno_ok", "perno_defecto", "sellante", "cambio_coloracion"])
async def test_las_marcas_nuevas_se_crean_sin_superficie(client, h_dra, tipo):
    pid = await _paciente(client, h_dra)
    r = await _marca(client, h_dra, pid, 22, tipo)
    assert r.status_code == 201, r.text
    assert r.json()["tipo_hallazgo"] == tipo


async def test_sellante_y_coloracion_son_condicion_no_cierran_ni_se_cierran(client, h_dra):
    pid = await _paciente(client, h_dra)
    await _marca(client, h_dra, pid, 22, "caries", "oclusal")
    await _marca(client, h_dra, pid, 22, "sellante")
    await _marca(client, h_dra, pid, 22, "cambio_coloracion")
    assert await _activos(client, h_dra, pid, 22) == ["cambio_coloracion", "caries", "sellante"]
    # un estado exclusivo (ausente) cierra la caries pero no las condiciones
    await _marca(client, h_dra, pid, 22, "ausente")
    assert await _activos(client, h_dra, pid, 22) == ["ausente", "cambio_coloracion", "sellante"]


async def test_perno_es_independiente_del_conducto(client, h_dra):
    pid = await _paciente(client, h_dra)
    await _marca(client, h_dra, pid, 11, "conducto_ok")
    await _marca(client, h_dra, pid, 11, "perno_defecto")
    assert await _activos(client, h_dra, pid, 11) == ["conducto_ok", "perno_defecto"]
    # el conducto puede estar bien y el perno mal; al cambiar el conducto el perno no se toca
    await _marca(client, h_dra, pid, 11, "conducto_defecto")
    assert await _activos(client, h_dra, pid, 11) == ["conducto_defecto", "perno_defecto"]


async def test_marca_nueva_repetida_es_409(client, h_dra):
    pid = await _paciente(client, h_dra)
    assert (await _marca(client, h_dra, pid, 22, "sellante")).status_code == 201
    assert (await _marca(client, h_dra, pid, 22, "sellante")).status_code == 409
