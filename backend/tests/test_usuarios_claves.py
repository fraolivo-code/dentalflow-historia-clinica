# Etapa 7, Parte A: gestion de usuarios y contrasenas (sin red y sin Postgres).
# Especificacion: especificacion-tecnica-usuarios-contrasenas.md, A.7.
# Los correos de recuperacion se interceptan: nunca se llama al puente real.

import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import httpx
import jwt
import pytest
import pytest_asyncio
from sqlalchemy import select

from app import security
from app.deps import get_session
from app.enums import RolUsuario
from app.main import app
from app.models import AuditoriaUsuario, TokenRecuperacion, Usuario
from app.routers import auth as auth_router
from app.services import auditoria, correo
from app.services.passwords import generar_temporal, validar_password

CLAVE_DRA = "clave-de-la-doctora-1"
CLAVE_ASISTENTE = "clave-de-la-asistente-1"
MENSAJE_RECHAZO = auth_router.MENSAJE_LOGIN_RECHAZADO


@pytest.fixture(autouse=True)
def bcrypt_rapido(monkeypatch):
    """bcrypt con 4 rondas: el costo real (12) haria lenta la suite sin cambiar la logica."""
    original = bcrypt.gensalt
    monkeypatch.setattr(security.bcrypt, "gensalt", lambda *a, **k: original(rounds=4))


@pytest.fixture(autouse=True)
def reiniciar_purga(monkeypatch):
    monkeypatch.setattr(auditoria, "_ultima_purga", None)


@pytest_asyncio.fixture
async def api(session_factory):
    """Cliente HTTP con la base de tests; sin la clave de servicio de Alma."""

    async def _get_session():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_session] = _get_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def correos(monkeypatch):
    """Intercepta el envio: guarda (para, token) en vez de llamar al puente."""
    enviados: list[tuple[str, str]] = []

    async def _falso(para: str, token: str) -> bool:
        enviados.append((para, token))
        return True

    monkeypatch.setattr(correo, "enviar_recuperacion", _falso)
    return enviados


@pytest_asyncio.fixture
async def crear(session_factory):
    async def _crear(nombre, rol=RolUsuario.asistente, password=CLAVE_ASISTENTE, **extra) -> uuid.UUID:
        async with session_factory() as s:
            u = Usuario(
                nombre=nombre,
                rol=rol,
                password_hash=security.hash_password(password),
                **extra,
            )
            s.add(u)
            await s.commit()
            return u.id

    return _crear


@pytest_asyncio.fixture
async def dra(crear):
    return await crear(
        "doctora", RolUsuario.dra, CLAVE_DRA, email="doctora@ejemplo.com"
    )


@pytest_asyncio.fixture
async def leer(session_factory):
    async def _leer(modelo, **filtros):
        async with session_factory() as s:
            consulta = select(modelo)
            for campo, valor in filtros.items():
                consulta = consulta.where(getattr(modelo, campo) == valor)
            return (await s.execute(consulta)).scalars().all()

    return _leer


async def _login(api, nombre, password):
    return await api.post("/auth/login", json={"nombre": nombre, "password": password})


async def _headers(api, nombre="doctora", password=CLAVE_DRA):
    r = await _login(api, nombre, password)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _token_con_iat(usuario_id, iat_segundos_atras: int, sub=None) -> str:
    ahora = int(time.time())
    payload = {"iat": ahora - iat_segundos_atras, "exp": ahora + 3600, "rol": "dra"}
    payload["sub"] = str(usuario_id) if sub is None else sub
    return jwt.encode(payload, security.JWT_SECRET_KEY, algorithm=security.JWT_ALGORITHM)


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------- reglas A.2


def test_clave_corta():
    assert "al menos 10" in validar_password("123456789")
    assert validar_password("1234567890") is None


def test_clave_maximo_72_bytes():
    assert validar_password("a" * 72) is None
    assert "demasiado larga" in validar_password("a" * 73)
    # 37 caracteres pero 74 bytes en UTF-8
    assert "demasiado larga" in validar_password("ñ" * 37)


def test_clave_igual_a_nombre_o_correo_sin_distinguir_mayusculas():
    assert "nombre de usuario" in validar_password("DoctoraGranados", nombre="doctoragranados")
    assert "correo" in validar_password("Doctora@Ejemplo.COM", nombre="otra", email="doctora@ejemplo.com")
    assert validar_password("una-clave-distinta", nombre="doctora", email="d@e.com") is None


def test_temporal_cumple_las_reglas():
    for _ in range(50):
        assert validar_password(generar_temporal()) is None


# ------------------------------------------------------------- login y bloqueo


