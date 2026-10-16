# Enlazar a la visita lo cargado ese dia sin visita (procedimiento aparte, scripts/enlazar_visita.py).

from datetime import date, timedelta
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import select

from app import security
from app.enums import RolUsuario
from app.models import BitacoraTratamiento, OdontogramaHallazgo, Usuario
from app.services import enlazar_visita

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
        "/pacientes", headers=h,
        json={"movil": "04141234567", "nombre_completo": "Paciente de prueba", "fecha_registro": "2026-10-05",
              "fecha_nacimiento": NAC, "cedula": "V-12345678"},
    )
    return r.json()["id"]


async def _caries_y_restauracion(client, h, pid, diente, dia):
    await client.post(
        f"/pacientes/{pid}/dientes/{diente}/hallazgos", headers=h,
        json={"numero_diente": diente, "tipo_hallazgo": "caries", "superficie": "oclusal", "fecha": "2019-04-17"},
    )
    r = await client.post(
        f"/pacientes/{pid}/dientes/{diente}/tratamiento-realizado", headers=h,
        json={"numero_diente": diente, "tratamiento": "restauracion", "fecha": dia, "superficies": ["oclusal"]},
    )
    assert r.status_code == 201, r.text


async def test_enlaza_lo_suelto_del_dia_a_la_visita_de_ese_dia(client, h, session_factory):
    pid = await _paciente(client, h)
    await _caries_y_restauracion(client, h, pid, 26, "2019-04-23")
    await _caries_y_restauracion(client, h, pid, 16, "2019-04-23")
    visita = (await client.post(f"/pacientes/{pid}/visitas", headers=h, json={"fecha": "2019-04-23", "tipo": "otra"})).json()["id"]
    async with session_factory() as s:
        sueltos = await enlazar_visita.sueltos_del_dia(s, UUID(pid), date(2019, 4, 23))
        assert len(sueltos["bitacora"]) == 2 and len(sueltos["hallazgos"]) == 2  # las 2 obturaciones del dia
        hecho = await enlazar_visita.enlazar(s, UUID(pid), date(2019, 4, 23))
    assert (hecho["bitacora"], hecho["hallazgos"]) == (2, 2)
    entradas = (await client.get(f"/pacientes/{pid}/bitacora", headers=h)).json()
    assert [e["visita_id"] for e in entradas] == [visita, visita]
    async with session_factory() as s:
        # los hallazgos de otro dia (las caries del 17/04) no se tocan
        caries = (await s.execute(select(OdontogramaHallazgo).where(OdontogramaHallazgo.fecha == date(2019, 4, 17)))).scalars().all()
        assert caries and all(c.visita_id is None for c in caries)
        assert len((await s.execute(select(BitacoraTratamiento))).scalars().all()) == 2  # no borra nada


async def test_sin_visita_unica_no_enlaza(client, h, session_factory):
    pid = await _paciente(client, h)
    await _caries_y_restauracion(client, h, pid, 26, "2019-04-23")
    async with session_factory() as s:
        with pytest.raises(enlazar_visita.SinVisitaUnica):
            await enlazar_visita.enlazar(s, UUID(pid), date(2019, 4, 23))  # ninguna visita ese dia
    for _ in range(2):
        await client.post(f"/pacientes/{pid}/visitas", headers=h, json={"fecha": "2019-04-23"})
    async with session_factory() as s:
        with pytest.raises(enlazar_visita.SinVisitaUnica):
            await enlazar_visita.enlazar(s, UUID(pid), date(2019, 4, 23))  # dos visitas: ambiguo
