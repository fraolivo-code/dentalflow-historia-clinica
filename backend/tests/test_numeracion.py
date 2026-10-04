# Numeracion continua, "Paciente desde" y seguro (04/10/2026), Parte A.
# Especificacion: especificacion-tecnica-numeracion-ficha.md. Sin red ni Postgres:
# la secuencia se simula por motor (ver services/correlativos.py).

import pytest
import pytest_asyncio
from sqlalchemy import select

from app import security
from app.enums import RolUsuario
from app.models import AuditoriaUsuario, Paciente, Usuario
from app.models.common import ahora


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


def _cuerpo(**extra):
    return {
        "movil": "04141234567",
        "nombre_completo": "Paciente Prueba",
        "fecha_registro": "2026-10-05",
        **extra,
    }


async def _alta(client, h, **extra):
    return await client.post("/pacientes", headers=h, json=_cuerpo(**extra))


async def _configurar(client, h, siguiente, ancho=4):
    return await client.put(
        "/configuracion/numeracion",
        headers=h,
        json={"siguiente_numero": siguiente, "numero_ancho": ancho},
    )


# ------------------------------------------------------------ configuracion


async def test_numeracion_por_defecto(client, h_dra):
    r = await client.get("/configuracion/numeracion", headers=h_dra)
    assert r.status_code == 200
    assert r.json() == {"siguiente_numero": 1, "numero_ancho": 4, "mayor_existente": 0}


async def test_configurar_numeracion_valida_y_audita(client, h_dra, session_factory):
    r = await _configurar(client, h_dra, 458, 5)
    assert r.status_code == 200
    assert r.json() == {"siguiente_numero": 458, "numero_ancho": 5, "mayor_existente": 0}
    # leer no consume el numero
    leido = await client.get("/configuracion/numeracion", headers=h_dra)
    assert leido.json()["siguiente_numero"] == 458
    async with session_factory() as s:
        acciones = (await s.execute(select(AuditoriaUsuario.accion))).scalars().all()
    assert "numeracion_configurada" in acciones


async def test_configurar_por_debajo_o_igual_al_mayor_existente_es_409(client, h_dra):
    await _configurar(client, h_dra, 10)
    assert (await _alta(client, h_dra, numero_historia="457")).status_code == 201
    for valor in (457, 100, 1):
        r = await _configurar(client, h_dra, valor)
        assert r.status_code == 409, valor
        assert "457" in r.json()["detail"]
    assert (await _configurar(client, h_dra, 458)).status_code == 200
    leido = await client.get("/configuracion/numeracion", headers=h_dra)
    assert leido.json()["mayor_existente"] == 457


async def test_configurar_valores_invalidos_son_422(client, h_dra):
    assert (await _configurar(client, h_dra, 0)).status_code == 422
    assert (await _configurar(client, h_dra, 5, 0)).status_code == 422


async def test_asistente_no_lee_ni_configura_numeracion(client, h_asistente):
    assert (await client.get("/configuracion/numeracion", headers=h_asistente)).status_code == 403
    assert (await _configurar(client, h_asistente, 500)).status_code == 403
    assert (await client.get("/configuracion/numeracion")).status_code == 401


# --------------------------------------------------------------------- alta


async def test_alta_automatica_usa_el_ancho_configurado(client, h_dra):
    await _configurar(client, h_dra, 458, 6)
    a = await _alta(client, h_dra)
    b = await _alta(client, h_dra)
    assert (a.status_code, a.json()["numero_historia"]) == (201, "000458")
    assert b.json()["numero_historia"] == "000459"


async def test_alta_automatica_sin_configurar_empieza_en_0001(client, h_asistente):
    r = await _alta(client, h_asistente)
    assert r.json()["numero_historia"] == "0001"


async def test_alta_manual_se_normaliza_al_ancho(client, h_dra):
    r = await _alta(client, h_dra, numero_historia=" 457 ")
    assert (r.status_code, r.json()["numero_historia"]) == (201, "0457")
    # mas digitos que el ancho: se guarda tal cual
    r = await _alta(client, h_dra, numero_historia="12345")
    assert r.json()["numero_historia"] == "12345"
    # ceros de mas se recortan hasta el ancho
    r = await _alta(client, h_dra, numero_historia="000789")
    assert r.json()["numero_historia"] == "0789"


