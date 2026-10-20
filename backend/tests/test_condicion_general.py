# Gingivitis general (19/10/2026, migracion 0037): una condicion de toda la boca, no de un diente.
# Se marca una vez por paciente; en pantalla son dos botones (naranja / rojo) y en el papel no se agrega nada.

from datetime import date, date as _date, timedelta as _timedelta

import pytest
import pytest_asyncio

from app import security
from app.enums import RolUsuario
from app.models import Usuario

NAC_MENOR = (_date.today() - _timedelta(days=365 * 5)).isoformat()


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
    return {"Authorization": f"Bearer {security.crear_access_token(usuarios['asistente'], 'asistente')}"}


async def _paciente(client, h, nombre="Paciente Prueba"):
    r = await client.post(
        "/pacientes",
        headers=h,
        json={"movil": "04141234567", "nombre_completo": nombre, "fecha_registro": "2026-10-05", "fecha_nacimiento": NAC_MENOR},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _marcar(client, h, pid, fecha="2026-05-02", **extra):
    return await client.post(
        f"/pacientes/{pid}/condiciones-generales", headers=h, json={"tipo": "gingivitis", "fecha": fecha, **extra}
    )


async def test_marcar_gingivitis_general_y_listarla(client, h_dra):
    pid = await _paciente(client, h_dra)
    r = await _marcar(client, h_dra, pid)
    assert r.status_code == 201, r.text
    assert r.json()["tipo"] == "gingivitis" and r.json()["resuelto"] is False
    lista = (await client.get(f"/pacientes/{pid}/condiciones-generales", headers=h_dra)).json()
    assert [c["tipo"] for c in lista] == ["gingivitis"]


async def test_no_se_marca_dos_veces_la_misma_condicion(client, h_dra):
    pid = await _paciente(client, h_dra)
    await _marcar(client, h_dra, pid)
    assert (await _marcar(client, h_dra, pid, fecha="2026-06-01")).status_code == 409


async def test_gingivitis_y_periodontitis_general_son_independientes(client, h_dra):
    pid = await _paciente(client, h_dra)
    assert (await _marcar(client, h_dra, pid)).status_code == 201
    r = await client.post(
        f"/pacientes/{pid}/condiciones-generales", headers=h_dra, json={"tipo": "periodontitis", "fecha": "2026-05-02"}
    )
    assert r.status_code == 201, r.text
    lista = (await client.get(f"/pacientes/{pid}/condiciones-generales", headers=h_dra)).json()
    assert sorted(c["tipo"] for c in lista) == ["gingivitis", "periodontitis"]


async def test_resolverla_y_volver_a_marcarla(client, h_dra):
    pid = await _paciente(client, h_dra)
    cid = (await _marcar(client, h_dra, pid)).json()["id"]
    r = await client.patch(
        f"/pacientes/{pid}/condiciones-generales/{cid}/resolver", headers=h_dra, json={"fecha": "2026-07-31"}
    )
    assert r.status_code == 200 and r.json()["resuelto"] is True and r.json()["resuelto_fecha"] == "2026-07-31"
    assert (await client.get(f"/pacientes/{pid}/condiciones-generales", headers=h_dra)).json() == []
    assert (await _marcar(client, h_dra, pid, fecha="2026-09-01")).status_code == 201   # puede volver a aparecer


async def test_resolver_con_fecha_anterior_o_dos_veces(client, h_dra):
    pid = await _paciente(client, h_dra)
    cid = (await _marcar(client, h_dra, pid, fecha="2026-05-02")).json()["id"]
    url = f"/pacientes/{pid}/condiciones-generales/{cid}/resolver"
    assert (await client.patch(url, headers=h_dra, json={"fecha": "2026-04-01"})).status_code == 422
    assert (await client.patch(url, headers=h_dra, json={"fecha": "2026-07-31"})).status_code == 200
    assert (await client.patch(url, headers=h_dra, json={"fecha": "2026-08-01"})).status_code == 409


async def test_al_dia_de_una_evaluacion(client, h_dra):
    pid = await _paciente(client, h_dra)
    cid = (await _marcar(client, h_dra, pid, fecha="2026-05-02")).json()["id"]
    await client.patch(
        f"/pacientes/{pid}/condiciones-generales/{cid}/resolver", headers=h_dra, json={"fecha": "2026-07-31"}
    )
    def ver(al):
        return client.get(f"/pacientes/{pid}/condiciones-generales", headers=h_dra, params={"al": al})
    assert len((await ver("2026-05-02")).json()) == 1      # el dia que se marco
    assert len((await ver("2026-06-15")).json()) == 1      # aun vigente
    assert (await ver("2026-07-31")).json() == []           # resuelta ese dia
    assert (await ver("2026-04-01")).json() == []           # antes de marcarse


async def test_visita_de_otro_paciente_y_solo_la_dra(client, h_dra, h_asistente):
    a = await _paciente(client, h_dra, "Paciente A")
    b = await _paciente(client, h_dra, "Paciente B")
    v = await client.post(f"/pacientes/{a}/visitas", headers=h_dra, json={"fecha": "2026-05-02", "motivo_consulta": "Evaluación"})
    assert (await _marcar(client, h_dra, b, visita_id=v.json()["id"])).status_code == 422
    assert (await _marcar(client, h_asistente, b)).status_code == 403
    assert (await client.get(f"/pacientes/{b}/condiciones-generales", headers=h_asistente)).status_code == 403
