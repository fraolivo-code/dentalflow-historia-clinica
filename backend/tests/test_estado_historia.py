# Historia en carga / aprobada y eliminacion de lo cargado por error (15/10/2026).
# Procedimiento: Francisco carga bajo la supervision de la Dra.; ella aprueba.

from datetime import date as _date, timedelta as _timedelta

NAC_MENOR = (_date.today() - _timedelta(days=365 * 5)).isoformat()

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app import security
from app.enums import RolUsuario
from app.models import (
    AuditoriaUsuario,
    BitacoraTratamiento,
    ExamenSolicitado,
    OdontogramaHallazgo,
    Paciente,
    ProfesionalTratante,
    Tratamiento,
    Usuario,
    Visita,
)


@pytest_asyncio.fixture
async def usuarios(session_factory):
    ids = {}
    async with session_factory() as s:
        for nombre, rol in (("doctora", RolUsuario.dra), ("francisco", RolUsuario.dra), ("asistente", RolUsuario.asistente)):
            u = Usuario(nombre=nombre, rol=rol, password_hash="x", email=f"{nombre}@e.com")
            s.add(u)
            await s.flush()
            ids[nombre] = u.id
        # Solo la cuenta de la Dra. esta vinculada a un profesional.
        s.add(ProfesionalTratante(nombre="Leonor Granados", usuario_id=ids["doctora"]))
        await s.commit()
    return ids


def _h(usuarios, nombre, rol):
    return {"Authorization": f"Bearer {security.crear_access_token(usuarios[nombre], rol)}"}


@pytest.fixture
def h_dra(usuarios):
    return _h(usuarios, "doctora", "dra")


@pytest.fixture
def h_fran(usuarios):
    return _h(usuarios, "francisco", "dra")


@pytest.fixture
def h_asistente(usuarios):
    return _h(usuarios, "asistente", "asistente")


