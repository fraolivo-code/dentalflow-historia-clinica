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
            "direccion_corta": "Mun. Sucre",
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
    ("GET", "/pacientes/{pid}/recetas"),
    ("POST", "/pacientes/{pid}/recetas"),
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


# ============================== recetas del especialista ==============================

LINEA = {"medicamento_nombre": "Amoxicilina 500 mg", "dosis": "1 capsula", "frecuencia": "cada 8 horas", "duracion": "7 dias"}


@pytest_asyncio.fixture
async def profesionales(session_factory, cuentas):
    from app.models import ProfesionalTratante

    async with session_factory() as s:
        s.add(ProfesionalTratante(nombre="Dra Granados", usuario_id=cuentas["doctora"], cov="1", mpps="2"))
        s.add(ProfesionalTratante(nombre="Dr Cirujano", usuario_id=cuentas["cirujano"], cov="CM-123", mpps="MS-456", direccion="Av. Principal, Caracas", telefonos="0212-5551234", correo="dr@e.com", rif="V-123"))
        await s.commit()


@pytest.fixture
def pdf_capturado(monkeypatch):
    capturado = {}

    async def _falso(plantilla, contexto):
        capturado.update(contexto, plantilla=plantilla)
        return b"%PDF-falso"

    monkeypatch.setattr("app.routers.recetas.generar_pdf", _falso)
    return capturado


async def test_el_especialista_emite_su_receta_firmada_por_el(client, h_dra, h_cirujano, cuentas, profesionales):
    pid = await _paciente(client, h_dra)
    await _remitir(client, h_dra, pid, cuentas)
    r = await client.post(f"/especialista/pacientes/{pid}/recetas", headers=h_cirujano, json={"medicamentos": [LINEA]})
    assert r.status_code == 201, r.text
    assert r.json()["medicamentos"][0]["medicamento_nombre_impreso"] == "Amoxicilina 500 mg"
    mias = (await client.get(f"/especialista/pacientes/{pid}/recetas", headers=h_cirujano)).json()
    assert [x["id"] for x in mias] == [r.json()["id"]]
    # la Dra. la ve entre las recetas del paciente
    assert [x["id"] for x in (await client.get(f"/pacientes/{pid}/recetas", headers=h_dra)).json()] == [r.json()["id"]]


async def test_sin_profesional_vinculado_no_emite(client, h_dra, h_cirujano, cuentas):
    pid = await _paciente(client, h_dra)
    await _remitir(client, h_dra, pid, cuentas)
    r = await client.post(f"/especialista/pacientes/{pid}/recetas", headers=h_cirujano, json={"medicamentos": [LINEA]})
    assert r.status_code == 409


async def test_no_receta_a_quien_no_le_remitieron_ni_con_visita_de_la_dra(client, h_dra, h_cirujano, cuentas, profesionales):
    ajeno = await _paciente(client, h_dra, "Ajeno")
    assert (await client.post(f"/especialista/pacientes/{ajeno}/recetas", headers=h_cirujano, json={"medicamentos": [LINEA]})).status_code == 404
    mio = await _paciente(client, h_dra, "Mio")
    await _remitir(client, h_dra, mio, cuentas)
    r = await client.post(
        f"/especialista/pacientes/{mio}/recetas", headers=h_cirujano,
        json={"medicamentos": [LINEA], "visita_id": str(uuid.uuid4())},
    )
    assert r.status_code == 422


async def test_solo_ve_y_descarga_sus_recetas(client, h_dra, h_cirujano, h_endo, cuentas, profesionales, pdf_capturado, session_factory):
    from app.models import ProfesionalTratante

    async with session_factory() as s:
        s.add(ProfesionalTratante(nombre="Dr Endo", usuario_id=cuentas["endodoncista"], cov="9", mpps="8"))
        await s.commit()
    pid = await _paciente(client, h_dra)
    await _remitir(client, h_dra, pid, cuentas, "cirujano")
    await _remitir(client, h_dra, pid, cuentas, "endodoncista", motivo="Endodoncia")
    rc = (await client.post(f"/especialista/pacientes/{pid}/recetas", headers=h_cirujano, json={"medicamentos": [LINEA]})).json()
    rd = (await client.post(f"/pacientes/{pid}/recetas", headers=h_dra, json={"medicamentos": [LINEA]})).json()

    assert [x["id"] for x in (await client.get(f"/especialista/pacientes/{pid}/recetas", headers=h_endo)).json()] == []
    for ajena in (rd["id"],):
        assert (await client.get(f"/especialista/pacientes/{pid}/recetas/{ajena}/pdf", headers=h_cirujano)).status_code == 404
    assert (await client.get(f"/especialista/pacientes/{pid}/recetas/{rc['id']}/pdf", headers=h_endo)).status_code == 404

    r = await client.get(f"/especialista/pacientes/{pid}/recetas/{rc['id']}/pdf", headers=h_cirujano)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert pdf_capturado["profesional"].nombre == "Dr Cirujano" and "paciente_cedula" in pdf_capturado
    assert pdf_capturado["paciente_direccion_corta"] == "Mun. Sucre"
    assert pdf_capturado["paciente_fecha_nacimiento"].isoformat() == NAC_MENOR
    assert (await client.get(f"/especialista/pacientes/{pid}/recetas/{rc['id']}/pdf-indicaciones", headers=h_cirujano)).status_code == 200


