# Flujo de visitas, fase 4 (15/10/2026): linea de tiempo del paciente y de un diente.
# Especificacion: especificacion-tecnica-flujo-visitas-tratamientos.md, seccion 9.

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


async def _linea(client, h, pid, diente=None):
    url = f"/pacientes/{pid}/linea-de-tiempo" + (f"?diente={diente}" if diente else "")
    r = await client.get(url, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


async def test_paciente_sin_historia_devuelve_lista_vacia(client, h_dra):
    pid = await _paciente(client, h_dra)
    assert await _linea(client, h_dra, pid) == []


async def test_mezcla_visita_bitacora_hallazgos_y_examenes_de_mas_reciente_a_mas_antiguo(client, h_dra):
    pid = await _paciente(client, h_dra)
    await client.post(
        f"/pacientes/{pid}/visitas", headers=h_dra,
        json={"fecha": "2026-10-01", "tipo": "evaluacion", "motivo_consulta": "Me duele el 22"},
    )
    await _marca(client, h_dra, pid, 22, "caries", "oclusal", fecha="2026-10-01")
    await client.post(
        f"/pacientes/{pid}/dientes/22/tratamiento-realizado", headers=h_dra,
        json={"numero_diente": 22, "tratamiento": "restauracion", "fecha": "2026-10-10", "superficies": ["oclusal"]},
    )
    ex = (await client.post(f"/pacientes/{pid}/examenes", headers=h_dra, json={"tipo": "tomografia", "fecha_indicacion": "2026-10-12"})).json()
    await client.patch(f"/examenes/{ex['id']}/traido", headers=h_dra, json={"fecha_traido": "2026-10-14", "hallazgos": "Sin lesión"})

    eventos = await _linea(client, h_dra, pid)
    fechas = [e["fecha"] for e in eventos]
    assert fechas == sorted(fechas, reverse=True)
    titulos = [e["titulo"] for e in eventos]
    assert "Examen traído: Tomografía" in titulos
    assert "Examen indicado: Tomografía" in titulos
    assert "Visita — Evaluación" in titulos
    assert any(t.startswith("Se resolvió: Caries") for t in titulos)
    assert any(t.startswith("Se marcó: Obturación en buen estado") for t in titulos)
    assert "Bitácora" in titulos  # «Tratamiento realizado» deja una entrada
    traido = next(e for e in eventos if e["tipo"] == "examen_traido")
    assert traido["detalle"] == "Sin lesión"
    visita = next(e for e in eventos if e["tipo"] == "visita")
    assert visita["detalle"] == "Me duele el 22"


async def test_la_resolucion_dice_por_quien_fue_reemplazada(client, h_dra):
    pid = await _paciente(client, h_dra)
    await _marca(client, h_dra, pid, 22, "caries", "oclusal", fecha="2026-10-01")
    await client.post(
        f"/pacientes/{pid}/dientes/22/tratamiento-realizado", headers=h_dra,
        json={"numero_diente": 22, "tratamiento": "restauracion", "fecha": "2026-10-10", "superficies": ["oclusal"]},
    )
    resuelto = next(e for e in await _linea(client, h_dra, pid) if e["tipo"] == "hallazgo_resuelto")
    assert resuelto["fecha"] == "2026-10-10"
    assert "Reemplazado por Obturación en buen estado" in resuelto["detalle"]
    assert "marcado el 01/10/2026" in resuelto["detalle"]


async def test_filtro_por_diente_solo_trae_lo_de_ese_diente(client, h_dra):
    pid = await _paciente(client, h_dra)
    await client.post(f"/pacientes/{pid}/visitas", headers=h_dra, json={"fecha": "2026-10-01"})
    await _marca(client, h_dra, pid, 22, "caries", "oclusal")
    await _marca(client, h_dra, pid, 36, "caries", "mesial")
    await client.post(f"/pacientes/{pid}/bitacora", headers=h_dra, json={"fecha": "2026-10-02", "descripcion": "Limpieza del 36", "dientes": [36]})
    await client.post(f"/pacientes/{pid}/bitacora", headers=h_dra, json={"fecha": "2026-10-03", "descripcion": "Resina 22", "dientes": [22]})
    await client.post(f"/pacientes/{pid}/examenes", headers=h_dra, json={"tipo": "rx_panoramica", "fecha_indicacion": "2026-10-04"})

    e22 = await _linea(client, h_dra, pid, 22)
    assert {e["tipo"] for e in e22} == {"hallazgo", "bitacora"}
    assert all(22 in e["dientes"] for e in e22)
    assert [e["detalle"] for e in e22 if e["tipo"] == "bitacora"] == ["Resina 22"]
    # sin filtro aparecen la visita, los dos dientes y el examen
    todos = {e["tipo"] for e in await _linea(client, h_dra, pid)}
    assert {"visita", "hallazgo", "bitacora", "examen_indicado"} <= todos


async def test_tratamiento_con_dientes_y_su_cierre(client, h_dra):
    pid = await _paciente(client, h_dra)
    prof = await client.post("/profesionales-tratantes", headers=h_dra, json={"nombre": "Dra. X"})
    t = (
        await client.post(
            f"/pacientes/{pid}/tratamientos", headers=h_dra,
            json={"tipo": "Endodoncia", "fecha_inicio": "2026-09-01", "profesional_tratante_id": prof.json()["id"], "dientes": [11]},
        )
    ).json()
    await client.patch(f"/tratamientos/{t['id']}", headers=h_dra, json={"estado": "completado", "fecha_fin": "2026-09-20"})
    e11 = await _linea(client, h_dra, pid, 11)
    assert [(e["tipo"], e["fecha"]) for e in e11] == [("tratamiento_fin", "2026-09-20"), ("tratamiento_inicio", "2026-09-01")]
    assert e11[0]["titulo"] == "Completado: Endodoncia"
    assert await _linea(client, h_dra, pid, 36) == []  # otro diente: nada


async def test_validaciones_y_permisos(client, h_dra, h_asistente):
    pid = await _paciente(client, h_dra)
    assert (await client.get(f"/pacientes/{pid}/linea-de-tiempo?diente=99", headers=h_dra)).status_code == 400
    assert (await client.get(f"/pacientes/{pid}/linea-de-tiempo", headers=h_asistente)).status_code == 403
    assert (await client.get("/pacientes/00000000-0000-0000-0000-000000000000/linea-de-tiempo", headers=h_dra)).status_code == 404
