from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import ConsultaVinculacion, Paciente
from app.services import vinculacion as servicio

REG = "/interno/vinculacion/registrado"
VER = "/interno/vinculacion/verificar"


# ── Clave de servicio ────────────────────────────────────────────────────────
async def test_sin_variable_responde_503(client, headers, monkeypatch):
    monkeypatch.delenv("VINCULACION_API_KEY")
    r = await client.post(REG, json={"telefono": "04141234567"}, headers=headers)
    assert r.status_code == 503


async def test_clave_corta_responde_503(client, monkeypatch):
    monkeypatch.setenv("VINCULACION_API_KEY", "corta")
    r = await client.post(REG, json={"telefono": "1"}, headers={"X-Api-Key": "corta"})
    assert r.status_code == 503


async def test_sin_cabecera_o_incorrecta_responde_401(client):
    assert (await client.post(REG, json={"telefono": "04141234567"})).status_code == 401
    r = await client.post(REG, json={"telefono": "04141234567"}, headers={"X-Api-Key": "x" * 40})
    assert r.status_code == 401


async def test_clave_no_abre_otros_endpoints(client, headers):
    r = await client.get("/pacientes", headers=headers)
    assert r.status_code == 401


# ── registrado ───────────────────────────────────────────────────────────────
async def test_registrado_si_y_no_en_distintos_formatos(client, headers, crear_paciente):
    await crear_paciente("María Pérez", "0414-123.45.67")
    for tel in ("584141234567", "+58 414 1234567", "04141234567"):
        r = await client.post(REG, json={"telefono": tel}, headers=headers)
        assert r.json() == {"registrado": True}
    r = await client.post(REG, json={"telefono": "584249999999"}, headers=headers)
    assert r.json() == {"registrado": False}
    r = await client.post(REG, json={"telefono": "basura"}, headers=headers)
    assert r.json() == {"registrado": False}


async def test_paciente_extranjero_no_participa(client, headers, crear_paciente):
    await crear_paciente("John Smith", "+1 305 555 1234")
    r = await client.post(REG, json={"telefono": "+1 305 555 1234"}, headers=headers)
    assert r.json() == {"registrado": False}


async def test_edicion_de_movil_recalcula(session_factory, crear_paciente):
    pid = await crear_paciente("María Pérez", "04141234567")
    async with session_factory() as s:
        p = await s.get(Paciente, pid)
        assert p.movil_normalizado == "584141234567"
        p.movil = "0424-7654321"
        await s.commit()
    async with session_factory() as s:
        assert (await s.get(Paciente, pid)).movil_normalizado == "584247654321"


# ── verificar ────────────────────────────────────────────────────────────────
async def test_verificar_coincidencia_y_respuesta_minima(client, headers, crear_paciente):
    await crear_paciente("María José Pérez", "04141234567")
    tel = "584141234567"
    r = await client.post(VER, json={"telefono": tel, "nombre": "soy MARIA"}, headers=headers)
    assert r.json() == {"coincide": True, "nombre_saludo": "María"}
    r = await client.post(VER, json={"telefono": tel, "nombre": "María Pérez"}, headers=headers)
    assert r.json()["coincide"] is True
    r = await client.post(VER, json={"telefono": tel, "nombre": "María Rojas"}, headers=headers)
    assert r.json() == {"coincide": False}
    r = await client.post(VER, json={"telefono": tel, "nombre": "Mari"}, headers=headers)
    assert r.json() == {"coincide": False}


async def test_verificar_numero_no_registrado(client, headers):
    r = await client.post(
        VER, json={"telefono": "584141234567", "nombre": "María"}, headers=headers
    )
    assert r.json() == {"coincide": False}


async def test_verificar_dos_pacientes_mismo_nombre(client, headers, crear_paciente):
    await crear_paciente("Pedro Díaz", "04141234567")
    await crear_paciente("Pedro Pérez", "04141234567")
    tel = "584141234567"
    r = await client.post(
        VER, json={"telefono": tel, "nombre": "es para mi hijo Pedro"}, headers=headers
    )
    assert r.json() == {"coincide": False, "pedir_apellido": True}
    r = await client.post(VER, json={"telefono": tel, "nombre": "Pedro Pérez"}, headers=headers)
    assert r.json() == {"coincide": True, "nombre_saludo": "Pedro"}


# ── registro de consultas y purga ────────────────────────────────────────────
async def test_registro_sin_nombre_escrito(client, headers, crear_paciente, session_factory):
    await crear_paciente("María Pérez", "04141234567")
    await client.post(REG, json={"telefono": "04141234567"}, headers=headers)
    await client.post(
        VER, json={"telefono": "04141234567", "nombre": "SecretoUnico"}, headers=headers
    )
    await client.post(VER, json={"telefono": "04141234567", "nombre": "María"}, headers=headers)
    async with session_factory() as s:
        filas = (
            (await s.execute(select(ConsultaVinculacion).order_by(ConsultaVinculacion.fecha)))
            .scalars()
            .all()
        )
    assert [(f.endpoint, f.resultado) for f in filas] == [
        ("registrado", "registrado"),
        ("verificar", "no_coincide"),
        ("verificar", "coincide"),
    ]
    assert {f.movil_normalizado for f in filas} == {"584141234567"}
    columnas = {c.name for c in ConsultaVinculacion.__table__.columns}
    assert columnas == {"id", "fecha", "endpoint", "movil_normalizado", "resultado"}
    assert all("SecretoUnico" not in str(vars(f)) for f in filas)


async def test_purga_de_90_dias(session_factory, monkeypatch):
    monkeypatch.setattr(servicio, "_ultima_purga", None)
    ahora = datetime(2026, 10, 2, tzinfo=timezone.utc)
    async with session_factory() as s:
        for dias, tag in ((91, "vieja"), (89, "reciente")):
            s.add(
                ConsultaVinculacion(
                    fecha=ahora - timedelta(days=dias),
                    endpoint="registrado",
                    movil_normalizado=None,
                    resultado=tag,
                )
            )
        await s.commit()
        assert await servicio.purgar_si_corresponde(s, ahora) == 1
        # Una vez al dia: la segunda llamada no hace nada.
        assert await servicio.purgar_si_corresponde(s, ahora + timedelta(hours=1)) is None
        restantes = (await s.execute(select(ConsultaVinculacion.resultado))).scalars().all()
    assert restantes == ["reciente"]
    # 25 h despues vuelve a correr, y el "reciente" (89 dias) ya pasó los 90.
    async with session_factory() as s:
        assert await servicio.purgar_si_corresponde(s, ahora + timedelta(hours=25)) == 1