async def test_retirado_el_acceso_no_receta_ni_descarga(client, h_dra, h_cirujano, cuentas, profesionales, pdf_capturado):
    pid = await _paciente(client, h_dra)
    rem = (await _remitir(client, h_dra, pid, cuentas)).json()["id"]
    rc = (await client.post(f"/especialista/pacientes/{pid}/recetas", headers=h_cirujano, json={"medicamentos": [LINEA]})).json()
    await client.patch(f"/remisiones/{rem}/retirar", headers=h_dra)
    assert (await client.post(f"/especialista/pacientes/{pid}/recetas", headers=h_cirujano, json={"medicamentos": [LINEA]})).status_code == 404
    assert (await client.get(f"/especialista/pacientes/{pid}/recetas/{rc['id']}/pdf", headers=h_cirujano)).status_code == 404


async def test_catalogo_de_medicamentos_para_el_especialista(client, h_cirujano, h_asistente):
    assert (await client.get("/especialista/medicamentos", headers=h_cirujano)).status_code == 200
    assert (await client.get("/especialista/medicamentos", headers=h_asistente)).status_code == 403


# ============================== aviso por correo al remitir ==============================

async def test_al_remitir_se_avisa_al_especialista_sin_datos_del_paciente(client, h_dra, cuentas, monkeypatch):
    enviados = []

    async def _falso(para):
        enviados.append(para)
        return True

    monkeypatch.setattr("app.routers.remisiones.enviar_aviso_remision", _falso)
    pid = await _paciente(client, h_dra)
    r = await _remitir(client, h_dra, pid, cuentas)
    assert r.status_code == 201 and r.json()["aviso_correo"] is True
    assert enviados == ["cirujano@e.com"]
    # los listados no repiten el aviso
    assert (await client.get(f"/pacientes/{pid}/remisiones", headers=h_dra)).json()[0]["aviso_correo"] is None


async def test_si_el_correo_falla_la_remision_se_crea_igual(client, h_dra, h_cirujano, cuentas, monkeypatch):
    async def _falla(para):
        return False

    monkeypatch.setattr("app.routers.remisiones.enviar_aviso_remision", _falla)
    pid = await _paciente(client, h_dra)
    r = await _remitir(client, h_dra, pid, cuentas)
    assert r.status_code == 201 and r.json()["aviso_correo"] is False
    assert (await client.get(f"/especialista/pacientes/{pid}/ficha", headers=h_cirujano)).status_code == 200


async def test_el_texto_del_aviso_no_lleva_datos_clinicos(monkeypatch):
    from app.services import correo

    capturado = {}

    async def _enviar(para, asunto, texto, que):
        capturado.update(para=para, asunto=asunto, texto=texto)
        return True

    monkeypatch.setattr(correo, "_enviar", _enviar)
    monkeypatch.setenv("FRONTEND_URL", "https://app.ejemplo.com/")
    assert await correo.enviar_aviso_remision("dr@e.com") is True
    assert "https://app.ejemplo.com" in capturado["texto"] and "Mis pacientes" in capturado["texto"]
    assert "paciente" in capturado["texto"].lower()