async def test_alta_manual_duplicada_es_409(client, h_dra):
    await _alta(client, h_dra, numero_historia="457")
    r = await _alta(client, h_dra, numero_historia="0457")
    assert r.status_code == 409
    assert r.json()["detail"] == "Ya existe una historia con el número 0457."
    # igual aunque cambie el ancho despues: es el mismo numero
    await _configurar(client, h_dra, 600, 6)
    assert (await _alta(client, h_dra, numero_historia="457")).status_code == 409


@pytest.mark.parametrize("valor", ["45a7", "H-12", "4 57", "-5", "0", "0000", "1" * 19])
async def test_alta_manual_invalida_es_422(client, h_dra, valor):
    assert (await _alta(client, h_dra, numero_historia=valor)).status_code == 422


async def test_alta_manual_vacia_cuenta_como_automatica(client, h_dra):
    r = await _alta(client, h_dra, numero_historia="   ")
    assert r.json()["numero_historia"] == "0001"


async def test_asistente_no_puede_fijar_el_numero(client, h_asistente, session_factory):
    r = await _alta(client, h_asistente, numero_historia="457")
    assert r.status_code == 403
    async with session_factory() as s:
        assert (await s.execute(select(Paciente))).first() is None


async def test_automatico_salta_los_numeros_cargados_a_mano(client, h_dra):
    await _configurar(client, h_dra, 10)
    for n in ("10", "11", "13"):
        assert (await _alta(client, h_dra, numero_historia=n)).status_code == 201
    a = await _alta(client, h_dra)
    b = await _alta(client, h_dra)
    assert a.json()["numero_historia"] == "0012"
    assert b.json()["numero_historia"] == "0014"


async def test_automatico_se_detiene_si_no_hay_libres(client, h_dra, monkeypatch):
    from app.services import correlativos

    monkeypatch.setattr(correlativos, "TOPE_INTENTOS", 3)
    for n in ("1", "2", "3"):
        await _alta(client, h_dra, numero_historia=n)
    r = await _alta(client, h_dra)
    assert r.status_code == 409
    assert "numeración" in r.json()["detail"]


async def test_numero_historia_no_se_edita(client, h_dra):
    creado = (await _alta(client, h_dra)).json()
    r = await client.patch(
        f"/pacientes/{creado['id']}",
        headers=h_dra,
        json={"numero_historia": "9999", "movil": "04149998888"},
    )
    assert r.status_code == 200
    assert r.json()["numero_historia"] == creado["numero_historia"]
    solo = await client.patch(
        f"/pacientes/{creado['id']}", headers=h_dra, json={"numero_historia": "9999"}
    )
    assert solo.status_code == 422  # se ignora: no queda ningun campo que corregir
    leido = await client.get(f"/pacientes/{creado['id']}", headers=h_dra)
    assert leido.json()["numero_historia"] == creado["numero_historia"]


# ------------------------------------------------------------------- seguro


async def test_seguro_se_recorta_y_vacio_es_nulo(client, h_dra):
    r = await _alta(client, h_dra, seguro="  Seguros Caracas  ")
    assert r.json()["seguro"] == "Seguros Caracas"
    assert (await _alta(client, h_dra, seguro="   ")).json()["seguro"] is None
    assert (await _alta(client, h_dra)).json()["seguro"] is None
    assert (await _alta(client, h_dra, seguro="x" * 121)).status_code == 422


async def test_seguro_se_edita_y_se_borra(client, h_dra):
    pid = (await _alta(client, h_dra)).json()["id"]
    r = await client.patch(f"/pacientes/{pid}", headers=h_dra, json={"seguro": " Mercantil "})
    assert r.json()["seguro"] == "Mercantil"
    r = await client.patch(f"/pacientes/{pid}", headers=h_dra, json={"seguro": "  "})
    assert r.json()["seguro"] is None
    assert (await client.get(f"/pacientes/{pid}", headers=h_dra)).json()["seguro"] is None


# ----------------------------------------------------------- paciente desde


async def test_paciente_desde_con_fecha_real_y_sin_ella(client, h_dra):
    con = await _alta(client, h_dra, fecha_primera_consulta_real="2009-03-15")
    sin = await _alta(client, h_dra)
    assert con.json()["paciente_desde"] == 2009
    assert sin.json()["paciente_desde"] == ahora().year
    listado = (await client.get("/pacientes", headers=h_dra)).json()
    assert sorted(p["paciente_desde"] for p in listado) == [2009, ahora().year]
    # al quitar la fecha real vuelve al anio de creacion
    r = await client.patch(
        f"/pacientes/{con.json()['id']}", headers=h_dra, json={"fecha_primera_consulta_real": None}
    )
    assert r.json()["paciente_desde"] == ahora().year
