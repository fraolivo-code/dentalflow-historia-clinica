# Correccion de datos del paciente (04/10/2026), Parte A.
# Especificacion: especificacion-tecnica-correccion-datos-paciente.md.

from datetime import date as _date, timedelta as _timedelta

NAC_MENOR = (_date.today() - _timedelta(days=365 * 5)).isoformat()  # 5 anios: sin cedula obligatoria
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
        "fecha_registro": "2026-10-05", "fecha_nacimiento": NAC_MENOR,
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
    p = await _alta(client, h_dra, cedula="V-999", fecha_nacimiento="1980-01-01")
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


async def test_corregir_numero_reformatea_al_cambiar_el_ancho(client, h_dra):
    p = await _alta(client, h_dra)
    await client.put(
        "/configuracion/numeracion", headers=h_dra, json={"siguiente_numero": 50, "numero_ancho": 6}
    )
    r = await _corregir(client, h_dra, p["id"], "1")
    assert (r.status_code, r.json()["numero_historia"]) == (200, "000001")


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


# ------------------------------------------------- cedula y fecha de nacimiento

NAC_ADULTO = "1990-05-17"


async def _post(client, h, **extra):
    cuerpo = {"movil": "04141234567", "nombre_completo": "Paciente Prueba", "fecha_registro": "2026-10-05", **extra}
    return await client.post("/pacientes", headers=h, json=cuerpo)


async def test_alta_exige_fecha_de_nacimiento(client, h_asistente):
    r = await _post(client, h_asistente)
    assert (r.status_code, r.json()["detail"]) == (422, "La fecha de nacimiento es obligatoria.")


async def test_alta_adulto_exige_cedula_y_menor_no(client, h_asistente):
    r = await _post(client, h_asistente, fecha_nacimiento=NAC_ADULTO)
    assert r.status_code == 422 and "cédula es obligatoria" in r.json()["detail"]
    assert (await _post(client, h_asistente, fecha_nacimiento=NAC_MENOR)).status_code == 201
    assert (await _post(client, h_asistente, fecha_nacimiento=NAC_ADULTO, cedula="V-12345678")).status_code == 201


async def test_cedula_se_pide_exactamente_a_los_12_anios(client, h_asistente):
    from datetime import date

    hoy = date.today()
    doce = hoy.replace(year=hoy.year - 12) if (hoy.month, hoy.day) != (2, 29) else hoy.replace(year=hoy.year - 12, day=28)
    casi = doce.replace(year=doce.year + 1) if (doce.month, doce.day) != (2, 29) else doce.replace(year=doce.year + 1, day=28)
    assert (await _post(client, h_asistente, fecha_nacimiento=casi.isoformat())).status_code == 201  # 11
    assert (await _post(client, h_asistente, fecha_nacimiento=doce.isoformat())).status_code == 422  # 12


async def test_fecha_futura_es_422(client, h_asistente):
    r = await _post(client, h_asistente, fecha_nacimiento="2999-01-01")
    assert r.status_code == 422 and "futura" in r.json()["detail"]


async def test_cedula_duplicada_es_409_y_dice_cual_ficha(client, h_asistente):
    primero = (await _post(client, h_asistente, fecha_nacimiento=NAC_ADULTO, cedula="V-12345678")).json()
    # misma cedula escrita distinto: se normaliza y choca
    r = await _post(client, h_asistente, fecha_nacimiento=NAC_ADULTO, cedula="v-0012345678", nombre_completo="Otro")
    assert r.status_code == 409
    assert primero["numero_historia"] in r.json()["detail"] and "Paciente Prueba" in r.json()["detail"]
    # V y E son distintas
    assert (await _post(client, h_asistente, fecha_nacimiento=NAC_ADULTO, cedula="E-12345678")).status_code == 201


async def test_cedula_con_formato_invalido_es_422(client, h_asistente):
    for malo in ("12345678", "X-1", "V-abc", "V-0"):
        r = await _post(client, h_asistente, fecha_nacimiento=NAC_ADULTO, cedula=malo)
        assert r.status_code == 422, malo


async def test_cedula_se_normaliza(client, h_asistente):
    r = await _post(client, h_asistente, fecha_nacimiento=NAC_ADULTO, cedula=" v-0012345 ")
    assert r.json()["cedula"] == "V-12345"


async def test_asistente_completa_cedula_vacia_pero_no_cambia_una_existente(client, h_asistente, h_dra):
    menor = await _alta(client, h_dra)  # sin cedula
    r = await client.patch(f"/pacientes/{menor['id']}", headers=h_asistente, json={"cedula": "V-777"})
    assert (r.status_code, r.json()["cedula"]) == (200, "V-777")
    r = await client.patch(f"/pacientes/{menor['id']}", headers=h_asistente, json={"cedula": "V-888"})
    assert r.status_code == 403
    assert (await client.patch(f"/pacientes/{menor['id']}", headers=h_dra, json={"cedula": "V-888"})).status_code == 200


async def test_patch_no_deja_adulto_sin_cedula_ni_duplicada(client, h_dra):
    a = await _alta(client, h_dra, cedula="V-111", fecha_nacimiento=NAC_ADULTO)
    b = await _alta(client, h_dra, cedula="V-222", fecha_nacimiento=NAC_ADULTO)
    r = await client.patch(f"/pacientes/{b['id']}", headers=h_dra, json={"cedula": None})
    assert r.status_code == 422
    r = await client.patch(f"/pacientes/{b['id']}", headers=h_dra, json={"cedula": "V-111"})
    assert r.status_code == 409 and a["numero_historia"] in r.json()["detail"]
    # misma cedula en su propia ficha no es duplicado
    assert (await client.patch(f"/pacientes/{b['id']}", headers=h_dra, json={"cedula": "V-222", "movil": "04141112222"})).status_code == 200


async def test_pasaporte_se_acepta_normaliza_y_no_se_repite(client, h_asistente):
    r = await _post(client, h_asistente, fecha_nacimiento=NAC_ADULTO, cedula=" p-ab123456 ")
    assert (r.status_code, r.json()["cedula"]) == (201, "P-AB123456")
    r = await _post(client, h_asistente, fecha_nacimiento=NAC_ADULTO, cedula="PAB123456")
    assert r.status_code == 409
    for malo in ("P-1", "P-AB 12345", "P-AB-12345"):
        assert (await _post(client, h_asistente, fecha_nacimiento=NAC_ADULTO, cedula=malo)).status_code == 422, malo


async def test_cedula_representante_es_opcional_se_normaliza_y_puede_repetirse(client, h_asistente):
    a = await _post(client, h_asistente, fecha_nacimiento=NAC_MENOR, cedula_representante="v-0099")
    assert (a.status_code, a.json()["cedula_representante"]) == (201, "V-99")
    # hermanos: mismo representante
    b = await _post(client, h_asistente, fecha_nacimiento=NAC_MENOR, cedula_representante="V-99", nombre_completo="Hermano")
    assert b.status_code == 201
    assert (await _post(client, h_asistente, fecha_nacimiento=NAC_MENOR, cedula_representante="99")).status_code == 422
    sin = await _post(client, h_asistente, fecha_nacimiento=NAC_MENOR)
    assert sin.json()["cedula_representante"] is None
    # la asistente la completa si esta vacia, no la cambia
    r = await client.patch(f"/pacientes/{sin.json()['id']}", headers=h_asistente, json={"cedula_representante": "V-5"})
    assert r.status_code == 200
    r = await client.patch(f"/pacientes/{sin.json()['id']}", headers=h_asistente, json={"cedula_representante": "V-6"})
    assert r.status_code == 403