async def test_correo_repetido_dice_que_cuenta_lo_tiene_y_como_resolverlo(client, h_dra, cuentas):
    base = {"rol": "especialista", "password": "UnaClave#Larga2026", "activo": True}
    a = await client.post("/usuarios", headers=h_dra, json={**base, "nombre": "esp.vieja", "email": "mismo@e.com"})
    assert a.status_code == 201, a.text
    await client.patch(f"/usuarios/{a.json()['id']}", headers=h_dra, json={"activo": False})

    r = await client.post("/usuarios", headers=h_dra, json={**base, "nombre": "esp.nueva", "email": "mismo@e.com"})
    assert r.status_code == 409
    assert "esp.vieja" in r.json()["detail"] and "inactiva" in r.json()["detail"] and "Usuarios" in r.json()["detail"]

    # Se resuelve desde la app: liberar el correo de la cuenta vieja y crear la nueva.
    assert (await client.patch(f"/usuarios/{a.json()['id']}", headers=h_dra, json={"email": "otro@e.com"})).status_code == 200
    assert (await client.post("/usuarios", headers=h_dra, json={**base, "nombre": "esp.nueva", "email": "mismo@e.com"})).status_code == 201


# ============================== consulta del puente de correo ==============================

TOKEN_PUENTE = "t" * 40


async def test_el_puente_pregunta_si_un_correo_es_de_un_usuario_activo(client, h_dra, cuentas, monkeypatch):
    monkeypatch.setenv("CORREO_PUENTE_TOKEN", TOKEN_PUENTE)
    ok = {"X-Puente-Token": TOKEN_PUENTE}

    async def pregunta(email, headers=ok):
        return await client.get("/interno/correo-permitido", params={"email": email}, headers=headers)

    assert (await pregunta("cirujano@e.com")).json() == {"permitido": True}
    assert (await pregunta("  CIRUJANO@E.COM ")).json() == {"permitido": True}          # normaliza
    assert (await pregunta("nadie@e.com")).json() == {"permitido": False}
    # una cuenta inactiva ya no recibe avisos
    await client.patch(f"/usuarios/{cuentas['cirujano']}", headers=h_dra, json={"activo": False})
    assert (await pregunta("cirujano@e.com")).json() == {"permitido": False}


async def test_la_consulta_del_puente_exige_su_clave(client, cuentas, monkeypatch):
    monkeypatch.setenv("CORREO_PUENTE_TOKEN", TOKEN_PUENTE)
    ruta = "/interno/correo-permitido"
    assert (await client.get(ruta, params={"email": "cirujano@e.com"})).status_code == 401
    assert (await client.get(ruta, params={"email": "cirujano@e.com"}, headers={"X-Puente-Token": "otra"})).status_code == 401
    # sin clave configurada en el servidor, nadie entra (ni con encabezado vacio)
    monkeypatch.delenv("CORREO_PUENTE_TOKEN")
    assert (await client.get(ruta, params={"email": "cirujano@e.com"}, headers={"X-Puente-Token": ""})).status_code == 401
    assert (await client.get(ruta, params={"email": "cirujano@e.com"}, headers={"X-Puente-Token": TOKEN_PUENTE})).status_code == 401


# ============================== membrete del profesional (migracion 0039) ==============================

async def test_no_se_emite_receta_sin_cov_y_mpps(client, h_dra, h_cirujano, cuentas, session_factory):
    from app.models import ProfesionalTratante

    async with session_factory() as s:
        s.add(ProfesionalTratante(nombre="Dr Sin Datos", usuario_id=cuentas["cirujano"], cov="123"))   # falta el MPPS
        await s.commit()
    pid = await _paciente(client, h_dra)
    await _remitir(client, h_dra, pid, cuentas)
    r = await client.post(f"/especialista/pacientes/{pid}/recetas", headers=h_cirujano, json={"medicamentos": [LINEA]})
    assert r.status_code == 409 and "MPPS" in r.json()["detail"]
    # lo completa el mismo y ya puede emitir
    assert (await client.patch("/especialista/mi-perfil", headers=h_cirujano, json={"mpps": " 456 "})).json()["mpps"] == "456"
    assert (await client.post(f"/especialista/pacientes/{pid}/recetas", headers=h_cirujano, json={"medicamentos": [LINEA]})).status_code == 201