async def test_login_sin_distinguir_mayusculas_ni_espacios(api, dra, leer):
    r = await _login(api, "  DoCtora ", CLAVE_DRA)
    assert r.status_code == 200
    (u,) = await leer(Usuario, id=dra)
    assert u.ultimo_login is not None


async def test_mensaje_unico_en_todos_los_rechazos(api, dra, crear, session_factory):
    await crear("inactiva", activo=False)
    casos = [
        ("doctora", "clave-equivocada-1"),  # clave mala
        ("no-existe", CLAVE_DRA),  # usuario inexistente
        ("inactiva", CLAVE_ASISTENTE),  # cuenta inactiva
    ]
    for nombre, clave in casos:
        r = await _login(api, nombre, clave)
        assert r.status_code == 401
        assert r.json()["detail"] == MENSAJE_RECHAZO
    for _ in range(5):
        await _login(api, "doctora", "clave-equivocada-1")
    r = await _login(api, "doctora", CLAVE_DRA)  # ahora bloqueada
    assert r.status_code == 401
    assert r.json()["detail"] == MENSAJE_RECHAZO


async def test_bloqueo_al_quinto_intento_y_desbloqueo_a_los_15_minutos(
    api, dra, leer, monkeypatch
):
    reloj = {"ahora": datetime.now(timezone.utc)}
    monkeypatch.setattr(auth_router, "ahora", lambda: reloj["ahora"])

    for _ in range(4):
        r = await _login(api, "doctora", "clave-equivocada-1")
        assert r.status_code == 401
    (u,) = await leer(Usuario, id=dra)
    assert u.intentos_fallidos == 4 and u.bloqueado_hasta is None
    # Hasta el 4.o intento la clave correcta todavia entra... y reinicia el contador.
    r = await _login(api, "doctora", CLAVE_DRA)
    assert r.status_code == 200
    (u,) = await leer(Usuario, id=dra)
    assert u.intentos_fallidos == 0

    for _ in range(5):
        await _login(api, "doctora", "clave-equivocada-1")
    (u,) = await leer(Usuario, id=dra)
    assert u.bloqueado_hasta is not None and u.intentos_fallidos == 0
    assert (await _login(api, "doctora", CLAVE_DRA)).status_code == 401  # bloqueada

    reloj["ahora"] += timedelta(minutes=14)
    assert (await _login(api, "doctora", CLAVE_DRA)).status_code == 401
    reloj["ahora"] += timedelta(minutes=2)  # 16 min en total
    assert (await _login(api, "doctora", CLAVE_DRA)).status_code == 200
    (u,) = await leer(Usuario, id=dra)
    assert u.bloqueado_hasta is None and u.intentos_fallidos == 0


async def test_listado_muestra_bloqueado_calculado(api, dra, crear):
    otra = await crear("asistente.uno", email=None)
    h = await _headers(api)
    for _ in range(5):
        await _login(api, "asistente.uno", "clave-equivocada-1")
    r = await api.get(f"/usuarios/{otra}", headers=h)
    assert r.json()["bloqueado"] is True
    r = await api.get("/usuarios", headers=h)
    por_nombre = {u["nombre"]: u for u in r.json()}
    assert por_nombre["doctora"]["bloqueado"] is False
    assert por_nombre["doctora"]["ultimo_login"] is not None
    assert {"email", "activo", "debe_cambiar_clave"} <= set(por_nombre["doctora"])


# ------------------------------------------------------------ sesiones (JWT)


async def test_token_anterior_a_clave_cambiada_en_es_rechazado(api, dra, session_factory):
    viejo = _token_con_iat(dra, 120)
    assert (await api.get("/auth/me", headers=_bearer(viejo))).status_code == 200
    async with session_factory() as s:
        u = await s.get(Usuario, dra)
        u.clave_cambiada_en = datetime.now(timezone.utc) - timedelta(seconds=60)
        await s.commit()
    assert (await api.get("/auth/me", headers=_bearer(viejo))).status_code == 401
    nuevo = _token_con_iat(dra, 0)
    assert (await api.get("/auth/me", headers=_bearer(nuevo))).status_code == 200


@pytest.mark.parametrize("sub", ["no-es-un-uuid", 12345, None])
async def test_sub_invalido_da_401_no_500(api, sub):
    ahora = int(time.time())
    payload = {"iat": ahora, "exp": ahora + 3600}
    if sub is not None:
        payload["sub"] = sub
    token = jwt.encode(payload, security.JWT_SECRET_KEY, algorithm=security.JWT_ALGORITHM)
    assert (await api.get("/auth/me", headers=_bearer(token))).status_code == 401


