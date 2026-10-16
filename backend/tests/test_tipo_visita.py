# Flujo de visitas, fase 1 (14/10/2026): tipo de visita y vinculo con tratamientos.
# Especificacion: especificacion-tecnica-flujo-visitas-tratamientos.md.

from datetime import date as _date, timedelta as _timedelta

NAC_MENOR = (_date.today() - _timedelta(days=365 * 5)).isoformat()

import pytest_asyncio

from app import security
from app.enums import RolUsuario
from app.models import Usuario

import pytest


@pytest_asyncio.fixture
async def usuarios(session_factory):
    ids = {}
    async with session_factory() as s:
        for nombre, rol in (("doctora", RolUsuario.dra), ("asistente", RolUsuario.asistente)):
            u = Usuario(nombre=nombre, rol=rol, password_hash="x", email=f"{nombre}@e.com")
            s.add(u)
            await s.flush()
            ids[nombre] = u.id
        await s.commit()
    return ids


@pytest.fixture
def h_dra(usuarios):
    return {"Authorization": f"Bearer {security.crear_access_token(usuarios['doctora'], 'dra')}"}


@pytest.fixture
def h_asistente(usuarios):
    token = security.crear_access_token(usuarios["asistente"], "asistente")
    return {"Authorization": f"Bearer {token}"}


