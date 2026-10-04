# Correccion de datos del paciente (04/10/2026), Parte A.
# Especificacion: especificacion-tecnica-correccion-datos-paciente.md.

import pytest
import pytest_asyncio
from sqlalchemy import select

from app import security
from app.enums import RolUsuario
from app.models import AuditoriaUsuario, Paciente, PacienteCambio, Usuario


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


async def _alta(client, h, **extra):
    cuerpo = {
        "movil": "04141234567",
        "nombre_completo": "Paciente Prueba",
        "fecha_registro": "2026-10-05",
        **extra,
    }
    r = await client.post("/pacientes", headers=h, json=cuerpo)
    assert r.status_code == 201, r.text
    return r.json()


async def _cambios(client, h, pid):
    r = await client.get(f"/pacientes/{pid}/cambios", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


async def _corregir(client, h, pid, nuevo, confirmo=True):
    return await client.post(
        f"/pacientes/{pid}/numero-historia", headers=h, json={"numero_nuevo": nuevo, "confirmo": confirmo}
    )


# ------------------------------------------------------------------ PATCH


async def test_asistente_corrige_contacto_y_se_registra(client, h_asistente, h_dra):
    p = await _alta(client, h_dra, telefono_fijo="02121112233")
    r = await client.patch(
        f"/pacientes/{p['id']}",
        headers=h_asistente,
        json={"movil": "04245556677", "telefono_fijo": "02129998877", "email": "a@b.com", "direccion": "Calle 1"},
    )
    assert r.status_code == 200
    assert r.json()["email"] == "a@b.com"
    campos = {c["campo"]: c for c in await _cambios(client, h_dra, p["id"])}
    assert set(campos) == {"movil", "telefono_fijo", "email", "direccion"}
    assert campos["movil"]["valor_anterior"] == "04141234567"
    assert campos["movil"]["valor_nuevo"] == "04245556677"
    assert campos["email"]["valor_anterior"] is None
    assert campos["movil"]["actor_nombre"] == "asistente"
    assert campos["movil"]["etiqueta"] == "Teléfono móvil"


async def test_asistente_con_un_campo_personal_es_403_y_no_cambia_nada(client, h_asistente, h_dra):
    p = await _alta(client, h_dra)
    r = await client.patch(
        f"/pacientes/{p['id']}",
        headers=h_asistente,
        json={"movil": "04245556677", "nombre_completo": "Otro Nombre"},
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "Solo puede corregir los datos de contacto del paciente."
    despues = (await client.get(f"/pacientes/{p['id']}", headers=h_dra)).json()
    assert despues["movil"] == "04141234567" and despues["nombre_completo"] == "Paciente Prueba"
    assert await _cambios(client, h_dra, p["id"]) == []


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("cedula", "V-123"),
        ("fecha_nacimiento", "1990-01-01"),
        ("referido_por", "Juan"),
        ("fecha_primera_consulta_real", "2009-03-15"),
        ("historia_origen", "Otro consultorio"),
        ("seguro", "Mercantil"),
        ("fuma", True),
        ("foto", "x.jpg"),
    ],
)
async def test_asistente_no_corrige_ningun_campo_personal(client, h_asistente, h_dra, campo, valor):
    p = await _alta(client, h_dra)
    r = await client.patch(f"/pacientes/{p['id']}", headers=h_asistente, json={campo: valor})
    assert r.status_code == 403


async def test_acceso_total_corrige_personales_y_contacto(client, h_dra):
    p = await _alta(client, h_dra)
    r = await client.patch(
        f"/pacientes/{p['id']}",
        headers=h_dra,
        json={
            "nombre_completo": "Nombre Corregido",
            "cedula": "V-12345678",
            "fecha_nacimiento": "1990-05-17",
            "fuma": True,
            "fecha_primera_consulta_real": "2009-03-15",
            "movil": "04245556677",
        },
    )
    assert r.status_code == 200
    assert r.json()["paciente_desde"] == 2009
    campos = {c["campo"]: c for c in await _cambios(client, h_dra, p["id"])}
    assert set(campos) == {
        "nombre_completo", "cedula", "fecha_nacimiento", "fuma", "fecha_primera_consulta_real", "movil"
    }
    assert campos["fecha_nacimiento"]["valor_nuevo"] == "1990-05-17"
    assert (campos["fuma"]["valor_anterior"], campos["fuma"]["valor_nuevo"]) == ("No", "Sí")
    assert campos["nombre_completo"]["valor_anterior"] == "Paciente Prueba"


