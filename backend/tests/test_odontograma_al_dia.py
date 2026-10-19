# Odontograma «al dia» (18/10/2026): GET /pacientes/{id}/odontograma?al=FECHA devuelve el odontograma tal
# como estaba el dia de una evaluacion o reevaluacion, reconstruido de las fechas de cada hallazgo.

from datetime import date, date as _date, timedelta as _timedelta

import pytest
import pytest_asyncio

from app import security
from app.enums import OrigenHallazgo, RolUsuario, SuperficieDental, TipoHallazgo
from app.models import OdontogramaHallazgo, Usuario

NAC_MENOR = (_date.today() - _timedelta(days=365 * 5)).isoformat()


@pytest_asyncio.fixture
async def dra(session_factory):
    async with session_factory() as s:
        u = Usuario(nombre="doctora", rol=RolUsuario.dra, password_hash="x", email="doctora@e.com")
        s.add(u)
        await s.commit()
        return u.id


@pytest.fixture
def h_dra(dra):
    return {"Authorization": f"Bearer {security.crear_access_token(dra, 'dra')}"}


async def _paciente(client, h):
    r = await client.post(
        "/pacientes",
        headers=h,
        json={"movil": "04141234567", "nombre_completo": "Paciente Prueba", "fecha_registro": "2026-10-05", "fecha_nacimiento": NAC_MENOR},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _hallazgo(session_factory, dra, paciente_id, diente, tipo, fecha, resuelto_fecha=None, superficie=None):
    import uuid

    async with session_factory() as s:
        s.add(
            OdontogramaHallazgo(
                paciente_id=uuid.UUID(paciente_id),
                numero_diente=diente,
                tipo_hallazgo=TipoHallazgo(tipo),
                superficie=SuperficieDental(superficie) if superficie else None,
                fecha=fecha,
                resuelto=resuelto_fecha is not None,
                resuelto_fecha=resuelto_fecha,
                origen=OrigenHallazgo.aqui,
                creado_por=dra,
            )
        )
        await s.commit()


async def test_sin_fecha_devuelve_solo_lo_vigente(client, h_dra, session_factory, dra):
    pid = await _paciente(client, h_dra)
    await _hallazgo(session_factory, dra, pid, 22, "caries", date(2026, 5, 2), superficie="oclusal")
    await _hallazgo(session_factory, dra, pid, 36, "caries", date(2026, 5, 2), date(2026, 7, 31), "oclusal")
    r = await client.get(f"/pacientes/{pid}/odontograma", headers=h_dra)
    assert [(h["numero_diente"], h["tipo_hallazgo"]) for h in r.json()] == [(22, "caries")]


async def test_al_dia_de_la_evaluacion_incluye_lo_que_luego_se_resolvio(client, h_dra, session_factory, dra):
    pid = await _paciente(client, h_dra)
    await _hallazgo(session_factory, dra, pid, 22, "caries", date(2026, 5, 2), superficie="oclusal")
    await _hallazgo(session_factory, dra, pid, 36, "caries", date(2026, 5, 2), date(2026, 7, 31), "oclusal")
    r = await client.get(f"/pacientes/{pid}/odontograma", headers=h_dra, params={"al": "2026-05-02"})
    assert sorted(h["numero_diente"] for h in r.json()) == [22, 36]


async def test_al_dia_no_incluye_lo_marcado_despues_ni_lo_resuelto_antes(client, h_dra, session_factory, dra):
    pid = await _paciente(client, h_dra)
    await _hallazgo(session_factory, dra, pid, 15, "caries", date(2026, 10, 18), superficie="mesial")   # despues
    await _hallazgo(session_factory, dra, pid, 36, "caries", date(2026, 5, 2), date(2026, 7, 31), "oclusal")
    await _hallazgo(session_factory, dra, pid, 46, "caries", date(2026, 1, 10), date(2026, 3, 1), "oclusal")  # ya resuelto
    r = await client.get(f"/pacientes/{pid}/odontograma", headers=h_dra, params={"al": "2026-05-02"})
    assert [h["numero_diente"] for h in r.json()] == [36]


async def test_un_hallazgo_resuelto_el_mismo_dia_ya_no_cuenta(client, h_dra, session_factory, dra):
    pid = await _paciente(client, h_dra)
    await _hallazgo(session_factory, dra, pid, 36, "caries", date(2026, 5, 2), date(2026, 5, 2), "oclusal")
    r = await client.get(f"/pacientes/{pid}/odontograma", headers=h_dra, params={"al": "2026-05-02"})
    assert r.json() == []


async def test_fecha_invalida(client, h_dra):
    pid = await _paciente(client, h_dra)
    r = await client.get(f"/pacientes/{pid}/odontograma", headers=h_dra, params={"al": "no-es-fecha"})
    assert r.status_code == 422