async def test_la_dra_corrige_el_membrete_de_un_profesional_y_la_asistente_no(client, h_dra, h_asistente, profesionales):
    lista = (await client.get("/profesionales-tratantes", headers=h_dra)).json()
    prof = next(p for p in lista if p["nombre"] == "Dr Cirujano")
    assert prof["cov"] == "CM-123" and prof["rif"] == "V-123" and prof["direccion"] == "Av. Principal, Caracas"
    r = await client.patch(f"/profesionales-tratantes/{prof['id']}", headers=h_dra, json={"nombre": "Dr. Cirujano Prueba", "telefonos": "  ", "rif": "J-9"})
    assert r.status_code == 200 and r.json()["nombre"] == "Dr. Cirujano Prueba" and r.json()["telefonos"] is None and r.json()["rif"] == "J-9"
    assert r.json()["cov"] == "CM-123"                      # lo que no viene no cambia
    assert (await client.patch(f"/profesionales-tratantes/{prof['id']}", headers=h_dra, json={"nombre": "  "})).status_code == 422
    assert (await client.patch(f"/profesionales-tratantes/{prof['id']}", headers=h_asistente, json={"rif": "x"})).status_code == 403


async def test_el_especialista_solo_ve_y_edita_su_propio_perfil(client, h_dra, h_cirujano, h_endo, cuentas, profesionales):
    mio = (await client.get("/especialista/mi-perfil", headers=h_cirujano)).json()
    assert mio["nombre"] == "Dr Cirujano" and mio["cov"] == "CM-123"
    assert (await client.get("/especialista/mi-perfil", headers=h_endo)).status_code == 409      # no tiene profesional vinculado
    assert (await client.get("/especialista/mi-perfil", headers=h_dra)).status_code == 403
    # el cirujano cambia el suyo; el de la Dra. no se toca
    assert (await client.patch("/especialista/mi-perfil", headers=h_cirujano, json={"especialidad": "Cirugía bucal"})).json()["especialidad"] == "Cirugía bucal"
    dra = next(p for p in (await client.get("/profesionales-tratantes", headers=h_dra)).json() if p["nombre"] == "Dra Granados")
    assert dra["especialidad"] is None


def test_el_membrete_y_el_paciente_salen_en_el_recipe():
    from types import SimpleNamespace

    from app.services import pdf as servicio_pdf

    prof = SimpleNamespace(
        nombre="OD Martha Fernandez", especialidad="Cirugía bucal", direccion="Av. Francisco de Miranda, Los Ruices",
        telefonos="(+58-212) 237.4468", correo="m@e.com", rif="V-1", cov="7747", mpps="8353", numero_colegiatura=None,
    )
    plantilla = servicio_pdf._plantillas.get_template("receta.html")
    html = plantilla.render(
        profesional=prof, paciente_nombre="Paciente Ficticio", paciente_cedula="V-4022837",
        paciente_fecha_nacimiento=date(1990, 3, 4), paciente_direccion_corta="Mun. Sucre",
        fecha=date(2026, 10, 20), medicamentos=[], notas_generales=None, ciudad="Caracas",
    )
    for texto in ("OD Martha Fernandez", "Cirugía bucal", "Los Ruices", "Telf.: (+58-212) 237.4468", "m@e.com",
                  "RIF: V-1 · COV: 7747 · MPPS: 8353", "COV: 7747 · MPPS: 8353", "V-4022837",
                  "4 de marzo de 1990", "Mun. Sucre"):
        assert texto in html, texto


def test_recipe_e_indicaciones_son_media_carta_en_mitades_opuestas_de_una_hoja_carta_horizontal():
    from types import SimpleNamespace

    from app.services import pdf as servicio_pdf

    prof = SimpleNamespace(nombre="OD X", especialidad=None, direccion=None, telefonos=None, correo=None, rif=None,
                           cov="1", mpps="2", numero_colegiatura=None)
    contexto = dict(profesional=prof, paciente_nombre="P", paciente_cedula=None, paciente_fecha_nacimiento=None,
                    paciente_direccion_corta=None, fecha=date(2026, 10, 20), medicamentos=[], notas_generales=None)
    recipe = servicio_pdf._plantillas.get_template("receta.html").render(**contexto)
    indicaciones = servicio_pdf._plantillas.get_template("indicaciones_medicamentos.html").render(**contexto)
    for html in (recipe, indicaciones):
        assert "size: 11in 8.5in" in html            # Carta horizontal
    for html in (recipe, indicaciones):
        assert "position: running(firma)" in html and "element(firma)" in html     # firma fija al pie
    assert "margin-right: 430pt" in recipe and "margin-left: 430pt" not in recipe          # recipe: mitad izquierda
    assert "margin-left: 430pt" in indicaciones and "margin-right: 430pt" not in indicaciones  # indicaciones: mitad derecha