async def test_usuario_inactivo_pierde_la_sesion(api, dra, crear, session_factory):
    otra = await crear("asistente.dos")
    h = await _headers(api, "asistente.dos", CLAVE_ASISTENTE)
    assert (await api.get("/auth/me", headers=h)).status_code == 200
    async with session_factory() as s:
        (await s.get(Usuario, otra)).activo = False
        await s.commit()
    assert (await api.get("/auth/me", headers=h)).status_code == 401


# --------------------------------------------------- cambio obligatorio y cambiar-clave


async def test_cambio_obligatorio_bloquea_todo_salvo_me_y_cambiar_clave(api, crear):
    await crear("nueva.dra", RolUsuario.dra, CLAVE_DRA, email="n@e.com", debe_cambiar_clave=True)
    h = await _headers(api, "nueva.dra")

    for ruta in ("/pacientes", "/usuarios", "/medicamentos"):
        r = await api.get(ruta, headers=h)
        assert r.status_code == 403, ruta
        assert r.json()["detail"]["codigo"] == "debe_cambiar_clave"

    r = await api.get("/auth/me", headers=h)
    assert r.status_code == 200 and r.json()["debe_cambiar_clave"] is True

    r = await api.post(
        "/auth/cambiar-clave",
        headers=h,
        json={"clave_actual": CLAVE_DRA, "clave_nueva": "otra-clave-bien-larga"},
    )
    assert r.status_code == 200

    h2 = _bearer(r.json()["access_token"])
    assert (await api.get("/pacientes", headers=h2)).status_code == 200
    assert (await api.get("/auth/me", headers=h2)).json()["debe_cambiar_clave"] is False


async def test_cambiar_clave_devuelve_token_nuevo_y_el_viejo_deja_de_servir(api, dra, leer):
    viejo = _token_con_iat(dra, 120)
    r = await api.post(
        "/auth/cambiar-clave",
        headers=_bearer(viejo),
        json={"clave_actual": CLAVE_DRA, "clave_nueva": "clave-nueva-larga-1"},
    )
    assert r.status_code == 200
    nuevo = r.json()["access_token"]
    assert (await api.get("/auth/me", headers=_bearer(nuevo))).status_code == 200
    assert (await api.get("/auth/me", headers=_bearer(viejo))).status_code == 401
    assert (await _login(api, "doctora", CLAVE_DRA)).status_code == 401
    assert (await _login(api, "doctora", "clave-nueva-larga-1")).status_code == 200
    (u,) = await leer(Usuario, id=dra)
    assert u.clave_cambiada_en is not None


async def test_cambiar_clave_valida_actual_reglas_y_distinta(api, dra):
    h = await _headers(api)

    def _pedido(actual, nueva):
        return api.post(
            "/auth/cambiar-clave", headers=h, json={"clave_actual": actual, "clave_nueva": nueva}
        )

    r = await _pedido("no-es-la-actual-1", "clave-nueva-larga-1")
    assert r.status_code == 400 and "actual no es correcta" in r.json()["detail"]
    assert r.json()["detail"] == auth_router.MENSAJE_CAMBIAR_CLAVE_RECHAZADO
    r = await _pedido(CLAVE_DRA, "corta")
    assert r.status_code == 422 and "al menos 10" in r.json()["detail"]
    r = await _pedido(CLAVE_DRA, "doctora@ejemplo.com")
    assert r.status_code == 422 and "correo" in r.json()["detail"]
    r = await _pedido(CLAVE_DRA, CLAVE_DRA)
    assert r.status_code == 422 and "distinta de la actual" in r.json()["detail"]


async def test_cambiar_clave_incorrecta_suma_al_mismo_contador_y_bloquea(
    api, dra, leer, monkeypatch
):
    reloj = {"ahora": datetime.now(timezone.utc)}
    monkeypatch.setattr(auth_router, "ahora", lambda: reloj["ahora"])
    h = await _headers(api)

    def _cambiar(actual):
        return api.post(
            "/auth/cambiar-clave",
            headers=h,
            json={"clave_actual": actual, "clave_nueva": "clave-nueva-larga-1"},
        )

    # 2 fallos por cambiar-clave + 2 por login = 4 en el mismo contador.
    for _ in range(2):
        assert (await _cambiar("no-es-la-actual-1")).status_code == 400
    for _ in range(2):
        await _login(api, "doctora", "clave-equivocada-1")
    (u,) = await leer(Usuario, id=dra)
    assert u.intentos_fallidos == 4 and u.bloqueado_hasta is None

    # El 5.o intento (por cambiar-clave) bloquea la cuenta.
    assert (await _cambiar("no-es-la-actual-1")).status_code == 400
    (u,) = await leer(Usuario, id=dra)
    assert u.bloqueado_hasta is not None and u.intentos_fallidos == 0

    # Bloqueada: cambiar-clave rechaza incluso con la clave actual correcta...
    r = await _cambiar(CLAVE_DRA)
    assert r.status_code == 400
    assert r.json()["detail"] == auth_router.MENSAJE_CAMBIAR_CLAVE_RECHAZADO
    # ...y el login tambien.
    assert (await _login(api, "doctora", CLAVE_DRA)).status_code == 401

    # Auditoria: login_fallido con detalle "cambiar-clave" (sin claves ni nombres).
    filas = await leer(AuditoriaUsuario, accion="login_fallido", detalle="cambiar-clave")
    assert len(filas) == 4  # 3 por clave incorrecta + 1 con la cuenta ya bloqueada
    assert all(f.actor_id == dra and f.usuario_objetivo_id == dra for f in filas)
    assert len(await leer(AuditoriaUsuario, accion="cuenta_bloqueada")) == 1

    # A los 15 minutos vuelve a funcionar y la clave cambia.
    reloj["ahora"] += timedelta(minutes=16)
    assert (await _cambiar(CLAVE_DRA)).status_code == 200
    assert (await _login(api, "doctora", "clave-nueva-larga-1")).status_code == 200


