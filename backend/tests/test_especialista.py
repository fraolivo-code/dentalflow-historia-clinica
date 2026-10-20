# Rol de especialista (19/10/2026, migracion 0038). Diseno: docs/proceso-trabajo-caso-334.md, seccion 16.
# Lo que se prueba aqui es SEGURIDAD: que el especialista no vea ni toque nada fuera de lo que se le remitio.

import uuid
from datetime import date, date as _date, timedelta as _timedelta

import pytest
import pytest_asyncio

from app import security
from app.enums import OrigenHallazgo, RolUsuario, TipoHallazgo
from app.models import OdontogramaHallazgo, Usuario
from app.services.especialista import edad_en_anios

NAC_MENOR = (_date.today() - _timedelta(days=365 * 5)).isoformat()
CLAVE_DRA = "ClaveDeLaDra#2026"
PIN = "482913"


@pytest_asyncio.fixture
async def cuentas(session_factory):
    ids = {}
    async with session_factory() as s:
        for nombre, rol in (
            ("doctora", RolUsuario.dra),
            ("asistente", RolUsuario.asistente),
            ("cirujano", RolUsuario.especialista),
            ("endodoncista", RolUsuario.especialista),
        ):
            u = Usuario(nombre=nombre, rol=rol, password_hash=security.hash_password(CLAVE_DRA), email=f"{nombre}@e.com")
            s.add(u)
            await s.flush()
            ids[nombre] = u.id
        await s.commit()
    return ids


def _h(cuentas, nombre, rol):
    return {"Authorization": f"Bearer {security.crear_access_token(cuentas[nombre], rol)}"}


@pytest.fixture
def h_dra(cuentas):
    return _h(cuentas, "doctora", "dra")


@pytest.fixture
def h_asistente(cuentas):
    return _h(cuentas, "asistente", "asistente")


@pytest.fixture
def h_cirujano(cuentas):
    return _h(cuentas, "cirujano", "especialista")


@pytest.fixture
def h_endo(cuentas):
    return _h(cuentas, "endodoncista", "especialista")