async def test_sin_cambios_reales_no_registra_nada(client, h_dra, h_asistente, session_factory):
    p = await _alta(client, h_dra)
    for h, cuerpo in (
        (h_dra, {"nombre_completo": "Paciente Prueba", "movil": "04141234567"}),
        (h_asistente, {"movil": "04141234567"}),
    ):
        r = await client.patch(f"/pacientes/{p['id']}", headers=h, json=cuerpo)
        assert r.status_code == 200
    assert await _cambios(client, h_dra, p["id"]) == []
    async with session_factory() as s:
        assert (await s.get(Paciente, __import__("uuid").UUID(p["id"]))).actualizado_por is None


async def test_cambiar_movil_recalcula_movil_normalizado(client, h_asistente, h_dra, session_factory):
    import uuid

    p = await _alta(client, h_dra)
    await client.patch(f"/pacientes/{p['id']}", headers=h_asistente, json={"movil": "0424-555.66.77"})
    async with session_factory() as s:
        fila = await s.get(Paciente, uuid.UUID(p["id"]))
        assert fila.movil_normalizado == "584245556677"
        assert fila.actualizado_por is not None and fila.actualizado_en is not None


async def test_validaciones_del_alta_siguen_en_la_correccion(client, h_dra):
    p = await _alta(client, h_dra)
    assert (await client.patch(f"/pacientes/{p['id']}", headers=h_dra, json={"nombre_completo": "  "})).status_code == 422
    assert (await client.patch(f"/pacientes/{p['id']}", headers=h_dra, json={"seguro": "x" * 121})).status_code == 422
    assert (await client.patch(f"/pacientes/{p['id']}", headers=h_dra, json={})).status_code == 422
    assert (await client.patch(f"/pacientes/{p['id']}", headers=h_dra, json={"movil": None})).status_code == 422
    assert await _cambios(client, h_dra, p["id"]) == []


async def test_patch_sin_sesion_es_401_y_paciente_inexistente_404(client, h_dra):
    import uuid

    p = await _alta(client, h_dra)
    assert (await client.patch(f"/pacientes/{p['id']}", json={"movil": "1"})).status_code == 401
    r = await client.patch(f"/pacientes/{uuid.uuid4()}", headers=h_dra, json={"movil": "04141112233"})
    assert r.status_code == 404


# ----------------------------------------------------- corregir el numero


async def test_corregir_numero_normaliza_registra_y_audita(client, h_dra, session_factory):
    p = await _alta(client, h_dra)  # 0001
    r = await _corregir(client, h_dra, p["id"], " 457 ")
    assert r.status_code == 200
    assert r.json()["numero_historia"] == "0457"
    c = (await _cambios(client, h_dra, p["id"]))[0]
    assert (c["campo"], c["valor_anterior"], c["valor_nuevo"]) == ("numero_historia", "0001", "0457")
    assert c["etiqueta"] == "N.° de historia" and c["actor_nombre"] == "doctora"
    async with session_factory() as s:
        acciones = (await s.execute(select(AuditoriaUsuario.accion))).scalars().all()
    assert "numero_historia_corregido" in acciones


async def test_corregir_numero_exige_confirmacion(client, h_dra):
    p = await _alta(client, h_dra)
    for cuerpo in ({"numero_nuevo": "457"}, {"numero_nuevo": "457", "confirmo": False}):
        r = await client.post(f"/pacientes/{p['id']}/numero-historia", headers=h_dra, json=cuerpo)
        assert r.status_code == 422
        assert r.json()["detail"] == "Debe confirmar la corrección del número."
    assert (await client.get(f"/pacientes/{p['id']}", headers=h_dra)).json()["numero_historia"] == "0001"