async def test_cambiar_clave_correcta_reinicia_el_contador(api, dra, leer):
    h = await _headers(api)
    for _ in range(3):
        await api.post(
            "/auth/cambiar-clave",
            headers=h,
            json={"clave_actual": "no-es-la-actual-1", "clave_nueva": "clave-nueva-larga-1"},
        )
    r = await api.post(
        "/auth/cambiar-clave",
        headers=h,
        json={"clave_actual": CLAVE_DRA, "clave_nueva": "clave-nueva-larga-1"},
    )
    assert r.status_code == 200
    (u,) = await leer(Usuario, id=dra)
    assert u.intentos_fallidos == 0


# ------------------------------------------------------------------- olvide-clave


async def _olvide(api, email):
    return await api.post("/auth/olvide-clave", json={"email": email})


async def test_olvide_misma_respuesta_con_correo_existente_inexistente_e_inactivo(
    api, dra, crear, correos
):
    await crear("inactiva.dra", RolUsuario.dra, email="inactiva@ejemplo.com", activo=False)
    respuestas = [
        await _olvide(api, "DOCTORA@ejemplo.com "),
        await _olvide(api, "nadie@ejemplo.com"),
        await _olvide(api, "inactiva@ejemplo.com"),
        await _olvide(api, ""),
    ]
    assert {r.status_code for r in respuestas} == {200}
    assert len({r.text for r in respuestas}) == 1
    assert [para for para, _ in correos] == ["doctora@ejemplo.com"]


async def test_olvide_limite_de_3_por_hora(api, dra, correos, leer):
    for _ in range(5):
        assert (await _olvide(api, "doctora@ejemplo.com")).status_code == 200
    assert len(correos) == 3
    assert len(await leer(TokenRecuperacion, usuario_id=dra)) == 3


async def test_token_guarda_solo_el_hash_y_vence_a_los_30_minutos(api, dra, correos, leer):
    await _olvide(api, "doctora@ejemplo.com")
    _, token = correos[0]
    (reg,) = await leer(TokenRecuperacion, usuario_id=dra)
    assert reg.token_hash != token and len(reg.token_hash) == 64
    assert token not in repr(reg.__dict__)
    vigencia = reg.expira_en.replace(tzinfo=timezone.utc) - reg.creado_en.replace(tzinfo=timezone.utc)
    assert abs(vigencia - timedelta(minutes=30)) < timedelta(seconds=5)