async def _paciente(client, h, nombre="Paciente Prueba"):
    r = await client.post(
        "/pacientes",
        headers=h,
        json={
            "movil": "04141234567",
            "telefono_fijo": "02121112233",
            "email": "paciente@ejemplo.com",
            "nombre_completo": nombre,
            "fecha_registro": "2026-10-05",
            "fecha_nacimiento": NAC_MENOR,
            "direccion": "Calle Secreta 123",
            "empresa_profesion_cargo": "Empresa Reservada",
            "seguro": "Seguro Reservado",
            "fuma": True,
            "fuma_detalle": "5 al dia",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _remitir(client, h_dra, pid, cuentas, especialista="cirujano", dientes=(36,), toda_la_boca=False, motivo="Exodoncia del 36"):
    return await client.post(
        f"/pacientes/{pid}/remisiones",
        headers=h_dra,
        json={"especialista_id": str(cuentas[especialista]), "motivo": motivo, "dientes": list(dientes), "toda_la_boca": toda_la_boca},
    )


async def _fijar_pin(client, h_dra, pin=PIN):
    r = await client.put("/mi-cuenta/clave-de-autorizacion", headers=h_dra, json={"pin": pin, "clave_actual": CLAVE_DRA})
    assert r.status_code == 204, r.text


# ============================== el cierre por defecto ==============================

RUTAS_PROHIBIDAS = [
    ("GET", "/pacientes"),
    ("GET", "/pacientes/{pid}"),
    ("POST", "/pacientes"),
    ("PATCH", "/pacientes/{pid}"),
    ("GET", "/pacientes/{pid}/odontograma"),
    ("GET", "/pacientes/{pid}/visitas"),
    ("GET", "/pacientes/{pid}/antecedentes"),
    ("GET", "/pacientes/{pid}/observaciones"),
    ("GET", "/pacientes/{pid}/bitacora"),
    ("GET", "/pacientes/{pid}/recordatorios"),
    ("GET", "/pacientes/{pid}/remisiones"),
    ("GET", "/pacientes/{pid}/atenciones-especialistas"),
    ("GET", "/pacientes/{pid}/accesos-especialistas"),
    ("GET", "/pacientes/{pid}/historia-compacta"),
    ("GET", "/recordatorios/vencidos"),
    ("GET", "/especialistas"),
    ("GET", "/usuarios"),
    ("POST", "/usuarios"),
    ("PUT", "/mi-cuenta/clave-de-autorizacion"),
    ("GET", "/medicamentos"),
]


@pytest.mark.parametrize("metodo, ruta", RUTAS_PROHIBIDAS)
async def test_el_especialista_no_entra_a_nada_fuera_de_lo_suyo(client, h_dra, h_cirujano, cuentas, metodo, ruta):
    pid = await _paciente(client, h_dra)
    await _remitir(client, h_dra, pid, cuentas)   # aun remitido, estas rutas no son suyas
    r = await client.request(metodo, ruta.format(pid=pid), headers=h_cirujano, json={} if metodo != "GET" else None)
    assert r.status_code == 403, (metodo, ruta, r.status_code, r.text)


async def test_el_especialista_si_puede_usar_su_cuenta(client, h_cirujano):
    r = await client.get("/auth/me", headers=h_cirujano)
    assert r.status_code == 200, r.text


async def test_sin_sesion_no_hay_nada(client, h_dra, cuentas):
    pid = await _paciente(client, h_dra)
    assert (await client.get("/especialista/pacientes")).status_code in (401, 403)
    assert (await client.get(f"/especialista/pacientes/{pid}/ficha")).status_code in (401, 403)


async def test_la_dra_y_la_asistente_no_usan_las_rutas_del_especialista(client, h_dra, h_asistente, cuentas):
    pid = await _paciente(client, h_dra)
    for h in (h_dra, h_asistente):
        assert (await client.get("/especialista/pacientes", headers=h)).status_code == 403
        assert (await client.get(f"/especialista/pacientes/{pid}/ficha", headers=h)).status_code == 403


# ============================== remitir y retirar ==============================

async def test_la_dra_remite_y_el_especialista_ve_a_ese_paciente(client, h_dra, h_cirujano, cuentas):
    pid = await _paciente(client, h_dra)
    assert (await client.get("/especialista/pacientes", headers=h_cirujano)).json() == []
    r = await _remitir(client, h_dra, pid, cuentas)
    assert r.status_code == 201, r.text
    assert r.json()["dientes"] == [36] and r.json()["especialista_nombre"] == "cirujano"
    mis = (await client.get("/especialista/pacientes", headers=h_cirujano)).json()
    assert [p["id"] for p in mis] == [pid] and mis[0]["motivo"] == "Exodoncia del 36"


async def test_solo_ve_a_los_pacientes_remitidos_a_el(client, h_dra, h_cirujano, h_endo, cuentas):
    mio = await _paciente(client, h_dra, "Paciente Mio")
    ajeno = await _paciente(client, h_dra, "Paciente De Otro")
    sin_remitir = await _paciente(client, h_dra, "Paciente Sin Remitir")
    await _remitir(client, h_dra, mio, cuentas, "cirujano")
    await _remitir(client, h_dra, ajeno, cuentas, "endodoncista")

    assert [p["id"] for p in (await client.get("/especialista/pacientes", headers=h_cirujano)).json()] == [mio]
    for otro in (ajeno, sin_remitir):
        assert (await client.get(f"/especialista/pacientes/{otro}/ficha", headers=h_cirujano)).status_code == 404
        assert (await client.get(f"/especialista/pacientes/{otro}/odontograma", headers=h_cirujano)).status_code == 404
        r = await client.post(
            f"/especialista/pacientes/{otro}/atenciones", headers=h_cirujano, json={"fecha": "2026-10-19", "procedimiento": "x"}
        )
        assert r.status_code == 404


async def test_validaciones_de_la_remision(client, h_dra, h_asistente, cuentas):
    pid = await _paciente(client, h_dra)
    assert (await _remitir(client, h_dra, pid, cuentas, dientes=(), toda_la_boca=False)).status_code == 422
    assert (await _remitir(client, h_dra, pid, cuentas, dientes=(99,))).status_code == 422
    assert (await _remitir(client, h_dra, pid, cuentas, motivo="   ")).status_code == 422
    # no se remite a una asistente ni a la propia Dra.
    for no_especialista in ("asistente", "doctora"):
        assert (await _remitir(client, h_dra, pid, cuentas, especialista=no_especialista)).status_code == 422
    assert (await _remitir(client, h_dra, pid, cuentas, dientes=(), toda_la_boca=True)).status_code == 201
    assert (await _remitir(client, h_dra, pid, cuentas)).status_code == 409           # ya vigente
    assert (await _remitir(client, h_asistente, pid, cuentas)).status_code == 403     # la asistente no remite


async def test_retirar_el_acceso_lo_corta_y_permite_remitir_de_nuevo(client, h_dra, h_cirujano, cuentas):
    pid = await _paciente(client, h_dra)
    rid = (await _remitir(client, h_dra, pid, cuentas)).json()["id"]
    assert (await client.get(f"/especialista/pacientes/{pid}/ficha", headers=h_cirujano)).status_code == 200

    r = await client.patch(f"/remisiones/{rid}/retirar", headers=h_dra)
    assert r.status_code == 200 and r.json()["retirada_en"] is not None
    assert (await client.patch(f"/remisiones/{rid}/retirar", headers=h_dra)).status_code == 409
    assert (await client.get("/especialista/pacientes", headers=h_cirujano)).json() == []
    assert (await client.get(f"/especialista/pacientes/{pid}/ficha", headers=h_cirujano)).status_code == 404
    assert (await _remitir(client, h_dra, pid, cuentas)).status_code == 201
    historial = (await client.get(f"/pacientes/{pid}/remisiones", headers=h_dra)).json()
    assert len(historial) == 2 and sum(1 for x in historial if x["retirada_en"] is None) == 1


# ============================== lo que ve ==============================

DATOS_RESERVADOS = ["Calle Secreta 123", "Empresa Reservada", "Seguro Reservado"]


async def test_la_ficha_lleva_solo_lo_permitido(client, h_dra, h_cirujano, cuentas):
    pid = await _paciente(client, h_dra)
    await client.patch(f"/pacientes/{pid}", headers=h_dra, json={"alerta": True, "alerta_texto": "Anticoagulantes"})
    await _remitir(client, h_dra, pid, cuentas)
    r = await client.get(f"/especialista/pacientes/{pid}/ficha", headers=h_cirujano)
    assert r.status_code == 200, r.text
    ficha = r.json()
    for reservado in DATOS_RESERVADOS:
        assert reservado not in r.text
    prohibidos = {"cedula", "cedula_representante", "direccion", "empresa_profesion_cargo", "seguro", "fecha_nacimiento",
                  "referido_por", "creado_por", "estado_historia", "activo", "motivo_inactivo", "historia_origen"}
    assert not prohibidos & set(ficha["paciente"])
    # sí: contacto (se comparte al remitir), alerta con su texto y salud
    assert ficha["paciente"]["movil"] == "04141234567" and ficha["paciente"]["email"] == "paciente@ejemplo.com"
    assert ficha["paciente"]["alerta"] is True and ficha["paciente"]["alerta_texto"] == "Anticoagulantes"
    assert ficha["paciente"]["fuma"] is True and ficha["paciente"]["edad"] == edad_en_anios(date.fromisoformat(NAC_MENOR))
    assert ficha["remision"]["motivo"] == "Exodoncia del 36" and ficha["remision"]["dientes"] == [36]


async def test_notas_solo_las_ligadas_a_los_dientes_de_la_remision(client, h_dra, h_cirujano, h_endo, cuentas):
    pid = await _paciente(client, h_dra)
    for texto, dientes in (("Dolor en el 36", [36]), ("Caries en el 14", [14]), ("Nota general sin dientes", [])):
        r = await client.post(
            f"/pacientes/{pid}/bitacora", headers=h_dra, json={"fecha": "2026-10-10", "descripcion": texto, "dientes": dientes}
        )
        assert r.status_code == 201, r.text
    await _remitir(client, h_dra, pid, cuentas, "cirujano", dientes=(36,))
    await _remitir(client, h_dra, pid, cuentas, "endodoncista", dientes=(), toda_la_boca=True)

    cirujano = (await client.get(f"/especialista/pacientes/{pid}/ficha", headers=h_cirujano)).json()
    assert [n["descripcion"] for n in cirujano["notas"]] == ["Dolor en el 36"]
    endo = (await client.get(f"/especialista/pacientes/{pid}/ficha", headers=h_endo)).json()
    # «toda la boca»: cualquier nota ligada a dientes, pero nunca las que no tienen dientes
    assert sorted(n["descripcion"] for n in endo["notas"]) == ["Caries en el 14", "Dolor en el 36"]


async def test_el_odontograma_es_de_solo_lectura_y_solo_trae_lo_vigente(client, h_dra, h_cirujano, cuentas, session_factory):
    pid = await _paciente(client, h_dra)
    async with session_factory() as s:
        for diente, tipo, resuelto in ((36, "caries", False), (46, "caries", True)):
            s.add(OdontogramaHallazgo(
                paciente_id=uuid.UUID(pid), numero_diente=diente, tipo_hallazgo=TipoHallazgo(tipo),
                fecha=date(2026, 5, 2), resuelto=resuelto, resuelto_fecha=date(2026, 7, 1) if resuelto else None,
                origen=OrigenHallazgo.aqui, creado_por=cuentas["doctora"],
            ))
        await s.commit()
    await _remitir(client, h_dra, pid, cuentas)
    r = await client.get(f"/especialista/pacientes/{pid}/odontograma", headers=h_cirujano)
    assert r.status_code == 200, r.text
    assert [h["numero_diente"] for h in r.json()["hallazgos"]] == [36]
    # no puede marcar nada: las rutas de escritura del odontograma son de la Dra.
    escribir = await client.post(f"/pacientes/{pid}/dientes/36/hallazgos", headers=h_cirujano, json={})
    assert escribir.status_code == 403


# ============================== su atencion ==============================

ATENCION = {"fecha": "2026-10-19", "procedimiento": "Exodoncia del 36", "descripcion": "Sin complicaciones", "indicaciones": "Reposo", "dientes": [36]}


async def test_registra_su_atencion_y_solo_ve_las_suyas(client, h_dra, h_cirujano, h_endo, cuentas):
    pid = await _paciente(client, h_dra)
    await _remitir(client, h_dra, pid, cuentas, "cirujano")
    await _remitir(client, h_dra, pid, cuentas, "endodoncista", dientes=(14,))

    r = await client.post(f"/especialista/pacientes/{pid}/atenciones", headers=h_cirujano, json=ATENCION)
    assert r.status_code == 201, r.text
    assert r.json()["dientes"] == [36] and r.json()["autor_nombre"] == "cirujano"
    await client.post(
        f"/especialista/pacientes/{pid}/atenciones", headers=h_endo,
        json={"fecha": "2026-10-20", "procedimiento": "Conducto del 14", "dientes": [14]},
    )
    suyas = (await client.get(f"/especialista/pacientes/{pid}/atenciones", headers=h_cirujano)).json()
    assert [a["procedimiento"] for a in suyas] == ["Exodoncia del 36"]
    de_la_dra = (await client.get(f"/pacientes/{pid}/atenciones-especialistas", headers=h_dra)).json()
    assert sorted(a["autor_nombre"] for a in de_la_dra) == ["cirujano", "endodoncista"]


async def test_validaciones_de_la_atencion(client, h_dra, h_cirujano, cuentas):
    pid = await _paciente(client, h_dra)
    await _remitir(client, h_dra, pid, cuentas)
    url = f"/especialista/pacientes/{pid}/atenciones"
    assert (await client.post(url, headers=h_cirujano, json={**ATENCION, "procedimiento": "  "})).status_code == 422
    assert (await client.post(url, headers=h_cirujano, json={**ATENCION, "dientes": [99]})).status_code == 422
    assert (await client.post(url, headers=h_cirujano, json={"procedimiento": "x"})).status_code == 422


async def test_la_dra_corrige_la_atencion_y_el_especialista_no(client, h_dra, h_cirujano, cuentas):
    pid = await _paciente(client, h_dra)
    await _remitir(client, h_dra, pid, cuentas)
    aid = (await client.post(f"/especialista/pacientes/{pid}/atenciones", headers=h_cirujano, json=ATENCION)).json()["id"]

    r = await client.patch(f"/atenciones-especialistas/{aid}", headers=h_dra, json={"procedimiento": "Exodoncia quirúrgica del 36", "dientes": [36, 37]})
    assert r.status_code == 200, r.text
    assert r.json()["procedimiento"] == "Exodoncia quirúrgica del 36" and r.json()["dientes"] == [36, 37]
    assert r.json()["actualizado_por"] == str(cuentas["doctora"])
    assert (await client.patch(f"/atenciones-especialistas/{aid}", headers=h_dra, json={})).status_code == 422
    assert (await client.patch(f"/atenciones-especialistas/{aid}", headers=h_cirujano, json={"procedimiento": "x"})).status_code == 403


async def test_al_retirar_el_acceso_deja_de_poder_escribir_pero_lo_escrito_queda(client, h_dra, h_cirujano, cuentas):
    pid = await _paciente(client, h_dra)
    rid = (await _remitir(client, h_dra, pid, cuentas)).json()["id"]
    await client.post(f"/especialista/pacientes/{pid}/atenciones", headers=h_cirujano, json=ATENCION)
    await client.patch(f"/remisiones/{rid}/retirar", headers=h_dra)
    assert (await client.post(f"/especialista/pacientes/{pid}/atenciones", headers=h_cirujano, json=ATENCION)).status_code == 404
    assert len((await client.get(f"/pacientes/{pid}/atenciones-especialistas", headers=h_dra)).json()) == 1


# ============================== borrar con la clave de autorizacion ==============================

async def _con_atencion(client, h_dra, h_cirujano, cuentas):
    pid = await _paciente(client, h_dra)
    await _remitir(client, h_dra, pid, cuentas)
    aid = (await client.post(f"/especialista/pacientes/{pid}/atenciones", headers=h_cirujano, json=ATENCION)).json()["id"]
    return pid, aid


async def test_borrar_pide_la_clave_de_autorizacion(client, h_dra, h_cirujano, cuentas):
    pid, aid = await _con_atencion(client, h_dra, h_cirujano, cuentas)
    url = f"/especialista/atenciones/{aid}"
    # la Dra. todavia no fijo su clave
    assert (await client.delete(url, headers={**h_cirujano, "X-Clave-Autorizacion": PIN})).status_code == 409
    await _fijar_pin(client, h_dra)
    assert (await client.delete(url, headers=h_cirujano)).status_code == 403                                            # sin clave
    assert (await client.delete(url, headers={**h_cirujano, "X-Clave-Autorizacion": "000000"})).status_code == 403     # equivocada
    assert (await client.delete(url, headers={**h_cirujano, "X-Clave-Autorizacion": CLAVE_DRA})).status_code == 403     # su clave de acceso no vale
    assert len((await client.get(f"/especialista/pacientes/{pid}/atenciones", headers=h_cirujano)).json()) == 1
    assert (await client.delete(url, headers={**h_cirujano, "X-Clave-Autorizacion": PIN})).status_code == 204
    assert (await client.get(f"/especialista/pacientes/{pid}/atenciones", headers=h_cirujano)).json() == []


async def test_demasiados_intentos_con_la_clave_se_bloquean(client, h_dra, h_cirujano, cuentas):
    pid, aid = await _con_atencion(client, h_dra, h_cirujano, cuentas)
    await _fijar_pin(client, h_dra)
    url = f"/especialista/atenciones/{aid}"
    for _ in range(5):
        assert (await client.delete(url, headers={**h_cirujano, "X-Clave-Autorizacion": "111111"})).status_code == 403
    # a la sexta se bloquea aunque la clave sea la correcta
    assert (await client.delete(url, headers={**h_cirujano, "X-Clave-Autorizacion": PIN})).status_code == 429


async def test_no_borra_lo_de_otro_ni_con_la_clave_correcta(client, h_dra, h_cirujano, h_endo, cuentas):
    pid, aid = await _con_atencion(client, h_dra, h_cirujano, cuentas)
    await _fijar_pin(client, h_dra)
    await _remitir(client, h_dra, pid, cuentas, "endodoncista", dientes=(14,))
    r = await client.delete(f"/especialista/atenciones/{aid}", headers={**h_endo, "X-Clave-Autorizacion": PIN})
    assert r.status_code == 404
    assert len((await client.get(f"/pacientes/{pid}/atenciones-especialistas", headers=h_dra)).json()) == 1


async def test_la_dra_borra_sin_clave(client, h_dra, h_cirujano, cuentas):
    pid, aid = await _con_atencion(client, h_dra, h_cirujano, cuentas)
    assert (await client.delete(f"/atenciones-especialistas/{aid}", headers=h_dra)).status_code == 204
    assert (await client.get(f"/pacientes/{pid}/atenciones-especialistas", headers=h_dra)).json() == []


async def test_la_clave_de_autorizacion(client, h_dra, h_asistente):
    url = "/mi-cuenta/clave-de-autorizacion"
    assert (await client.put(url, headers=h_dra, json={"pin": "12345", "clave_actual": CLAVE_DRA})).status_code == 422       # 6 digitos
    assert (await client.put(url, headers=h_dra, json={"pin": "abcdef", "clave_actual": CLAVE_DRA})).status_code == 422
    assert (await client.put(url, headers=h_dra, json={"pin": PIN, "clave_actual": "otra"})).status_code == 403              # pide la clave actual
    assert (await client.put(url, headers=h_asistente, json={"pin": PIN, "clave_actual": CLAVE_DRA})).status_code == 403    # solo la Dra.
    assert (await client.put(url, headers=h_dra, json={"pin": PIN, "clave_actual": CLAVE_DRA})).status_code == 204


# ============================== registro de accesos ==============================

async def test_la_dra_ve_quien_miro_a_su_paciente(client, h_dra, h_cirujano, cuentas):
    pid = await _paciente(client, h_dra)
    await _remitir(client, h_dra, pid, cuentas)
    await client.get(f"/especialista/pacientes/{pid}/ficha", headers=h_cirujano)
    await client.get(f"/especialista/pacientes/{pid}/odontograma", headers=h_cirujano)
    accesos = (await client.get(f"/pacientes/{pid}/accesos-especialistas", headers=h_dra)).json()
    assert {a["accion"] for a in accesos} == {"ficha", "odontograma"}
    assert all(a["usuario_nombre"] == "cirujano" for a in accesos)


async def test_listar_especialistas_para_remitir(client, h_dra):
    lista = (await client.get("/especialistas", headers=h_dra)).json()
    assert sorted(e["nombre"] for e in lista) == ["cirujano", "endodoncista"]


async def test_la_dra_puede_crear_cuentas_de_especialista(client, h_dra):
    r = await client.post(
        "/usuarios", headers=h_dra,
        json={"nombre": "periodoncista", "rol": "especialista", "password": "UnaClave#Larga2026", "email": "p@e.com", "activo": True},
    )
    assert r.status_code == 201, r.text
    assert r.json()["rol"] == "especialista"