async def test_corregir_numero_igual_al_actual_es_422(client, h_dra):
    p = await _alta(client, h_dra)
    for nuevo in ("1", "0001", "00001"):
        r = await _corregir(client, h_dra, p["id"], nuevo)
        assert r.status_code == 422
        assert r.json()["detail"] == "El número nuevo es igual al actual."
    assert await _cambios(client, h_dra, p["id"]) == []


async def test_corregir_numero_en_uso_es_409(client, h_dra):
    a = await _alta(client, h_dra)
    b = await _alta(client, h_dra)
    r = await _corregir(client, h_dra, b["id"], a["numero_historia"].lstrip("0"))
    assert r.status_code == 409
    assert r.json()["detail"] == "Ya existe una historia con el número 0001."


@pytest.mark.parametrize("valor", ["45a7", "H-12", "0", "0000", "", "1" * 19])
async def test_corregir_numero_invalido_es_422(client, h_dra, valor):
    p = await _alta(client, h_dra)
    assert (await _corregir(client, h_dra, p["id"], valor)).status_code == 422


async def test_corregir_numero_solo_acceso_total(client, h_asistente, h_dra):
    p = await _alta(client, h_dra)
    assert (await _corregir(client, h_asistente, p["id"], "457")).status_code == 403
    assert (await client.post(f"/pacientes/{p['id']}/numero-historia", json={})).status_code == 401
    assert (await client.get(f"/pacientes/{p['id']}", headers=h_dra)).json()["numero_historia"] == "0001"


async def test_corregir_numero_de_paciente_inexistente_es_404(client, h_dra):
    import uuid

    assert (await _corregir(client, h_dra, str(uuid.uuid4()), "457")).status_code == 404


async def test_alta_automatica_sigue_saltando_numeros_tras_una_correccion(client, h_dra):
    a = await _alta(client, h_dra)  # 0001
    await _alta(client, h_dra)  # 0002
    await _corregir(client, h_dra, a["id"], "3")  # 0001 -> 0003; el 0001 queda libre
    siguiente = await _alta(client, h_dra)  # la secuencia da 3 (usado) y salta a 4
    assert siguiente["numero_historia"] == "0004"


# -------------------------------------------------------------- historial


async def test_historial_ordenado_y_solo_acceso_total(client, h_dra, h_asistente):
    p = await _alta(client, h_dra)
    await client.patch(f"/pacientes/{p['id']}", headers=h_asistente, json={"movil": "04245556677"})
    await client.patch(f"/pacientes/{p['id']}", headers=h_dra, json={"cedula": "V-1"})
    await _corregir(client, h_dra, p["id"], "457")
    lista = await _cambios(client, h_dra, p["id"])
    assert [c["campo"] for c in lista] == ["numero_historia", "cedula", "movil"]
    assert [c["actor_nombre"] for c in lista] == ["doctora", "doctora", "asistente"]
    assert (await client.get(f"/pacientes/{p['id']}/cambios", headers=h_asistente)).status_code == 403
    assert (await client.get(f"/pacientes/{p['id']}/cambios")).status_code == 401


async def test_historial_de_otro_paciente_no_se_mezcla_y_404(client, h_dra):
    import uuid

    a = await _alta(client, h_dra)
    b = await _alta(client, h_dra)
    await client.patch(f"/pacientes/{a['id']}", headers=h_dra, json={"cedula": "V-1"})
    assert await _cambios(client, h_dra, b["id"]) == []
    assert (await client.get(f"/pacientes/{uuid.uuid4()}/cambios", headers=h_dra)).status_code == 404


async def test_el_historial_no_se_purga_con_la_purga_de_auditoria(client, h_dra, session_factory):
    from datetime import datetime, timedelta, timezone

    from app.services import auditoria

    p = await _alta(client, h_dra)
    await client.patch(f"/pacientes/{p['id']}", headers=h_dra, json={"cedula": "V-1"})
    async with session_factory() as s:
        await auditoria.purgar_antiguos(s, ahora=datetime.now(timezone.utc) + timedelta(days=5000))
        assert (await s.execute(select(PacienteCambio))).scalars().all()
