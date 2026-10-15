# Flujo de visitas, fase 2 (15/10/2026): accion «Tratamiento realizado».
# Especificacion: especificacion-tecnica-flujo-visitas-tratamientos.md, seccion 5.

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


async def _paciente(client, h):
    r = await client.post(
        "/pacientes",
        headers=h,
        json={"movil": "04141234567", "nombre_completo": "Paciente Prueba", "fecha_registro": "2026-10-05", "fecha_nacimiento": NAC_MENOR},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _marca(client, h, pid, diente, tipo, superficie=None, fecha="2026-10-01"):
    r = await client.post(
        f"/pacientes/{pid}/dientes/{diente}/hallazgos",
        headers=h,
        json={"numero_diente": diente, "tipo_hallazgo": tipo, "superficie": superficie, "fecha": fecha},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _hecho(client, h, pid, diente, tratamiento, fecha="2026-10-10", **extra):
    return await client.post(
        f"/pacientes/{pid}/dientes/{diente}/tratamiento-realizado",
        headers=h,
        json={"numero_diente": diente, "tratamiento": tratamiento, "fecha": fecha, **extra},
    )


async def _activos(client, h, pid, diente):
    r = await client.get(f"/pacientes/{pid}/odontograma", headers=h)
    return sorted(
        (x["tipo_hallazgo"], x["superficie"]) for x in r.json() if x["numero_diente"] == diente
    )


async def test_restauracion_cierra_la_caries_y_abre_la_obturacion(client, h_dra):
    pid = await _paciente(client, h_dra)
    caries = await _marca(client, h_dra, pid, 22, "caries", "palatino_lingual")
    r = await _hecho(client, h_dra, pid, 22, "restauracion", superficies=["palatino_lingual"])
    assert r.status_code == 201, r.text
    cuerpo = r.json()
    assert [c["id"] for c in cuerpo["cerrados"]] == [caries["id"]]
    assert cuerpo["cerrados"][0]["resuelto"] and cuerpo["cerrados"][0]["resuelto_fecha"] == "2026-10-10"
    assert [(a["tipo_hallazgo"], a["superficie"]) for a in cuerpo["abiertos"]] == [("obturacion_ok", "palatino_lingual")]
    assert cuerpo["cerrados"][0]["resuelto_por_hallazgo_id"] == cuerpo["abiertos"][0]["id"]
    assert await _activos(client, h_dra, pid, 22) == [("obturacion_ok", "palatino_lingual")]


async def test_restauracion_solo_cierra_las_superficies_elegidas(client, h_dra):
    pid = await _paciente(client, h_dra)
    await _marca(client, h_dra, pid, 36, "caries", "oclusal")
    await _marca(client, h_dra, pid, 36, "caries", "mesial")
    r = await _hecho(client, h_dra, pid, 36, "restauracion", superficies=["oclusal"])
    assert r.status_code == 201
    assert await _activos(client, h_dra, pid, 36) == [("caries", "mesial"), ("obturacion_ok", "oclusal")]


async def test_restauracion_pide_superficie_y_obturacion_con_defecto_se_cierra(client, h_dra):
    pid = await _paciente(client, h_dra)
    await _marca(client, h_dra, pid, 24, "obturacion_defecto", "cervical")
    assert (await _hecho(client, h_dra, pid, 24, "restauracion")).status_code == 422
    r = await _hecho(client, h_dra, pid, 24, "cambio_restauracion", superficies=["cervical"])
    assert r.status_code == 201
    assert await _activos(client, h_dra, pid, 24) == [("obturacion_ok", "cervical")]


async def test_endodoncia_y_perno_se_manejan_por_separado(client, h_dra):
    pid = await _paciente(client, h_dra)
    await _marca(client, h_dra, pid, 11, "conducto_indicado")
    await _marca(client, h_dra, pid, 11, "perno_defecto")
    assert (await _hecho(client, h_dra, pid, 11, "endodoncia")).status_code == 201
    assert await _activos(client, h_dra, pid, 11) == [("conducto_ok", None), ("perno_defecto", None)]
    assert (await _hecho(client, h_dra, pid, 11, "perno")).status_code == 201
    assert await _activos(client, h_dra, pid, 11) == [("conducto_ok", None), ("perno_ok", None)]


async def test_extraccion_deja_ausente_y_conserva_las_condiciones(client, h_dra):
    pid = await _paciente(client, h_dra)
    await _marca(client, h_dra, pid, 18, "caries", "oclusal")
    await _marca(client, h_dra, pid, 18, "cambio_coloracion")
    assert (await _hecho(client, h_dra, pid, 18, "extraccion")).status_code == 201
    assert await _activos(client, h_dra, pid, 18) == [("ausente", None), ("cambio_coloracion", None)]


async def test_carilla_exige_resultado_y_la_dra_lo_elige(client, h_dra):
    pid = await _paciente(client, h_dra)
    await _marca(client, h_dra, pid, 12, "caries", "vestibular")
    assert (await _hecho(client, h_dra, pid, 12, "carilla")).status_code == 422
    assert (await _hecho(client, h_dra, pid, 12, "carilla", resultado="obturacion_ok")).status_code == 422
    r = await _hecho(client, h_dra, pid, 12, "carilla", resultado="corona_ok")
    assert r.status_code == 201
    assert await _activos(client, h_dra, pid, 12) == [("corona_ok", None)]
    pid2 = await _paciente(client, h_dra)
    r = await _hecho(client, h_dra, pid2, 21, "carilla", resultado="carilla_ok")
    assert [(a["tipo_hallazgo"], a["superficie"]) for a in r.json()["abiertos"]] == [("carilla_ok", "vestibular")]


async def test_implante_cierra_ausente_y_exodoncia_indicada(client, h_dra):
    pid = await _paciente(client, h_dra)
    await _marca(client, h_dra, pid, 46, "ausente")
    await _marca(client, h_dra, pid, 46, "exodoncia_simple")
    assert (await _hecho(client, h_dra, pid, 46, "implante")).status_code == 201
    assert await _activos(client, h_dra, pid, 46) == [("implante", None)]


async def test_sellante_cierra_spp(client, h_dra):
    pid = await _paciente(client, h_dra)
    await _marca(client, h_dra, pid, 16, "spp")
    assert (await _hecho(client, h_dra, pid, 16, "sellante")).status_code == 201
    assert await _activos(client, h_dra, pid, 16) == [("sellante", None)]


async def test_diastema_se_quita_y_se_marca_resina_carilla_u_ortodoncia(client, h_dra):
    pid = await _paciente(client, h_dra)
    await _marca(client, h_dra, pid, 11, "diastema", "mesial")
    assert (await _hecho(client, h_dra, pid, 11, "diastema_resina", superficies=["oclusal"])).status_code == 422
    r = await _hecho(client, h_dra, pid, 11, "diastema_resina", superficies=["mesial"])
    assert r.status_code == 201
    assert await _activos(client, h_dra, pid, 11) == [("obturacion_ok", "mesial")]
    await _marca(client, h_dra, pid, 21, "diastema", "mesial")
    r = await _hecho(client, h_dra, pid, 21, "diastema_ortodoncia")
    assert r.status_code == 201 and r.json()["abiertos"] == [] and len(r.json()["cerrados"]) == 1
    assert await _activos(client, h_dra, pid, 21) == []


async def test_deja_una_entrada_en_la_bitacora(client, h_dra):
    pid = await _paciente(client, h_dra)
    await _marca(client, h_dra, pid, 22, "caries", "oclusal")
    r = await _hecho(client, h_dra, pid, 22, "restauracion", superficies=["oclusal"], descripcion="Resina A2")
    assert r.status_code == 201
    entradas = (await client.get(f"/pacientes/{pid}/bitacora", headers=h_dra)).json()
    assert len(entradas) == 1 and entradas[0]["descripcion"] == "Resina A2" and entradas[0]["dientes"] == [22]
    assert entradas[0]["id"] == r.json()["bitacora_id"]


async def test_descripcion_automatica_si_no_se_escribe(client, h_dra):
    pid = await _paciente(client, h_dra)
    await _marca(client, h_dra, pid, 22, "caries", "oclusal")
    await _hecho(client, h_dra, pid, 22, "restauracion", superficies=["oclusal"])
    entradas = (await client.get(f"/pacientes/{pid}/bitacora", headers=h_dra)).json()
    assert "Restauración (resina), diente 22" in entradas[0]["descripcion"]


async def test_fecha_anterior_al_hallazgo_es_422_y_no_cambia_nada(client, h_dra):
    pid = await _paciente(client, h_dra)
    await _marca(client, h_dra, pid, 22, "caries", "oclusal", fecha="2026-10-05")
    r = await _hecho(client, h_dra, pid, 22, "restauracion", fecha="2026-10-01", superficies=["oclusal"])
    assert r.status_code == 422
    assert await _activos(client, h_dra, pid, 22) == [("caries", "oclusal")]
    assert (await client.get(f"/pacientes/{pid}/bitacora", headers=h_dra)).json() == []


async def test_cierre_explicito_manda_sobre_el_propuesto(client, h_dra):
    pid = await _paciente(client, h_dra)
    caries = await _marca(client, h_dra, pid, 22, "caries", "oclusal")
    r = await _hecho(client, h_dra, pid, 22, "restauracion", superficies=["oclusal"], cierra_ids=[])
    assert r.status_code == 201 and r.json()["cerrados"] == []
    assert await _activos(client, h_dra, pid, 22) == [("caries", "oclusal"), ("obturacion_ok", "oclusal")]
    # un hallazgo de otro diente no se puede cerrar
    otra = await _marca(client, h_dra, pid, 23, "caries", "mesial")
    r = await _hecho(client, h_dra, pid, 22, "corona", cierra_ids=[otra["id"]])
    assert r.status_code == 422
    assert caries["id"]


async def test_restauracion_sin_hallazgo_previo_se_registra_igual(client, h_dra):
    """Carga historica: el odontograma inicial no existe y la obturacion igual se anota."""
    pid = await _paciente(client, h_dra)
    r = await _hecho(client, h_dra, pid, 23, "restauracion", superficies=["cervical"])
    assert r.status_code == 201 and r.json()["cerrados"] == []
    assert await _activos(client, h_dra, pid, 23) == [("obturacion_ok", "cervical")]


async def test_la_asistente_no_puede_y_el_catalogo_lista_las_reglas(client, h_dra, h_asistente):
    pid = await _paciente(client, h_dra)
    assert (await _hecho(client, h_asistente, pid, 22, "sellante")).status_code == 403
    catalogo = (await client.get("/tratamientos-realizados", headers=h_dra)).json()
    assert [c["codigo"] for c in catalogo][:3] == ["restauracion", "cambio_restauracion", "endodoncia"]
    assert len(catalogo) == 12
    carilla = next(c for c in catalogo if c["codigo"] == "carilla")
    assert carilla["resultados"] == ["carilla_ok", "corona_ok", "ausente"]