async def test_token_de_un_solo_uso(api, dra, correos):
    await _olvide(api, "doctora@ejemplo.com")
    _, token = correos[0]
    r = await api.post(
        "/auth/restablecer-clave", json={"token": token, "clave_nueva": "clave-restablecida-1"}
    )
    assert r.status_code == 200
    r = await api.post(
        "/auth/restablecer-clave", json={"token": token, "clave_nueva": "clave-restablecida-2"}
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "El enlace no es válido o ya venció. Solicite uno nuevo."


async def test_token_vencido_e_inexistente(api, dra, correos, session_factory):
    await _olvide(api, "doctora@ejemplo.com")
    _, token = correos[0]
    async with session_factory() as s:
        reg = (await s.execute(select(TokenRecuperacion))).scalar_one()
        reg.expira_en = datetime.now(timezone.utc) - timedelta(seconds=1)
        await s.commit()
    for t in (token, "token-que-no-existe"):
        r = await api.post(
            "/auth/restablecer-clave", json={"token": t, "clave_nueva": "clave-restablecida-1"}
        )
        assert r.status_code == 400


async def test_un_pedido_nuevo_invalida_el_enlace_anterior(api, dra, correos):
    await _olvide(api, "doctora@ejemplo.com")
    await _olvide(api, "doctora@ejemplo.com")
    primero, segundo = correos[0][1], correos[1][1]
    r = await api.post(
        "/auth/restablecer-clave", json={"token": primero, "clave_nueva": "clave-restablecida-1"}
    )
    assert r.status_code == 400
    r = await api.post(
        "/auth/restablecer-clave", json={"token": segundo, "clave_nueva": "clave-restablecida-1"}
    )
    assert r.status_code == 200


async def test_restablecer_actualiza_todo(api, crear, correos, leer):
    uid = await crear(
        "bloqueada",
        RolUsuario.dra,
        CLAVE_DRA,
        email="b@ejemplo.com",
        debe_cambiar_clave=True,
        intentos_fallidos=3,
        bloqueado_hasta=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    viejo = _token_con_iat(uid, 120)
    await _olvide(api, "b@ejemplo.com")
    _, token = correos[0]

    # Clave que no cumple las reglas: 422 y el enlace NO se consume.
    r = await api.post("/auth/restablecer-clave", json={"token": token, "clave_nueva": "corta"})
    assert r.status_code == 422
    r = await api.post(
        "/auth/restablecer-clave", json={"token": token, "clave_nueva": "clave-restablecida-1"}
    )
    assert r.status_code == 200

    (u,) = await leer(Usuario, id=uid)
    assert u.debe_cambiar_clave is False and u.intentos_fallidos == 0
    assert u.bloqueado_hasta is None and u.clave_cambiada_en is not None
    (reg,) = await leer(TokenRecuperacion, usuario_id=uid)
    assert reg.usado_en is not None
    assert (await _login(api, "bloqueada", "clave-restablecida-1")).status_code == 200
    assert (await _login(api, "bloqueada", CLAVE_DRA)).status_code == 401
    assert (await api.get("/auth/me", headers=_bearer(viejo))).status_code == 401


# --------------------------------------------------------------------- POST /usuarios


def _nuevo(**extra):
    base = {"nombre": "Asistente.Nueva", "rol": "asistente", "password": "clave-inicial-larga"}
    return {**base, **extra}


async def test_crear_usuario(api, dra, leer):
    h = await _headers(api)
    r = await api.post("/usuarios", headers=h, json=_nuevo(email=" Nueva@Ejemplo.COM "))
    assert r.status_code == 201
    cuerpo = r.json()
    assert cuerpo["nombre"] == "asistente.nueva" and cuerpo["email"] == "nueva@ejemplo.com"
    assert cuerpo["debe_cambiar_clave"] is True and "password" not in cuerpo
    (u,) = await leer(Usuario, nombre="asistente.nueva")
    assert u.creado_por == dra and u.password_hash != "clave-inicial-larga"
    # La clave inicial sirve para entrar (y obliga a cambiarla).
    assert (await _login(api, "ASISTENTE.nueva", "clave-inicial-larga")).status_code == 200


async def test_crear_usuario_validaciones(api, dra, crear):
    h = await _headers(api)
    await api.post("/usuarios", headers=h, json=_nuevo(email="uno@ejemplo.com"))

    r = await api.post("/usuarios", headers=h, json=_nuevo(nombre="ASISTENTE.NUEVA"))
    assert r.status_code == 409 and "nombre" in r.json()["detail"]
    r = await api.post("/usuarios", headers=h, json=_nuevo(nombre="otra", email="UNO@ejemplo.com"))
    assert r.status_code == 409 and "correo" in r.json()["detail"]
    r = await api.post("/usuarios", headers=h, json=_nuevo(nombre="adm", rol="admin"))
    assert r.status_code == 422 and "dra y asistente" in r.json()["detail"]
    r = await api.post("/usuarios", headers=h, json=_nuevo(nombre="sin.correo", rol="dra"))
    assert r.status_code == 422 and "obligatorio" in r.json()["detail"]
    r = await api.post("/usuarios", headers=h, json=_nuevo(nombre="corta", password="123456789"))
    assert r.status_code == 422 and "al menos 10" in r.json()["detail"]
    r = await api.post(
        "/usuarios", headers=h, json=_nuevo(nombre="mismoNombreLargo", password="MISMONOMBRELARGO")
    )
    assert r.status_code == 422 and "nombre de usuario" in r.json()["detail"]
    r = await api.post("/usuarios", headers=h, json=_nuevo(nombre="mal", email="no-es-correo"))
    assert r.status_code == 422 and "formato" in r.json()["detail"]


async def test_asistente_no_puede_gestionar_usuarios(api, dra, crear):
    await crear("asistente.tres")
    h = await _headers(api, "asistente.tres", CLAVE_ASISTENTE)
    assert (await api.get("/usuarios", headers=h)).status_code == 403
    assert (await api.post("/usuarios", headers=h, json=_nuevo())).status_code == 403
    assert (await api.patch(f"/usuarios/{dra}", headers=h, json={"activo": False})).status_code == 403
    assert (await api.post(f"/usuarios/{dra}/reiniciar-clave", headers=h)).status_code == 403


# -------------------------------------------------------------------- PATCH /usuarios


async def test_patch_protecciones_sobre_si_mismo(api, dra):
    h = await _headers(api)
    r = await api.patch(f"/usuarios/{dra}", headers=h, json={"activo": False})
    assert r.status_code == 409 and "propia cuenta" in r.json()["detail"]
    r = await api.patch(f"/usuarios/{dra}", headers=h, json={"rol": "asistente"})
    assert r.status_code == 409 and "propio tipo de acceso" in r.json()["detail"]
    # Cambiar su propio correo si se puede.
    r = await api.patch(f"/usuarios/{dra}", headers=h, json={"email": "nuevo@ejemplo.com"})
    assert r.status_code == 200 and r.json()["email"] == "nuevo@ejemplo.com"


async def test_patch_desactivar_cambiar_rol_y_correo_con_auditoria(api, dra, crear, leer):
    otra = await crear("asistente.cuatro", email="a4@ejemplo.com")
    h = await _headers(api)

    r = await api.patch(f"/usuarios/{otra}", headers=h, json={"activo": False})
    assert r.status_code == 200 and r.json()["activo"] is False
    r = await api.patch(f"/usuarios/{otra}", headers=h, json={"activo": True, "rol": "dra"})
    assert r.status_code == 200 and r.json()["rol"] == "dra"
    r = await api.patch(f"/usuarios/{otra}", headers=h, json={"email": "A4-NUEVO@ejemplo.com"})
    assert r.json()["email"] == "a4-nuevo@ejemplo.com"
    r = await api.patch(f"/usuarios/{otra}", headers=h, json={"rol": "admin"})
    assert r.status_code == 422
    r = await api.patch(f"/usuarios/{otra}", headers=h, json={"email": "doctora@ejemplo.com"})
    assert r.status_code == 409
    r = await api.patch(f"/usuarios/{otra}", headers=h, json={"email": None})
    assert r.status_code == 422  # ahora es dra: el correo es obligatorio
    r = await api.patch(f"/usuarios/{uuid.uuid4()}", headers=h, json={"activo": False})
    assert r.status_code == 404

    acciones = [a.accion for a in await leer(AuditoriaUsuario, usuario_objetivo_id=otra)]
    assert {"usuario_desactivado", "usuario_activado", "rol_cambiado", "email_cambiado"} <= set(acciones)


async def test_patch_pasar_asistente_a_dra_exige_correo(api, dra, crear):
    sin_correo = await crear("asistente.sin.correo")
    h = await _headers(api)
    r = await api.patch(f"/usuarios/{sin_correo}", headers=h, json={"rol": "dra"})
    assert r.status_code == 422 and "obligatorio" in r.json()["detail"]
    r = await api.patch(
        f"/usuarios/{sin_correo}", headers=h, json={"rol": "dra", "email": "s@ejemplo.com"}
    )
    assert r.status_code == 200


async def test_desactivar_a_otro_dra_corta_su_sesion(api, dra, crear):
    otra = await crear("segunda.dra", RolUsuario.dra, CLAVE_DRA, email="s@ejemplo.com")
    h_otra = await _headers(api, "segunda.dra")
    h = await _headers(api)
    assert (await api.patch(f"/usuarios/{otra}", headers=h, json={"activo": False})).status_code == 200
    assert (await api.get("/auth/me", headers=h_otra)).status_code == 401


async def test_nunca_queda_sin_cuenta_activa_con_acceso_total(session_factory, dra, crear):
    from app.routers.usuarios import quedaria_sin_acceso_total

    asistente = await crear("solo.asistente")
    async with session_factory() as s:
        # Con una sola dra activa, quitarle el acceso dejaria a cero.
        assert await quedaria_sin_acceso_total(s, await s.get(Usuario, dra)) is True
        # Quitar a una asistente no afecta: la dra sigue activa.
        assert await quedaria_sin_acceso_total(s, await s.get(Usuario, asistente)) is False
    segunda = await crear("segunda.dra", RolUsuario.dra, CLAVE_DRA, email="s@ejemplo.com")
    async with session_factory() as s:
        assert await quedaria_sin_acceso_total(s, await s.get(Usuario, dra)) is False
    async with session_factory() as s:
        (await s.get(Usuario, segunda)).activo = False  # inactiva: no cuenta
        await s.commit()
    async with session_factory() as s:
        assert await quedaria_sin_acceso_total(s, await s.get(Usuario, dra)) is True


# ------------------------------------------------------------------ reiniciar-clave


async def test_reiniciar_clave_devuelve_temporal_una_vez_y_fuerza_el_cambio(
    api, dra, crear, leer, caplog
):
    otra = await crear(
        "asistente.cinco",
        intentos_fallidos=4,
        bloqueado_hasta=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    viejo = _token_con_iat(otra, 120)
    h = await _headers(api)

    with caplog.at_level(logging.DEBUG):
        r = await api.post(f"/usuarios/{otra}/reiniciar-clave", headers=h)
    assert r.status_code == 200
    temporal = r.json()["password_temporal"]
    assert validar_password(temporal) is None
    assert r.headers["cache-control"] == "no-store"
    assert temporal not in caplog.text

    (u,) = await leer(Usuario, id=otra)
    assert u.debe_cambiar_clave is True and u.bloqueado_hasta is None and u.intentos_fallidos == 0
    # La temporal no se guarda en claro y la lectura posterior no la incluye.
    assert temporal not in u.password_hash
    assert "password_temporal" not in (await api.get(f"/usuarios/{otra}", headers=h)).json()

    assert (await api.get("/auth/me", headers=_bearer(viejo))).status_code == 401
    assert (await _login(api, "asistente.cinco", CLAVE_ASISTENTE)).status_code == 401
    h_nueva = await _headers(api, "asistente.cinco", temporal)
    r = await api.get("/pacientes", headers=h_nueva)
    assert r.status_code == 403 and r.json()["detail"]["codigo"] == "debe_cambiar_clave"
    assert (await api.post("/usuarios/" + str(uuid.uuid4()) + "/reiniciar-clave", headers=h)).status_code == 404


# ------------------------------------------------------------------------ auditoria


async def test_auditoria_registra_acciones_sin_secretos(api, dra, crear, correos, leer):
    nombre_tipeado = "nombre-escrito-en-login-fallido"
    clave_mala = "clave-mala-que-no-debe-guardarse"
    await _login(api, nombre_tipeado, clave_mala)  # usuario inexistente
    for _ in range(5):
        await _login(api, "doctora", clave_mala)  # fallidos y bloqueo
    h_dra = _bearer(_token_con_iat(dra, 0))
    clave_inicial = "clave-inicial-secreta-1"
    r = await api.post("/usuarios", headers=h_dra, json=_nuevo(password=clave_inicial))
    otra = r.json()["id"]
    r = await api.post(f"/usuarios/{otra}/reiniciar-clave", headers=h_dra)
    temporal = r.json()["password_temporal"]
    await _olvide(api, "doctora@ejemplo.com")
    _, token = correos[0]
    await api.post(
        "/auth/restablecer-clave", json={"token": token, "clave_nueva": "clave-restablecida-1"}
    )
    h = await _headers(api, "doctora", "clave-restablecida-1")
    await api.post(
        "/auth/cambiar-clave",
        headers=h,
        json={"clave_actual": "clave-restablecida-1", "clave_nueva": "clave-final-larga-1"},
    )

    filas = await leer(AuditoriaUsuario)
    acciones = {f.accion for f in filas}
    assert {
        "login_ok",
        "login_fallido",
        "cuenta_bloqueada",
        "usuario_creado",
        "clave_reiniciada",
        "recuperacion_solicitada",
        "clave_restablecida",
        "clave_cambiada",
    } <= acciones
    texto = " ".join(f"{f.accion} {f.detalle or ''}" for f in filas)
    for prohibido in (
        nombre_tipeado,
        clave_mala,
        clave_inicial,
        temporal,
        token,
        "clave-restablecida-1",
        "clave-final-larga-1",
        CLAVE_DRA,
    ):
        assert prohibido not in texto
    # El login a un usuario inexistente queda sin actor ni objetivo.
    sin_objetivo = [f for f in filas if f.accion == "login_fallido" and f.usuario_objetivo_id is None]
    assert len(sin_objetivo) == 1 and sin_objetivo[0].actor_id is None


async def test_purga_de_auditoria_y_tokens(session_factory, dra):
    ahora = datetime.now(timezone.utc)
    async with session_factory() as s:
        s.add_all(
            [
                AuditoriaUsuario(accion="vieja", fecha=ahora - timedelta(days=366)),
                AuditoriaUsuario(accion="reciente", fecha=ahora - timedelta(days=364)),
                TokenRecuperacion(
                    usuario_id=dra, token_hash="a" * 64, expira_en=ahora - timedelta(days=8)
                ),
                TokenRecuperacion(
                    usuario_id=dra, token_hash="b" * 64, expira_en=ahora - timedelta(days=1)
                ),
                TokenRecuperacion(
                    usuario_id=dra,
                    token_hash="c" * 64,
                    expira_en=ahora + timedelta(minutes=5),
                    usado_en=ahora - timedelta(days=8),
                ),
                TokenRecuperacion(
                    usuario_id=dra, token_hash="d" * 64, expira_en=ahora + timedelta(minutes=5)
                ),
            ]
        )
        await s.commit()
    async with session_factory() as s:
        assert await auditoria.purgar_si_corresponde(s, ahora) is True
        assert await auditoria.purgar_si_corresponde(s, ahora) is False  # una vez al dia
    async with session_factory() as s:
        acciones = (await s.execute(select(AuditoriaUsuario.accion))).scalars().all()
        hashes = (await s.execute(select(TokenRecuperacion.token_hash))).scalars().all()
    assert acciones == ["reciente"]
    assert sorted(hashes) == ["b" * 64, "d" * 64]


# ----------------------------------------------------------- correo por el puente


async def test_correo_no_configurado_no_falla(monkeypatch, caplog):
    for var in ("CORREO_PUENTE_URL", "CORREO_PUENTE_TOKEN", "FRONTEND_URL"):
        monkeypatch.delenv(var, raising=False)
    with caplog.at_level(logging.WARNING):
        assert await correo.enviar_recuperacion("a@ejemplo.com", "tok") is False
    assert "faltan" in caplog.text and "tok" not in caplog.text.replace("token", "")


async def test_correo_contrato_del_puente_con_redireccion(monkeypatch):
    monkeypatch.setenv("CORREO_PUENTE_URL", "https://puente.invalido/exec")
    monkeypatch.setenv("CORREO_PUENTE_TOKEN", "t" * 40)
    monkeypatch.setenv("FRONTEND_URL", "https://front.invalido/")
    monkeypatch.setenv("NOMBRE_PRODUCTO", "DentalFlow")
    recibido = {}

    def manejador(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            recibido["json"] = request.read().decode("utf-8")
            return httpx.Response(302, headers={"Location": "https://puente.invalido/final"})
        return httpx.Response(200, json={"ok": True, "error": None})

    real = httpx.AsyncClient
    monkeypatch.setattr(
        correo.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(manejador), **kw)
    )
    assert await correo.enviar_recuperacion("d@ejemplo.com", "TOKEN123") is True
    cuerpo = json.loads(recibido["json"])
    assert cuerpo["para"] == "d@ejemplo.com" and cuerpo["token"] == "t" * 40
    assert cuerpo["asunto"] == "Restablecer su contraseña — DentalFlow"
    assert "https://front.invalido/restablecer?token=TOKEN123" in cuerpo["texto"]
    assert "30 minutos" in cuerpo["texto"] and "ignore este mensaje" in cuerpo["texto"]


async def test_correo_rechazado_o_con_error_devuelve_false_sin_filtrar_el_token(monkeypatch, caplog):
    monkeypatch.setenv("CORREO_PUENTE_URL", "https://puente.invalido/exec")
    monkeypatch.setenv("CORREO_PUENTE_TOKEN", "t" * 40)
    monkeypatch.setenv("FRONTEND_URL", "https://front.invalido")
    real = httpx.AsyncClient

    def rechaza(request):
        return httpx.Response(200, json={"ok": False, "error": "destinatario_no_permitido"})

    def falla(request):
        raise httpx.ConnectError("sin red https://puente.invalido/exec")

    for manejador in (rechaza, falla):
        monkeypatch.setattr(
            correo.httpx,
            "AsyncClient",
            lambda manejador=manejador, **kw: real(transport=httpx.MockTransport(manejador), **kw),
        )
        with caplog.at_level(logging.ERROR):
            assert await correo.enviar_recuperacion("d@ejemplo.com", "TOKEN-SECRETO") is False
    assert "TOKEN-SECRETO" not in caplog.text and "puente.invalido" not in caplog.text
    assert "ConnectError" in caplog.text


async def test_olvide_responde_igual_con_el_puente_sin_configurar(api, dra, monkeypatch):
    # Sin el puente configurado no se envia nada, pero la respuesta es la misma.
    for var in ("CORREO_PUENTE_URL", "CORREO_PUENTE_TOKEN", "FRONTEND_URL"):
        monkeypatch.delenv(var, raising=False)
    r = await _olvide(api, "doctora@ejemplo.com")
    assert r.status_code == 200
    assert r.json()["mensaje"] == auth_router.MENSAJE_OLVIDE_CLAVE
