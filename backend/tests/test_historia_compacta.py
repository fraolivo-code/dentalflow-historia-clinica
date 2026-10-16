# Historia por dia en una linea por hecho + resumen «se encontro / estado» (15/10/2026).

from datetime import date, timedelta

import pytest_asyncio

from app import security
from app.enums import RolUsuario
from app.models import Usuario

NAC = (date.today() - timedelta(days=365 * 15)).isoformat()


@pytest_asyncio.fixture
async def h(session_factory):
    async with session_factory() as s:
        u = Usuario(nombre="doctora", rol=RolUsuario.dra, password_hash="x", email="d@e.com")
        s.add(u)
        await s.commit()
        uid = u.id
    return {"Authorization": f"Bearer {security.crear_access_token(uid, 'dra')}"}


async def _paciente(client, h):
    r = await client.post(
        "/pacientes", headers=h,
        json={"movil": "04141234567", "nombre_completo": "Paciente de prueba", "fecha_registro": "2019-04-17",
              "fecha_nacimiento": NAC, "cedula": "V-12345678", "denticion": "mixta"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _hallazgo(client, h, pid, diente, tipo, fecha, superficie=None):
    r = await client.post(
        f"/pacientes/{pid}/dientes/{diente}/hallazgos", headers=h,
        json={"numero_diente": diente, "tipo_hallazgo": tipo, "superficie": superficie, "fecha": fecha},
    )
    assert r.status_code == 201, r.text


async def _realizado(client, h, pid, diente, tratamiento, fecha, **extra):
    r = await client.post(
        f"/pacientes/{pid}/dientes/{diente}/tratamiento-realizado", headers=h,
        json={"numero_diente": diente, "tratamiento": tratamiento, "fecha": fecha, **extra},
    )
    assert r.status_code == 201, r.text


async def _historia(client, h, pid):
    r = await client.get(f"/pacientes/{pid}/historia-compacta", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


async def test_el_caso_de_la_paciente_diagnostico_y_resinas(client, h):
    pid = await _paciente(client, h)
    await client.post(f"/pacientes/{pid}/visitas", headers=h, json={"fecha": "2019-04-17", "tipo": "evaluacion", "motivo_consulta": "Consulta 1ra vez"})
    for diente in (26, 55):
        await _hallazgo(client, h, pid, diente, "caries", "2019-04-17", "oclusal")
    await client.post(f"/pacientes/{pid}/visitas", headers=h, json={"fecha": "2019-04-23", "tipo": "tratamiento"})
    await _realizado(client, h, pid, 26, "restauracion", "2019-04-23", superficies=["oclusal"])
    await _realizado(client, h, pid, 55, "sellante", "2019-04-23", cierra_ids=[
        x["id"] for x in (await client.get(f"/pacientes/{pid}/dientes/55/hallazgos", headers=h)).json()])

    historia = await _historia(client, h, pid)
    dias = {d["fecha"]: d for d in historia["dias"]}
    assert list(dias) == ["2019-04-23", "2019-04-17"]  # el mas reciente primero

    diagnostico = dias["2019-04-17"]
    assert [(x["diente"], x["etiqueta"]) for x in diagnostico["hallazgos"]] == [
        (26, "Caries (oclusal)"), (55, "Caries (oclusal)")] or sorted((x["diente"], x["etiqueta"]) for x in diagnostico["hallazgos"]) == [
        (26, "Caries (oclusal)"), (55, "Caries (oclusal)")]
    assert diagnostico["realizado"] == [] and diagnostico["visitas"][0]["tipo"] == "Evaluación"

    tratamiento = dias["2019-04-23"]
    assert tratamiento["hallazgos"] == []  # lo hecho no se repite como «hallazgo»
    hechos = {x["diente"]: x for x in tratamiento["realizado"]}
    assert hechos[26]["antes"] == ["Caries (oclusal)"] and hechos[26]["despues"] == ["Obturación en buen estado (oclusal)"]
    assert hechos[55]["despues"] == ["Sellante aplicado (SELL)"]
    assert tratamiento["notas"] == []  # las entradas automaticas de bitacora no se duplican

    assert [(r["diente"], r["estado"], r["fecha_estado"]) for r in historia["resumen"]] == [
        (26, "tratado", "2019-04-23"), (55, "tratado", "2019-04-23")]


async def test_el_resumen_deja_los_pendientes_primero_y_suma_los_de_una_reevaluacion(client, h):
    pid = await _paciente(client, h)
    await _hallazgo(client, h, pid, 26, "caries", "2019-04-17", "oclusal")
    await _realizado(client, h, pid, 26, "restauracion", "2019-04-23", superficies=["oclusal"])
    await _hallazgo(client, h, pid, 16, "caries", "2019-10-20", "mesial")  # hallazgo nuevo meses despues
    resumen = (await _historia(client, h, pid))["resumen"]
    assert [(r["diente"], r["estado"]) for r in resumen] == [(16, "pendiente"), (26, "tratado")]
    assert resumen[0]["fecha_estado"] is None and resumen[1]["con"] == "Obturación en buen estado (oclusal)"


async def test_lo_quitado_a_mano_y_las_notas_escritas_se_ven(client, h):
    pid = await _paciente(client, h)
    await _hallazgo(client, h, pid, 14, "caries", "2019-04-17", "mesial")
    hallazgo = (await client.get(f"/pacientes/{pid}/odontograma", headers=h)).json()[0]["id"]
    await client.patch(f"/pacientes/{pid}/hallazgos/{hallazgo}/resolver", headers=h, json={"fecha": "2019-05-02"})
    await client.post(f"/pacientes/{pid}/bitacora", headers=h, json={"fecha": "2019-05-02", "descripcion": "Control, sin molestias", "dientes": [14]})
    historia = await _historia(client, h, pid)
    dia = next(d for d in historia["dias"] if d["fecha"] == "2019-05-02")
    assert [(q["diente"], q["etiqueta"]) for q in dia["quitados"]] == [(14, "Caries (mesial)")]
    assert [(n["dientes"], n["texto"]) for n in dia["notas"]] == [([14], "Control, sin molestias")]
    assert historia["resumen"][0]["estado"] == "quitado"


async def test_la_nota_que_escribe_la_dra_queda_en_la_linea_de_su_diente(client, h):
    pid = await _paciente(client, h)
    await _hallazgo(client, h, pid, 36, "caries", "2019-04-17", "oclusal")
    await _realizado(client, h, pid, 36, "restauracion", "2019-04-23", superficies=["oclusal"], descripcion="Resina A2, anestesia local")
    dia = next(d for d in (await _historia(client, h, pid))["dias"] if d["fecha"] == "2019-04-23")
    assert dia["realizado"][0]["nota"] == "Resina A2, anestesia local" and dia["notas"] == []


async def test_solo_la_dra_ve_la_historia_compacta(client, h, session_factory):
    pid = await _paciente(client, h)
    async with session_factory() as s:
        a = Usuario(nombre="asistente", rol=RolUsuario.asistente, password_hash="x", email="a@e.com")
        s.add(a)
        await s.commit()
        aid = a.id
    ha = {"Authorization": f"Bearer {security.crear_access_token(aid, 'asistente')}"}
    assert (await client.get(f"/pacientes/{pid}/historia-compacta", headers=ha)).status_code == 403


async def test_la_bitacora_marca_las_entradas_automaticas(client, h):
    pid = await _paciente(client, h)
    await _hallazgo(client, h, pid, 26, "caries", "2019-04-17", "oclusal")
    await _realizado(client, h, pid, 26, "restauracion", "2019-04-23", superficies=["oclusal"])  # texto automatico
    await _hallazgo(client, h, pid, 36, "caries", "2019-04-17", "oclusal")
    await _realizado(client, h, pid, 36, "restauracion", "2019-04-23", superficies=["oclusal"], descripcion="Resina A2")
    await client.post(f"/pacientes/{pid}/bitacora", headers=h, json={"fecha": "2019-05-02", "descripcion": "Control", "dientes": [26]})
    entradas = (await client.get(f"/pacientes/{pid}/bitacora", headers=h)).json()
    por_texto = {e["descripcion"][:12]: e["automatica"] for e in entradas}
    assert por_texto["Restauración"] is True and por_texto["Resina A2"] is False and por_texto["Control"] is False