async def _paciente(client, h, nombre="Paciente de prueba"):
    r = await client.post(
        "/pacientes",
        headers=h,
        json={"movil": "04141234567", "nombre_completo": nombre, "fecha_registro": "2026-10-05", "fecha_nacimiento": NAC_MENOR},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _contar(session_factory, modelo):
    async with session_factory() as s:
        return (await s.execute(select(func.count()).select_from(modelo))).scalar_one()


# ------------------------------------------------------------------ aprobacion


async def test_toda_ficha_nueva_nace_en_carga(client, h_asistente):
    p = await _paciente(client, h_asistente)
    assert (p["estado_historia"], p["aprobada_en"]) == ("en_carga", None)


async def test_solo_la_cuenta_vinculada_a_la_dra_aprueba(client, h_dra, h_fran, h_asistente):
    pid = (await _paciente(client, h_dra))["id"]
    url = f"/pacientes/{pid}/aprobar-historia"
    r = await client.post(url, headers=h_fran, json={"confirmo": True})
    assert r.status_code == 403 and "Solo la Dra." in r.json()["detail"]
    assert (await client.post(url, headers=h_asistente, json={"confirmo": True})).status_code == 403
    assert (await client.post(url, headers=h_dra, json={})).status_code == 422  # sin confirmar
    r = await client.post(url, headers=h_dra, json={"confirmo": True})
    assert r.status_code == 200, r.text
    assert r.json()["estado_historia"] == "aprobada" and r.json()["aprobada_en"]
    assert (await client.post(url, headers=h_dra, json={"confirmo": True})).status_code == 409


async def test_la_aprobacion_queda_en_el_historial_de_cambios_y_en_el_log(client, h_dra, session_factory):
    p = await _paciente(client, h_dra)
    await client.post(f"/pacientes/{p['id']}/aprobar-historia", headers=h_dra, json={"confirmo": True})
    cambios = (await client.get(f"/pacientes/{p['id']}/cambios", headers=h_dra)).json()
    assert [(c["campo"], c["valor_anterior"], c["valor_nuevo"]) for c in cambios] == [("estado_historia", "en_carga", "aprobada")]
    async with session_factory() as s:
        acciones = (await s.execute(select(AuditoriaUsuario.accion))).scalars().all()
    assert "historia_aprobada" in acciones


# ----------------------------------------------------- eliminar la historia entera


async def test_eliminar_historia_en_carga_pide_el_numero_y_deja_log_sin_datos_clinicos(client, h_fran, session_factory):
    p = await _paciente(client, h_fran)
    url = f"/pacientes/{p['id']}/eliminar-historia"
    assert (await client.post(url, headers=h_fran, json={"numero_historia": "999"})).status_code == 422
    r = await client.post(url, headers=h_fran, json={"numero_historia": str(int(p["numero_historia"]))})
    assert r.status_code == 200 and r.json()["eliminada"] == p["numero_historia"]
    assert await _contar(session_factory, Paciente) == 0
    async with session_factory() as s:
        log = (await s.execute(select(AuditoriaUsuario.detalle).where(AuditoriaUsuario.accion == "historia_en_carga_eliminada"))).scalar_one()
    assert log.startswith(p["numero_historia"]) and "Paciente de prueba" not in log


async def test_una_historia_aprobada_no_se_elimina(client, h_dra, h_fran, session_factory):
    p = await _paciente(client, h_dra)
    await client.post(f"/pacientes/{p['id']}/aprobar-historia", headers=h_dra, json={"confirmo": True})
    r = await client.post(f"/pacientes/{p['id']}/eliminar-historia", headers=h_fran, json={"numero_historia": p["numero_historia"]})
    assert r.status_code == 409 and "ya está aprobada" in r.json()["detail"]
    assert await _contar(session_factory, Paciente) == 1


async def test_la_asistente_no_elimina_nada(client, h_dra, h_asistente):
    p = await _paciente(client, h_dra)
    assert (await client.post(f"/pacientes/{p['id']}/eliminar-historia", headers=h_asistente, json={"numero_historia": "1"})).status_code == 403


# ------------------------------------------- eliminar un registro cargado por error


async def _tratamiento(client, h, pid):
    prof = await client.post("/profesionales-tratantes", headers=h, json={"nombre": "Dra. X"})
    return (
        await client.post(
            f"/pacientes/{pid}/tratamientos", headers=h,
            json={"tipo": "Endodoncia", "fecha_inicio": "2026-09-01", "profesional_tratante_id": prof.json()["id"], "dientes": [11]},
        )
    ).json()["id"]


async def test_eliminar_una_visita_de_tratamiento_deja_el_tratamiento_y_desvincula(client, h_fran, session_factory):
    pid = (await _paciente(client, h_fran))["id"]
    trat = await _tratamiento(client, h_fran, pid)
    visita = (await client.post(f"/pacientes/{pid}/visitas", headers=h_fran, json={"fecha": "2026-10-01", "tipo": "tratamiento", "tratamiento_ids": [trat]})).json()["id"]
    examen = (await client.post(f"/pacientes/{pid}/examenes", headers=h_fran, json={"tipo": "tomografia", "fecha_indicacion": "2026-10-02", "visita_id": visita})).json()["id"]
    assert (await client.delete(f"/visitas/{visita}", headers=h_fran)).status_code == 204
    assert await _contar(session_factory, Visita) == 0 and await _contar(session_factory, Tratamiento) == 1
    ex = (await client.get(f"/pacientes/{pid}/examenes", headers=h_fran)).json()[0]
    assert ex["id"] == examen and ex["visita_id"] is None  # el examen se conserva, sin visita


async def test_eliminar_tratamiento_borra_sus_dientes_y_desvincula_lo_demas(client, h_fran, session_factory):
    pid = (await _paciente(client, h_fran))["id"]
    trat = await _tratamiento(client, h_fran, pid)
    await client.post(f"/pacientes/{pid}/visitas", headers=h_fran, json={"fecha": "2026-10-01", "tipo": "tratamiento", "tratamiento_ids": [trat]})
    assert (await client.delete(f"/tratamientos/{trat}", headers=h_fran)).status_code == 204
    assert await _contar(session_factory, Tratamiento) == 0 and await _contar(session_factory, Visita) == 1


async def test_eliminar_entrada_de_bitacora_y_examen(client, h_fran, session_factory):
    pid = (await _paciente(client, h_fran))["id"]
    entrada = (await client.post(f"/pacientes/{pid}/bitacora", headers=h_fran, json={"fecha": "2026-10-02", "descripcion": "x", "dientes": [11, 12]})).json()["id"]
    examen = (await client.post(f"/pacientes/{pid}/examenes", headers=h_fran, json={"tipo": "rx_panoramica", "fecha_indicacion": "2026-10-02"})).json()["id"]
    assert (await client.delete(f"/bitacora/{entrada}", headers=h_fran)).status_code == 204
    assert (await client.delete(f"/examenes/{examen}", headers=h_fran)).status_code == 204
    assert await _contar(session_factory, BitacoraTratamiento) == 0 and await _contar(session_factory, ExamenSolicitado) == 0


async def test_deshacer_una_restauracion_reabre_la_caries(client, h_fran):
    pid = (await _paciente(client, h_fran))["id"]
    await client.post(
        f"/pacientes/{pid}/dientes/22/hallazgos", headers=h_fran,
        json={"numero_diente": 22, "tipo_hallazgo": "caries", "superficie": "oclusal", "fecha": "2026-10-01"},
    )
    hecho = (
        await client.post(
            f"/pacientes/{pid}/dientes/22/tratamiento-realizado", headers=h_fran,
            json={"numero_diente": 22, "tratamiento": "restauracion", "fecha": "2026-10-10", "superficies": ["oclusal"]},
        )
    ).json()
    obturacion = hecho["abiertos"][0]["id"]
    assert (await client.delete(f"/hallazgos/{obturacion}", headers=h_fran)).status_code == 204
    activos = (await client.get(f"/pacientes/{pid}/odontograma", headers=h_fran)).json()
    assert [(h["tipo_hallazgo"], h["resuelto"]) for h in activos] == [("caries", False)]
    caries = (await client.get(f"/pacientes/{pid}/dientes/22/hallazgos", headers=h_fran)).json()
    assert len(caries) == 1 and caries[0]["resuelto_fecha"] is None


async def test_en_una_historia_aprobada_no_se_elimina_ningun_registro(client, h_dra, h_fran):
    pid = (await _paciente(client, h_dra))["id"]
    visita = (await client.post(f"/pacientes/{pid}/visitas", headers=h_dra, json={"fecha": "2026-10-01"})).json()["id"]
    marca = (
        await client.post(
            f"/pacientes/{pid}/dientes/22/hallazgos", headers=h_dra,
            json={"numero_diente": 22, "tipo_hallazgo": "sano", "fecha": "2026-10-01"},
        )
    ).json()["id"]
    await client.post(f"/pacientes/{pid}/aprobar-historia", headers=h_dra, json={"confirmo": True})
    for url in (f"/visitas/{visita}", f"/hallazgos/{marca}"):
        r = await client.delete(url, headers=h_fran)
        assert r.status_code == 409 and "ya está aprobada" in r.json()["detail"], url


async def test_eliminar_algo_inexistente_es_404(client, h_fran):
    assert (await client.delete("/visitas/00000000-0000-0000-0000-000000000000", headers=h_fran)).status_code == 404


# ------------------------------------------------------------------ marca BORRADOR


async def test_el_odontograma_se_imprime_con_la_marca_hasta_aprobar(client, h_dra, monkeypatch):
    from app.services import odontograma_impreso as impreso, pdf as servicio_pdf

    async def _render(plantilla, contexto):  # el "PDF" es el HTML de la plantilla
        return servicio_pdf._plantillas.get_template(plantilla).render(**contexto).encode("utf-8")

    async def _sin_raices(session):  # diente_anatomia usa ARRAY: no existe en sqlite
        return {}

    monkeypatch.setattr("app.routers.pdf.generar_pdf", _render)
    monkeypatch.setattr("app.routers.historia_clinica.generar_pdf", _render)
    monkeypatch.setattr(impreso, "raices_por_diente", _sin_raices)
    p = await _paciente(client, h_dra)
    pid = p["id"]
    # historia-completa usa la misma plantilla/flag, pero necesita tablas que sqlite del test no crea
    for url in (f"/pacientes/{pid}/pdf/odontograma-actual",):
        r = await client.get(url, headers=h_dra)
        assert r.status_code == 200, (url, r.text[:200])
        assert "BORRADOR — pendiente de aprobación" in r.text, url
    await client.post(f"/pacientes/{pid}/aprobar-historia", headers=h_dra, json={"confirmo": True})
    for url in (f"/pacientes/{pid}/pdf/odontograma-actual",):
        assert "BORRADOR" not in (await client.get(url, headers=h_dra)).text, url
