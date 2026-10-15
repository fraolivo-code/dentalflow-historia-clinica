# Flujo de visitas, fase 3 (15/10/2026): examenes solicitados (indicado -> traido).
# Especificacion: especificacion-tecnica-flujo-visitas-tratamientos.md, seccion 7.

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


async def _indicar(client, h, pid, tipo="tomografia", fecha="2026-10-10", **extra):
    return await client.post(
        f"/pacientes/{pid}/examenes", headers=h, json={"tipo": tipo, "fecha_indicacion": fecha, **extra}
    )


async def test_indicar_deja_el_examen_pendiente(client, h_dra):
    pid = await _paciente(client, h_dra)
    r = await _indicar(client, h_dra, pid, "rx_periapical", descripcion="  diente 22 ")
    assert r.status_code == 201, r.text
    e = r.json()
    assert (e["estado"], e["tipo"], e["descripcion"], e["fecha_traido"], e["hallazgos"]) == (
        "indicado", "rx_periapical", "diente 22", None, None,
    )


async def test_tipo_otro_exige_decir_cual(client, h_dra):
    pid = await _paciente(client, h_dra)
    assert (await _indicar(client, h_dra, pid, "otro")).status_code == 422
    assert (await _indicar(client, h_dra, pid, "otro", descripcion="Cefalometría")).status_code == 201


async def test_registrar_que_lo_trajo_con_hallazgos(client, h_dra):
    pid = await _paciente(client, h_dra)
    eid = (await _indicar(client, h_dra, pid)).json()["id"]
    r = await client.patch(
        f"/examenes/{eid}/traido", headers=h_dra, json={"fecha_traido": "2026-10-14", "hallazgos": "Lesión periapical en 22"}
    )
    assert r.status_code == 200, r.text
    e = r.json()
    assert (e["estado"], e["fecha_traido"], e["hallazgos"]) == ("traido", "2026-10-14", "Lesión periapical en 22")
    # no se puede registrar dos veces
    assert (await client.patch(f"/examenes/{eid}/traido", headers=h_dra, json={"fecha_traido": "2026-10-15"})).status_code == 409


async def test_trajo_sin_hallazgos_y_no_antes_de_la_indicacion(client, h_dra):
    pid = await _paciente(client, h_dra)
    eid = (await _indicar(client, h_dra, pid, fecha="2026-10-10")).json()["id"]
    r = await client.patch(f"/examenes/{eid}/traido", headers=h_dra, json={"fecha_traido": "2026-10-09"})
    assert r.status_code == 422
    r = await client.patch(f"/examenes/{eid}/traido", headers=h_dra, json={"fecha_traido": "2026-10-10", "hallazgos": "  "})
    assert r.status_code == 200 and r.json()["hallazgos"] is None


async def test_lista_con_pendientes_primero_y_mas_reciente_primero(client, h_dra):
    pid = await _paciente(client, h_dra)
    viejo = (await _indicar(client, h_dra, pid, "rx_panoramica", fecha="2026-09-01")).json()["id"]
    nuevo = (await _indicar(client, h_dra, pid, "tomografia", fecha="2026-10-12")).json()["id"]
    traido = (await _indicar(client, h_dra, pid, "rx_periapical", fecha="2026-10-13")).json()["id"]
    await client.patch(f"/examenes/{traido}/traido", headers=h_dra, json={"fecha_traido": "2026-10-14"})
    ids = [e["id"] for e in (await client.get(f"/pacientes/{pid}/examenes", headers=h_dra)).json()]
    assert ids == [nuevo, viejo, traido]


async def test_vincula_visita_y_tratamiento_del_mismo_paciente(client, h_dra):
    pid = await _paciente(client, h_dra)
    otro = await _paciente(client, h_dra, "Otro")
    visita = (await client.post(f"/pacientes/{pid}/visitas", headers=h_dra, json={"fecha": "2026-10-10"})).json()["id"]
    visita_ajena = (await client.post(f"/pacientes/{otro}/visitas", headers=h_dra, json={"fecha": "2026-10-10"})).json()["id"]
    assert (await _indicar(client, h_dra, pid, visita_id=visita)).json()["visita_id"] == visita
    r = await _indicar(client, h_dra, pid, visita_id=visita_ajena)
    assert r.status_code == 422 and "no es de este paciente" in r.json()["detail"]
    prof = await client.post("/profesionales-tratantes", headers=h_dra, json={"nombre": "Dra. X"})
    trat_ajeno = (
        await client.post(
            f"/pacientes/{otro}/tratamientos",
            headers=h_dra,
            json={"tipo": "implante", "fecha_inicio": "2026-09-01", "profesional_tratante_id": prof.json()["id"]},
        )
    ).json()["id"]
    assert (await _indicar(client, h_dra, pid, tratamiento_id=trat_ajeno)).status_code == 422


async def test_corregir_texto_y_hallazgos_solo_si_ya_lo_trajo(client, h_dra):
    pid = await _paciente(client, h_dra)
    eid = (await _indicar(client, h_dra, pid, descripcion="mal escrito")).json()["id"]
    r = await client.patch(f"/examenes/{eid}", headers=h_dra, json={"descripcion": "diente 22"})
    assert r.status_code == 200 and r.json()["descripcion"] == "diente 22"
    assert (await client.patch(f"/examenes/{eid}", headers=h_dra, json={"hallazgos": "x"})).status_code == 409
    assert (await client.patch(f"/examenes/{eid}", headers=h_dra, json={})).status_code == 422
    await client.patch(f"/examenes/{eid}/traido", headers=h_dra, json={"fecha_traido": "2026-10-12"})
    r = await client.patch(f"/examenes/{eid}", headers=h_dra, json={"hallazgos": "Sin lesión"})
    assert r.status_code == 200 and r.json()["hallazgos"] == "Sin lesión"


async def test_la_asistente_no_ve_ni_indica_examenes_y_paciente_inexistente_es_404(client, h_dra, h_asistente):
    pid = await _paciente(client, h_dra)
    assert (await _indicar(client, h_asistente, pid)).status_code == 403
    assert (await client.get(f"/pacientes/{pid}/examenes", headers=h_asistente)).status_code == 403
    assert (await client.get("/pacientes/00000000-0000-0000-0000-000000000000/examenes", headers=h_dra)).status_code == 404
