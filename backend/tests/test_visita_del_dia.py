# Lo realizado en un dia queda dentro de la visita de ese dia (15/10/2026): «Tratamiento realizado» y
# hallazgos enlazados a la visita; la visita de tratamiento no exige un tratamiento aparte.

from datetime import date, timedelta

import pytest_asyncio

from app import security
from app.enums import RolUsuario
from app.models import Usuario

NAC = (date.today() - timedelta(days=365 * 30)).isoformat()


@pytest_asyncio.fixture
async def h(session_factory):
    async with session_factory() as s:
        u = Usuario(nombre="doctora", rol=RolUsuario.dra, password_hash="x", email="d@e.com")
        s.add(u)
        await s.commit()
        uid = u.id
    return {"Authorization": f"Bearer {security.crear_access_token(uid, 'dra')}"}


async def _paciente(client, h):
    r = await client.post(
        "/pacientes",
        headers=h,
        json={"movil": "04141234567", "nombre_completo": "Paciente de prueba", "fecha_registro": "2026-10-05",
              "fecha_nacimiento": NAC, "cedula": "V-12345678"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_varios_procedimientos_de_un_dia_quedan_en_la_misma_visita(client, h):
    pid = await _paciente(client, h)
    for diente in (26, 16):
        await client.post(
            f"/pacientes/{pid}/dientes/{diente}/hallazgos", headers=h,
            json={"numero_diente": diente, "tipo_hallazgo": "caries", "superficie": "oclusal", "fecha": "2026-10-01"},
        )
    visita = (
        await client.post(f"/pacientes/{pid}/visitas", headers=h, json={"fecha": "2026-10-10", "tipo": "tratamiento"})
    ).json()["id"]
    for diente in (26, 16):
        r = await client.post(
            f"/pacientes/{pid}/dientes/{diente}/tratamiento-realizado", headers=h,
            json={"numero_diente": diente, "tratamiento": "restauracion", "fecha": "2026-10-10",
                  "superficies": ["oclusal"], "visita_id": visita},
        )
        assert r.status_code == 201, r.text
    entradas = (await client.get(f"/pacientes/{pid}/bitacora", headers=h)).json()
    assert sorted(e["visita_id"] for e in entradas) == [visita, visita]
    assert sorted(d for e in entradas for d in e["dientes"]) == [16, 26]


async def test_hallazgo_nuevo_con_la_visita_del_dia(client, h):
    pid = await _paciente(client, h)
    visita = (await client.post(f"/pacientes/{pid}/visitas", headers=h, json={"fecha": "2026-10-10"})).json()["id"]
    r = await client.post(
        f"/pacientes/{pid}/dientes/14/hallazgos", headers=h,
        json={"numero_diente": 14, "tipo_hallazgo": "caries", "superficie": "mesial", "fecha": "2026-10-10",
              "visita_id": visita},
    )
    assert r.status_code == 201 and r.json()["visita_id"] == visita
