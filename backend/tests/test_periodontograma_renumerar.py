# Correccion del numero de diente de un periodontograma ya guardado (05/10/2026).

import sqlalchemy as sa
from test_nivel_insercion import _visita, h_dra  # noqa: F401  (fixture + helper)

SITIOS = ["mesiovestibular", "vestibular", "distovestibular",
          "distopalatino_lingual", "palatino_lingual", "mesiopalatino_lingual"]


async def _cargar(client, h, vid, diente, furcacion=None):
    registros = [{"numero_diente": diente, "sitio": s, "margen_gingival": -3, "profundidad_sondaje": 4}
                 for s in SITIOS]
    resumen = {"numero_diente": diente, "movilidad": 1}
    if furcacion:
        resumen["furcacion"] = furcacion
    r = await client.post(f"/visitas/{vid}/periodontograma", headers=h,
                          json={"registros": registros, "resumenes": [resumen]})
    assert r.status_code == 201, r.text


def _url(vid, diente):
    return f"/visitas/{vid}/periodontograma/dientes/{diente}"


async def test_mueve_los_6_sitios_y_el_resumen_al_diente_correcto(client, h_dra):
    _, vid = await _visita(client, h_dra)
    await _cargar(client, h_dra, vid, 13)
    r = await client.patch(_url(vid, 13), headers=h_dra, json={"numero_diente": 11})
    assert r.status_code == 200, r.text
    assert len(r.json()["registros"]) == 6 and len(r.json()["resumenes"]) == 1
    leido = (await client.get(f"/visitas/{vid}/periodontograma", headers=h_dra)).json()
    assert {x["numero_diente"] for x in leido["registros"]} == {11}
    assert {x["numero_diente"] for x in leido["resumenes"]} == {11}
    assert all(x["nivel_insercion"] == 7 and x["actualizado_en"] for x in leido["registros"])  # valores intactos


async def test_rechaza_destino_ocupado_igual_invalido_y_sin_datos(client, h_dra):
    _, vid = await _visita(client, h_dra)
    await _cargar(client, h_dra, vid, 11)
    # el 12 no se puede cargar en la misma visita (una carga por visita): se prueba contra el propio 11.
    assert (await client.patch(_url(vid, 11), headers=h_dra, json={"numero_diente": 11})).status_code == 422
    assert (await client.patch(_url(vid, 11), headers=h_dra, json={"numero_diente": 99})).status_code == 422
    assert (await client.patch(_url(vid, 12), headers=h_dra, json={"numero_diente": 13})).status_code == 404


async def test_rechaza_destino_con_medicion_en_la_visita(client, h_dra, session_factory):
    from app.models.periodontograma import PeriodontogramaDienteResumen
    _, vid = await _visita(client, h_dra)
    await _cargar(client, h_dra, vid, 11)
    async with session_factory() as s:
        resumen = (await s.execute(sa.select(PeriodontogramaDienteResumen))).scalars().one()
        s.add(PeriodontogramaDienteResumen(paciente_id=resumen.paciente_id, visita_id=resumen.visita_id,
                                           numero_diente=13, movilidad=0, creado_por=resumen.creado_por))
        await s.commit()
    r = await client.patch(_url(vid, 11), headers=h_dra, json={"numero_diente": 13})
    assert r.status_code == 409
    leido = (await client.get(f"/visitas/{vid}/periodontograma", headers=h_dra)).json()
    assert {x["numero_diente"] for x in leido["registros"]} == {11}  # nada se movio


async def test_rechaza_si_la_furcacion_no_cabe_en_el_diente_nuevo(client, h_dra):
    _, vid = await _visita(client, h_dra)
    await _cargar(client, h_dra, vid, 16, furcacion="I")
    r = await client.patch(_url(vid, 16), headers=h_dra, json={"numero_diente": 11})
    assert r.status_code == 422 and "furcacion" in r.text
    # un molar a otro molar si
    assert (await client.patch(_url(vid, 16), headers=h_dra, json={"numero_diente": 17})).status_code == 200


# --- eliminar el periodontograma de la visita (paciente equivocado) -----------------


async def test_eliminar_exige_confirmacion_y_deja_copia_en_el_historial(client, h_dra):
    pid, vid = await _visita(client, h_dra)
    await _cargar(client, h_dra, vid, 11)
    url = f"/visitas/{vid}/periodontograma"
    assert (await client.delete(url, headers=h_dra)).status_code == 422
    assert (await client.delete(url + "?confirmar=eliminar", headers=h_dra)).status_code == 422
    assert len((await client.get(url, headers=h_dra)).json()["registros"]) == 6  # nada se borro

    assert (await client.delete(url + "?confirmar=ELIMINAR", headers=h_dra)).status_code == 204
    assert (await client.get(url, headers=h_dra)).json() == {"registros": [], "resumenes": []}
    assert (await client.delete(url + "?confirmar=ELIMINAR", headers=h_dra)).status_code == 404

    cambios = (await client.get(f"/pacientes/{pid}/cambios", headers=h_dra)).json()
    borrado = [c for c in cambios if c["etiqueta"] == "Periodontograma eliminado"]
    assert len(borrado) == 1 and "11:" in borrado[0]["valor_anterior"] and "MG-3 PS4" in borrado[0]["valor_anterior"]
    # la visita queda libre para cargar de nuevo
    await _cargar(client, h_dra, vid, 13)
