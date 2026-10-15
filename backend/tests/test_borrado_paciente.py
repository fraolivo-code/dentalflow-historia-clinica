# Borrado de un paciente de prueba con todo lo que depende de el (procedimiento aparte, no hay
# ruta en la API). Ver app/services/borrado_paciente.py y scripts/borrar_paciente.py.

from datetime import date as _date, timedelta as _timedelta

NAC_MENOR = (_date.today() - _timedelta(days=365 * 5)).isoformat()

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app import security
from app.enums import RolUsuario
from app.models import (
    BitacoraDiente,
    BitacoraTratamiento,
    ExamenSolicitado,
    OdontogramaHallazgo,
    Paciente,
    PacienteCambio,
    ProfesionalTratante,
    Tratamiento,
    Usuario,
    Visita,
    VisitaTratamiento,
)
from app.services import borrado_paciente


@pytest_asyncio.fixture
async def usuario_dra(session_factory):
    async with session_factory() as s:
        u = Usuario(nombre="doctora", rol=RolUsuario.dra, password_hash="x", email="d@e.com")
        s.add(u)
        await s.commit()
        return u.id


@pytest.fixture
def h_dra(usuario_dra):
    return {"Authorization": f"Bearer {security.crear_access_token(usuario_dra, 'dra')}"}


async def _paciente(client, h, nombre):
    r = await client.post(
        "/pacientes",
        headers=h,
        json={"movil": "04141234567", "nombre_completo": nombre, "fecha_registro": "2026-10-05", "fecha_nacimiento": NAC_MENOR},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _historia_completa(client, h, pid):
    """Visita de tratamiento, hallazgos, restauracion, bitacora y examen."""
    prof = await client.post("/profesionales-tratantes", headers=h, json={"nombre": f"Dra. {pid[:4]}"})
    trat = (
        await client.post(
            f"/pacientes/{pid}/tratamientos", headers=h,
            json={"tipo": "Endodoncia", "fecha_inicio": "2026-09-01", "profesional_tratante_id": prof.json()["id"], "dientes": [11]},
        )
    ).json()["id"]
    await client.post(f"/pacientes/{pid}/visitas", headers=h, json={"fecha": "2026-10-01", "tipo": "tratamiento", "tratamiento_ids": [trat]})
    await client.post(
        f"/pacientes/{pid}/dientes/22/hallazgos", headers=h,
        json={"numero_diente": 22, "tipo_hallazgo": "caries", "superficie": "oclusal", "fecha": "2026-10-01"},
    )
    await client.post(
        f"/pacientes/{pid}/dientes/22/tratamiento-realizado", headers=h,
        json={"numero_diente": 22, "tratamiento": "restauracion", "fecha": "2026-10-10", "superficies": ["oclusal"]},
    )
    await client.post(f"/pacientes/{pid}/examenes", headers=h, json={"tipo": "tomografia", "fecha_indicacion": "2026-10-12"})
    await client.patch(f"/pacientes/{pid}", headers=h, json={"movil": "04149998888"})


async def _contar(session_factory, modelo):
    async with session_factory() as s:
        return (await s.execute(select(func.count()).select_from(modelo))).scalar_one()


async def test_ensayo_cuenta_sin_borrar(client, h_dra, session_factory):
    pid = await _paciente(client, h_dra, "Paciente de PRUEBA")
    await _historia_completa(client, h_dra, pid)
    async with session_factory() as s:
        cuentas = await borrado_paciente.contar(s, (await s.execute(select(Paciente.id))).scalar_one())
    assert cuentas["paciente"] == 1 and cuentas["visita"] == 1 and cuentas["tratamiento"] == 1
    assert cuentas["examen_solicitado"] == 1 and cuentas["visita_tratamiento"] == 1
    assert cuentas["odontograma_hallazgo"] == 2  # caries (resuelta) + obturacion
    assert cuentas["bitacora_tratamiento"] == 1 and cuentas["bitacora_diente"] == 1
    assert await _contar(session_factory, Paciente) == 1  # nada se borro


async def test_borra_todo_lo_del_paciente_y_respeta_al_otro(client, h_dra, session_factory):
    a = await _paciente(client, h_dra, "Paciente de prueba A")
    b = await _paciente(client, h_dra, "Paciente real B")
    await _historia_completa(client, h_dra, a)
    await _historia_completa(client, h_dra, b)
    antes = {m: await _contar(session_factory, m) for m in (Visita, OdontogramaHallazgo, ExamenSolicitado, Tratamiento)}

    async with session_factory() as s:
        borradas = await borrado_paciente.borrar(s, __import__("uuid").UUID(a))
    assert borradas["paciente"] == 1 and borradas["visita"] == 1 and borradas["odontograma_hallazgo"] == 2

    # El paciente A no queda con nada; el B conserva exactamente lo suyo.
    async with session_factory() as s:
        quedan = (await s.execute(select(Paciente.nombre_completo))).scalars().all()
    assert quedan == ["Paciente real B"]
    for modelo, n in antes.items():
        assert await _contar(session_factory, modelo) == n // 2, modelo
    for modelo in (VisitaTratamiento, BitacoraTratamiento, BitacoraDiente, PacienteCambio):
        async with session_factory() as s:
            assert (await s.execute(select(func.count()).select_from(modelo))).scalar_one() <= 1, modelo
    # el profesional (no es hijo del paciente) sigue existiendo
    assert await _contar(session_factory, ProfesionalTratante) == 2


async def test_busca_el_paciente_por_valor_del_numero(client, h_dra, session_factory):
    await _paciente(client, h_dra, "Paciente de prueba")
    async with session_factory() as s:
        numero = (await s.execute(select(Paciente.numero_historia))).scalar_one()
        encontrado = await borrado_paciente.buscar_por_historia(s, str(int(numero)))
        assert encontrado is not None and encontrado.numero_historia == numero
        assert await borrado_paciente.buscar_por_historia(s, "99999") is None
        assert await borrado_paciente.buscar_por_historia(s, "abc") is None