async def _paciente(client, h, nombre="Paciente Prueba"):
    r = await client.post(
        "/pacientes",
        headers=h,
        json={"movil": "04141234567", "nombre_completo": nombre, "fecha_registro": "2026-10-05", "fecha_nacimiento": NAC_MENOR},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _tratamiento(client, h, paciente_id, tipo="endodoncia"):
    prof = await client.post("/profesionales-tratantes", headers=h, json={"nombre": f"Dra. {tipo}"})
    r = await client.post(
        f"/pacientes/{paciente_id}/tratamientos",
        headers=h,
        json={"tipo": tipo, "fecha_inicio": "2026-09-01", "profesional_tratante_id": prof.json()["id"]},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _visita(client, h, pid, **extra):
    return await client.post(f"/pacientes/{pid}/visitas", headers=h, json={"fecha": "2026-10-10", **extra})


async def test_visita_con_tipo_evaluacion(client, h_dra):
    pid = await _paciente(client, h_dra)
    r = await _visita(client, h_dra, pid, tipo="evaluacion", motivo_consulta="Me duele el diente 22")
    assert r.status_code == 201, r.text
    assert (r.json()["tipo"], r.json()["tratamiento_ids"]) == ("evaluacion", [])


async def test_visita_sin_tipo_queda_en_null(client, h_dra):
    pid = await _paciente(client, h_dra)
    r = await _visita(client, h_dra, pid)
    assert r.status_code == 201 and r.json()["tipo"] is None


async def test_visita_de_tratamiento_no_exige_un_tratamiento_aparte(client, h_dra):
    # Procedimientos sueltos del odontograma (15/10/2026): una visita de tratamiento sin tratamiento vinculado.
    pid = await _paciente(client, h_dra)
    r = await _visita(client, h_dra, pid, tipo="tratamiento")
    assert r.status_code == 201, r.text
    assert (r.json()["tipo"], r.json()["tratamiento_ids"]) == ("tratamiento", [])


async def test_visita_de_tratamiento_vincula_y_se_lee(client, h_dra):
    pid = await _paciente(client, h_dra)
    t1 = await _tratamiento(client, h_dra, pid, "endodoncia")
    t2 = await _tratamiento(client, h_dra, pid, "prótesis")
    r = await _visita(client, h_dra, pid, tipo="tratamiento", tratamiento_ids=[t1, t2, t1])
    assert r.status_code == 201, r.text
    assert sorted(r.json()["tratamiento_ids"]) == sorted([t1, t2])  # sin repetidos
    vid = r.json()["id"]
    detalle = (await client.get(f"/visitas/{vid}", headers=h_dra)).json()
    assert sorted(detalle["tratamiento_ids"]) == sorted([t1, t2])
    lista = (await client.get(f"/pacientes/{pid}/visitas", headers=h_dra)).json()
    assert [sorted(v["tratamiento_ids"]) for v in lista] == [sorted([t1, t2])]


async def test_tratamiento_de_otro_paciente_es_422(client, h_dra):
    a = await _paciente(client, h_dra, "A")
    b = await _paciente(client, h_dra, "B")
    ajeno = await _tratamiento(client, h_dra, b)
    r = await _visita(client, h_dra, a, tipo="tratamiento", tratamiento_ids=[ajeno])
    assert r.status_code == 422
    assert "no es de este paciente" in r.json()["detail"]


async def test_control_puede_vincular_un_tratamiento(client, h_dra):
    pid = await _paciente(client, h_dra)
    t = await _tratamiento(client, h_dra, pid, "restauración")
    r = await _visita(client, h_dra, pid, tipo="control_limpieza", tratamiento_ids=[t])
    assert r.status_code == 201 and r.json()["tratamiento_ids"] == [t]


async def test_asistente_no_manda_tipo_ni_tratamientos(client, h_asistente, h_dra):
    pid = await _paciente(client, h_asistente)
    t = await _tratamiento(client, h_dra, pid)
    assert (await _visita(client, h_asistente, pid, tipo="evaluacion")).status_code == 422
    assert (await _visita(client, h_asistente, pid, tratamiento_ids=[t])).status_code == 422
    r = await _visita(client, h_asistente, pid, motivo_consulta="Dolor")
    assert r.status_code == 201 and r.json()["tipo"] is None


async def test_dra_clasifica_despues_con_patch(client, h_dra, h_asistente):
    pid = await _paciente(client, h_asistente)
    vid = (await _visita(client, h_asistente, pid, motivo_consulta="Limpieza")).json()["id"]
    r = await client.patch(f"/visitas/{vid}", headers=h_dra, json={"tipo": "control_limpieza"})
    assert r.status_code == 200 and r.json()["tipo"] == "control_limpieza"
    # volver a "sin clasificar" esta permitido
    r = await client.patch(f"/visitas/{vid}", headers=h_dra, json={"tipo": None})
    assert r.status_code == 200 and r.json()["tipo"] is None


async def test_patch_reemplaza_tratamientos_y_valida(client, h_dra):
    pid = await _paciente(client, h_dra)
    t1 = await _tratamiento(client, h_dra, pid, "endodoncia")
    t2 = await _tratamiento(client, h_dra, pid, "corona")
    vid = (await _visita(client, h_dra, pid, tipo="tratamiento", tratamiento_ids=[t1])).json()["id"]
    r = await client.patch(f"/visitas/{vid}", headers=h_dra, json={"tratamiento_ids": [t2]})
    assert r.status_code == 200 and r.json()["tratamiento_ids"] == [t2]
    # una visita de tratamiento puede quedar sin tratamiento vinculado (procedimientos sueltos del odontograma)
    r = await client.patch(f"/visitas/{vid}", headers=h_dra, json={"tratamiento_ids": []})
    assert r.status_code == 200 and r.json()["tratamiento_ids"] == []
    otra = (await _visita(client, h_dra, pid, tipo="evaluacion")).json()["id"]
    r = await client.patch(f"/visitas/{otra}", headers=h_dra, json={"tipo": "tratamiento"})
    assert r.status_code == 200 and r.json()["tipo"] == "tratamiento"
    r = await client.patch(f"/visitas/{vid}", headers=h_dra, json={"tratamiento_ids": [t2]})
    assert r.status_code == 200
    # editar solo el examen no toca el vinculo
    r = await client.patch(f"/visitas/{vid}", headers=h_dra, json={"hallazgos": "sin novedad"})
    assert r.status_code == 200 and r.json()["tratamiento_ids"] == [t2]
