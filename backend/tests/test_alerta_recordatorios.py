# Migracion 0035 (17/10/2026): alerta, seguimiento periodontal, activo, recordatorios,
# enlace del examen y tipo de visita «reevaluacion».
# Especificacion: docs/proceso-trabajo-caso-334.md, secciones 11 y 12.

from datetime import date as _date, timedelta as _timedelta

NAC_MENOR = (_date.today() - _timedelta(days=365 * 5)).isoformat()

import pytest
import pytest_asyncio

from app import security
from app.enums import RolUsuario
from app.models import Usuario


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


async def test_paciente_nuevo_nace_sin_alerta_y_activo(client, h_dra):
    pid = await _paciente(client, h_dra)
    p = (await client.get(f"/pacientes/{pid}", headers=h_dra)).json()
    assert p["alerta"] is False and p["alerta_texto"] is None
    assert p["seguimiento_periodontal"] is False
    assert p["activo"] is True and p["motivo_inactivo"] is None


async def test_dra_marca_alerta_y_queda_en_el_historial(client, h_dra):
    pid = await _paciente(client, h_dra)
    r = await client.patch(
        f"/pacientes/{pid}", headers=h_dra, json={"alerta": True, "alerta_texto": "  Marcapasos: profilaxis previa "}
    )
    assert r.status_code == 200, r.text
    assert r.json()["alerta"] is True
    assert r.json()["alerta_texto"] == "Marcapasos: profilaxis previa"
    cambios = (await client.get(f"/pacientes/{pid}/cambios", headers=h_dra)).json()
    assert {c["etiqueta"] for c in cambios} == {"Alerta médica", "Detalle de la alerta"}


async def test_la_asistente_no_toca_alerta_ni_periodontal_ni_baja(client, h_dra, h_asistente):
    pid = await _paciente(client, h_dra)
    for cuerpo in ({"alerta": True}, {"seguimiento_periodontal": True}, {"activo": False}):
        r = await client.patch(f"/pacientes/{pid}", headers=h_asistente, json=cuerpo)
        assert r.status_code == 403, (cuerpo, r.text)


async def test_baja_con_motivo(client, h_dra):
    pid = await _paciente(client, h_dra)
    r = await client.patch(
        f"/pacientes/{pid}", headers=h_dra, json={"activo": False, "motivo_inactivo": "Cambió de odontólogo"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["activo"] is False and r.json()["motivo_inactivo"] == "Cambió de odontólogo"


async def test_las_casillas_no_aceptan_null(client, h_dra):
    pid = await _paciente(client, h_dra)
    r = await client.patch(f"/pacientes/{pid}", headers=h_dra, json={"alerta": None})
    assert r.status_code == 422


async def test_recordatorio_crear_listar_y_marcar_hecho(client, h_dra):
    pid = await _paciente(client, h_dra)
    r = await client.post(
        f"/pacientes/{pid}/recordatorios", headers=h_dra, json={"texto": "  Rx panorámica ", "fecha": "2026-12-01"}
    )
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert r.json()["texto"] == "Rx panorámica" and r.json()["hecho"] is False

    r = await client.patch(f"/recordatorios/{rid}", headers=h_dra, json={"hecho": True})
    assert r.status_code == 200 and r.json()["hecho"] is True and r.json()["hecho_fecha"] == _date.today().isoformat()

    r = await client.patch(f"/recordatorios/{rid}", headers=h_dra, json={"hecho": False})
    assert r.json()["hecho"] is False and r.json()["hecho_fecha"] is None

    lista = (await client.get(f"/pacientes/{pid}/recordatorios", headers=h_dra)).json()
    assert [x["id"] for x in lista] == [rid]


async def test_recordatorio_texto_vacio_y_patch_vacio(client, h_dra):
    pid = await _paciente(client, h_dra)
    r = await client.post(f"/pacientes/{pid}/recordatorios", headers=h_dra, json={"texto": "   ", "fecha": "2026-12-01"})
    assert r.status_code == 422
    r = await client.post(f"/pacientes/{pid}/recordatorios", headers=h_dra, json={"texto": "x", "fecha": "2026-12-01"})
    rid = r.json()["id"]
    assert (await client.patch(f"/recordatorios/{rid}", headers=h_dra, json={})).status_code == 422
    assert (await client.patch(f"/recordatorios/{rid}", headers=h_dra, json={"fecha": None})).status_code == 422


async def test_vencidos_solo_pendientes_y_pacientes_activos(client, h_dra):
    activo = await _paciente(client, h_dra, "Paciente Activo")
    baja = await _paciente(client, h_dra, "Paciente De Baja")
    for pid, fecha in ((activo, "2026-01-10"), (activo, "2099-01-10"), (baja, "2026-01-10")):
        await client.post(f"/pacientes/{pid}/recordatorios", headers=h_dra, json={"texto": "Control", "fecha": fecha})
    hecho = (
        await client.post(f"/pacientes/{activo}/recordatorios", headers=h_dra, json={"texto": "Hecho", "fecha": "2026-01-05"})
    ).json()["id"]
    await client.patch(f"/recordatorios/{hecho}", headers=h_dra, json={"hecho": True})
    await client.patch(f"/pacientes/{baja}", headers=h_dra, json={"activo": False})

    vencidos = (await client.get("/recordatorios/vencidos", headers=h_dra)).json()
    assert [(v["paciente_id"], v["fecha"]) for v in vencidos] == [(activo, "2026-01-10")]


async def test_recordatorios_son_solo_de_la_dra(client, h_dra, h_asistente):
    pid = await _paciente(client, h_dra)
    r = await client.post(f"/pacientes/{pid}/recordatorios", headers=h_asistente, json={"texto": "x", "fecha": "2026-12-01"})
    assert r.status_code == 403
    assert (await client.get("/recordatorios/vencidos", headers=h_asistente)).status_code == 403


async def test_recordatorio_con_visita_de_otro_paciente(client, h_dra):
    a = await _paciente(client, h_dra, "Paciente A")
    b = await _paciente(client, h_dra, "Paciente B")
    v = await client.post(f"/pacientes/{a}/visitas", headers=h_dra, json={"fecha": "2026-10-10", "motivo_consulta": "Control"})
    assert v.status_code == 201, v.text
    r = await client.post(
        f"/pacientes/{b}/recordatorios",
        headers=h_dra,
        json={"texto": "x", "fecha": "2026-12-01", "visita_id": v.json()["id"]},
    )
    assert r.status_code == 422


async def test_examen_guarda_el_enlace(client, h_dra):
    pid = await _paciente(client, h_dra)
    r = await client.post(
        f"/pacientes/{pid}/examenes",
        headers=h_dra,
        json={"tipo": "rx_panoramica", "fecha_indicacion": "2026-10-10", "enlace": "  https://drive.example/rx  "},
    )
    assert r.status_code == 201, r.text
    assert r.json()["enlace"] == "https://drive.example/rx"
    eid = r.json()["id"]
    r = await client.patch(f"/examenes/{eid}", headers=h_dra, json={"enlace": "https://drive.example/nuevo"})
    assert r.status_code == 200 and r.json()["enlace"] == "https://drive.example/nuevo"


async def test_visita_tipo_reevaluacion(client, h_dra):
    pid = await _paciente(client, h_dra)
    r = await client.post(
        f"/pacientes/{pid}/visitas",
        headers=h_dra,
        json={"fecha": "2026-10-10", "motivo_consulta": "Reevaluación", "tipo": "reevaluacion"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["tipo"] == "reevaluacion"
