# Odontograma anatomico (05/10/2026), Parte A: superficie palatino_lingual y
# dibujo de los PDF desde dientes_anatomicos.json.
# Especificacion: especificacion-tecnica-odontograma-anatomico.md.
#
# El SVG se parsea como XML: cada diente es <g data-diente="N"> y cada vista
# <g data-vista="vestibular|oclusal|palatina|lingual">. WeasyPrint no se usa
# (generar_pdf se sustituye por el render de la plantilla).

import importlib.util
import pathlib
import re
import xml.etree.ElementTree as ET
from types import SimpleNamespace as NS

import pytest
import pytest_asyncio

from app import security
from app.enums import (
    EstadoGeneralPuente,
    RolDientePuente,
    RolUsuario,
    SuperficieDental,
    TipoHallazgo,
    TipoLesionApical,
    validar_superficie,
)
from app.models import Usuario
from app.services import etiquetas
from app.services import odontograma_impreso as impreso
from app.services import odontograma_svg as odo
from app.services import pdf as servicio_pdf
from app.services.odontograma_svg import MODO_BLANCO, MODO_COLOR, MODO_GRIS, odontograma_svg

JSON = odo.cargar_formas()
COLORES = JSON["colores"]
AZUL, ROJO = COLORES["azul"], COLORES["rojo"]
HEX = re.compile(r"#[0-9a-fA-F]{6}\b")
VERSIONES = pathlib.Path(__file__).parent.parent / "alembic" / "versions"
SUPERFICIES = [s.value for s in SuperficieDental]


# ------------------------------------------------------------------ utilidades


def _h(numero, tipo, superficie=None):
    return NS(numero_diente=numero, tipo_hallazgo=TipoHallazgo(tipo),
              superficie=SuperficieDental(superficie) if superficie else None, resuelto=False)


def _lesion(numero, raiz, tipo=TipoLesionApical.periapical):
    return NS(numero_diente=numero, tipo=tipo, raiz=raiz)


def _tag(el):
    return el.tag.split("}")[-1]


def _dibujo(hallazgos=(), lesiones=(), puentes=(), modo=MODO_COLOR):
    return ET.fromstring(str(odontograma_svg(list(hallazgos), list(lesiones), list(puentes), {}, modo)))


def _diente(svg, numero):
    return next(g for g in svg.iter() if _tag(g) == "g" and g.get("data-diente") == str(numero))


def _vista(svg, numero, vista):
    return next(g for g in _diente(svg, numero).iter() if g.get("data-vista") == vista)


def _con(el, tag=None, **atributos):
    """Descendientes de `el` con ese tag y esos atributos (fill, stroke, ...)."""
    return [
        e for e in el.iter()
        if (tag is None or _tag(e) == tag) and all(e.get(k.replace("_", "-")) == v for k, v in atributos.items())
    ]


def _rojos(el):
    return _con(el, fill=ROJO)


def _forma(numero):
    return JSON["formas"][JSON["dientes"][str(numero)]["forma"]]


def _ancho_y_cervical(numero):
    f = _forma(numero)
    return f["ancho"], f["cervical"]


# ============================================================ JSON / catalogo


def _semilla_catalogo():
    spec = importlib.util.spec_from_file_location("mig0001", VERSIONES / "0001_initial_schema.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return {fila["numero_diente"]: fila["nombres_raices"] for fila in mod.DIENTE_ANATOMIA_SEED}


def test_json_version_y_cantidades():
    assert JSON["version"] == "2026-10-06.1"
    assert len(JSON["dientes"]) == 32
    raices = sum(len(_forma(int(n))["raices"]) for n in JSON["dientes"])
    assert raices == 52


def test_nombres_de_raices_del_json_coinciden_con_el_catalogo():
    catalogo = _semilla_catalogo()
    assert sorted(catalogo) == sorted(int(n) for n in JSON["dientes"])
    assert sum(len(v) for v in catalogo.values()) == 52
    for numero, nombres in catalogo.items():
        assert sorted(r["nombre"] for r in _forma(numero)["raices"]) == sorted(nombres), numero


def test_todos_los_dientes_se_dibujan_dentro_del_viewbox():
    for n, (x, _y0, _sup) in odo.POSICION.items():
        assert x >= 0 and x + _forma(n)["ancho"] <= odo.VIEWBOX_WIDTH, n


def test_las_raices_salen_del_json_no_del_argumento():
    con = odontograma_svg([], [], [], {16: ["X"]}, MODO_BLANCO)
    assert con == odontograma_svg([], [], [], {}, MODO_BLANCO)


# ====================================================== superficie palatino_lingual


def test_superficie_palatino_lingual_en_el_enum_y_las_6_en_caries_y_obturaciones():
    assert SuperficieDental.palatino_lingual.value == "palatino_lingual"
    assert len(SuperficieDental) == 6
    for tipo in (TipoHallazgo.caries, TipoHallazgo.obturacion_ok, TipoHallazgo.obturacion_defecto):
        for s in SuperficieDental:
            validar_superficie(tipo, s)  # no lanza
    with pytest.raises(ValueError):
        validar_superficie(TipoHallazgo.diastema, SuperficieDental.palatino_lingual)  # sigue solo mesial/distal


def test_etiqueta_palatina_en_superiores_y_lingual_en_inferiores():
    pl = SuperficieDental.palatino_lingual
    assert etiquetas.etiqueta_superficie(pl, [11]) == "palatina"
    assert etiquetas.etiqueta_superficie(pl, [28]) == "palatina"
    assert etiquetas.etiqueta_superficie(pl, [31]) == "lingual"
    assert etiquetas.etiqueta_superficie(pl, [48]) == "lingual"
    assert etiquetas.etiqueta_superficie(pl, [16, 26]) == "palatina"
    assert etiquetas.etiqueta_superficie(pl, [16, 46]) == "palatina/lingual"  # bitacora con las dos arcadas
    assert etiquetas.etiqueta_superficie(pl) == "palatina/lingual"
    assert etiquetas.etiqueta_superficie(SuperficieDental.mesial, [16]) == "mesial"  # el resto no cambia
    assert etiquetas.etiqueta_hallazgo(TipoHallazgo.caries, pl, 16) == "Caries (palatina)"
    assert etiquetas.etiqueta_hallazgo(TipoHallazgo.obturacion_ok, pl, 36) == "Obturación en buen estado (lingual)"
    assert etiquetas.etiqueta_hallazgo(TipoHallazgo.caries, SuperficieDental.oclusal, 16) == "Caries (oclusal)"


# --- por la API (alta, validacion por tipo, texto en los PDF) --------------------


@pytest.fixture(autouse=True)
def sin_weasyprint(monkeypatch):
    async def _render(plantilla: str, contexto: dict) -> bytes:
        return servicio_pdf._plantillas.get_template(plantilla).render(**contexto).encode("utf-8")

    monkeypatch.setattr("app.routers.pdf.generar_pdf", _render)
    monkeypatch.setattr("app.routers.historia_clinica.generar_pdf", _render)

    async def _sin_raices(session):  # diente_anatomia usa ARRAY: no existe en SQLite
        return {}

    monkeypatch.setattr(impreso, "raices_por_diente", _sin_raices)


@pytest_asyncio.fixture
async def h_dra(session_factory):
    async with session_factory() as s:
        u = Usuario(nombre="doctora", rol=RolUsuario.dra, password_hash="x", email="doctora@e.com")
        s.add(u)
        await s.commit()
        uid = u.id
    return {"Authorization": f"Bearer {security.crear_access_token(uid, 'dra')}"}


async def _paciente(client, h):
    r = await client.post(
        "/pacientes", headers=h,
        json={"movil": "04141234567", "nombre_completo": "Paciente Palatino", "fecha_registro": "2026-10-05",
              "fecha_primera_consulta_real": "2012-04-01"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _alta(client, h, pid, diente, tipo, superficie):
    return await client.post(
        f"/pacientes/{pid}/dientes/{diente}/hallazgos", headers=h,
        json={"numero_diente": diente, "tipo_hallazgo": tipo, "superficie": superficie, "fecha": "2026-10-01"},
    )


async def test_alta_acepta_las_6_superficies_en_caries_y_obturaciones(client, h_dra):
    pid = await _paciente(client, h_dra)
    for tipo in ("caries", "obturacion_ok", "obturacion_defecto"):
        for s in SUPERFICIES:
            r = await _alta(client, h_dra, pid, 16, tipo, s)
            assert r.status_code == 201, (tipo, s, r.text)
            assert r.json()["superficie"] == s


async def test_alta_rechaza_palatino_lingual_en_diastema(client, h_dra):
    pid = await _paciente(client, h_dra)
    r = await _alta(client, h_dra, pid, 11, "diastema", "palatino_lingual")
    assert r.status_code == 422
    assert (await _alta(client, h_dra, pid, 11, "diastema", "mesial")).status_code == 201


async def test_bitacora_acepta_palatino_lingual(client, h_dra):
    pid = await _paciente(client, h_dra)
    r = await client.post(
        f"/pacientes/{pid}/bitacora", headers=h_dra,
        json={"fecha": "2026-10-01", "descripcion": "Resina", "dientes": [16, 26],
              "tipo_hallazgo": "obturacion_ok", "superficie": "palatino_lingual"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["superficie"] == "palatino_lingual"


async def test_el_odontograma_impreso_dice_palatina_o_lingual_segun_el_diente(client, h_dra):
    pid = await _paciente(client, h_dra)
    await _alta(client, h_dra, pid, 16, "caries", "palatino_lingual")
    await _alta(client, h_dra, pid, 46, "caries", "palatino_lingual")
    await _alta(client, h_dra, pid, 36, "obturacion_ok", "palatino_lingual")
    html = (await client.get(f"/pacientes/{pid}/pdf/odontograma-actual", headers=h_dra)).text

    def linea(n):
        return re.search(rf'<td class="num">{n}</td><td class="texto">(.*?)</td>', html, re.S).group(1)

    assert linea(16) == "Caries (palatina)"
    assert linea(46) == "Caries (lingual)"
    assert linea(36) == "Obturación en buen estado (lingual)"
    assert "palatino_lingual" not in html and "palatina/lingual" not in html


# =================================================== dibujo: rellenos por superficie
# vestibular -> elipse vestibular + franja vestibular de la oclusal; palatino_lingual
# -> elipse palatina + franja de la oclusal; oclusal -> centro oclusal; mesial/distal
# -> franja lateral en las tres vistas; cervical -> franja cervical (solo vestibular).


def _rellenos_por_vista(superficie, numero=16, tipo="caries", color=ROJO):
    svg = _dibujo([_h(numero, tipo, superficie)])
    return {v: _con(_vista(svg, numero, v), fill=color) for v in ("vestibular", "oclusal", "palatina")}


def _tags(rellenos):
    return {v: sorted(_tag(e) for e in es) for v, es in rellenos.items()}


def test_caries_vestibular():
    r = _tags(_rellenos_por_vista("vestibular"))
    assert r == {"vestibular": ["ellipse"], "oclusal": ["rect"], "palatina": []}


def test_caries_palatino_lingual():
    r = _tags(_rellenos_por_vista("palatino_lingual"))
    assert r == {"vestibular": [], "oclusal": ["rect"], "palatina": ["ellipse"]}


def test_caries_oclusal_solo_en_el_centro_de_la_vista_oclusal():
    rellenos = _rellenos_por_vista("oclusal")
    assert _tags(rellenos) == {"vestibular": [], "oclusal": ["path"], "palatina": []}
    assert rellenos["oclusal"][0].get("d") == _forma(16)["oclusal"]["centro"]


@pytest.mark.parametrize("superficie", ["mesial", "distal"])
def test_caries_mesial_y_distal_en_las_tres_vistas(superficie):
    r = _tags(_rellenos_por_vista(superficie))
    assert r == {"vestibular": ["rect"], "oclusal": ["rect"], "palatina": ["rect"]}


def test_mesial_a_la_derecha_en_cuadrantes_1_y_4_y_a_la_izquierda_en_2_y_3():
    """Coordenadas locales: mesial = x >= 0.73*ancho; el reflejo (2 y 3) lo hace el grupo espejo."""
    for numero, espejo in ((16, False), (26, True), (46, False), (36, True)):
        w, _ = _ancho_y_cervical(numero)
        svg = _dibujo([_h(numero, "caries", "mesial")])
        rect = _con(_vista(svg, numero, "vestibular"), "rect", fill=ROJO)[0]
        assert float(rect.get("x")) == pytest.approx(0.73 * w)  # siempre a la derecha en coordenadas locales
        reflejado = any("scale(-1 1)" in (g.get("transform") or "") for g in _diente(svg, numero).iter())
        assert reflejado is espejo, numero


def test_caries_cervical_solo_en_la_vista_vestibular():
    r = _tags(_rellenos_por_vista("cervical"))
    assert r == {"vestibular": ["rect"], "oclusal": [], "palatina": []}
    w, c = _ancho_y_cervical(16)
    rect = _rellenos_por_vista("cervical")["vestibular"][0]
    assert (float(rect.get("y")), float(rect.get("height"))) == (c, 6)


def test_obturaciones_ok_y_con_defecto_en_azul_y_azul_con_borde_rojo():
    ok = _rellenos_por_vista("vestibular", tipo="obturacion_ok", color=AZUL)
    assert _tags(ok) == {"vestibular": ["ellipse"], "oclusal": ["rect"], "palatina": []}
    assert not _con(_vista(_dibujo([_h(16, "obturacion_ok", "vestibular")]), 16, "vestibular"), stroke=ROJO)
    defecto = _dibujo([_h(16, "obturacion_defecto", "vestibular")])
    el = _con(_vista(defecto, 16, "vestibular"), "ellipse", fill=AZUL)[0]
    assert el.get("stroke") == ROJO


def test_la_caries_se_pinta_encima_de_la_obturacion_de_la_misma_cara():
    svg = _dibujo([_h(16, "caries", "vestibular"), _h(16, "obturacion_ok", "vestibular")])  # caries primero
    colores = [e.get("fill") for e in _vista(svg, 16, "vestibular").iter() if _tag(e) == "ellipse"]
    assert colores == [AZUL, ROJO]


# ============================================================ dibujo: resto de la tabla


def test_corona_ok_y_con_defecto_en_las_tres_vistas():
    for tipo, con_rojo in (("corona_ok", False), ("corona_defecto", True)):
        svg = _dibujo([_h(13, tipo)])
        for v in ("vestibular", "oclusal", "palatina"):
            azul = _con(_vista(svg, 13, v), "path", stroke=AZUL, stroke_width="2")
            rojo = _con(_vista(svg, 13, v), "path", stroke=ROJO)
            assert len(azul) == 1, (tipo, v)
            assert bool(rojo) is con_rojo, (tipo, v)
    # sin corona, ni rastro de azul/rojo
    sano = _dibujo([_h(13, "sano")])
    assert not _con(_diente(sano, 13), stroke=AZUL) and not _con(_diente(sano, 13), stroke=ROJO)


def test_carilla_banda_azul_en_vestibular_y_en_la_franja_de_la_oclusal():
    ok = _dibujo([_h(14, "carilla_ok")])
    assert len(_con(_vista(ok, 14, "vestibular"), "rect", fill=AZUL)) == 1
    assert len(_con(_vista(ok, 14, "oclusal"), "rect", fill=AZUL)) == 1
    assert not _con(_vista(ok, 14, "palatina"), fill=AZUL)
    assert not _con(_diente(ok, 14), "line", stroke=ROJO)
    defecto = _dibujo([_h(14, "carilla_defecto")])
    for v in ("vestibular", "oclusal"):
        assert len(_con(_vista(defecto, 14, v), "line", stroke=ROJO)) == 1


@pytest.mark.parametrize(
    "tipo,esperado",
    [
        ("conducto_ok", [(AZUL, "2")]),
        ("conducto_ok_perno", [(AZUL, "3.5")]),
        ("conducto_defecto", [(AZUL, "2"), (ROJO, "2")]),
        ("conducto_perno_defecto", [(AZUL, "3.5"), (ROJO, "2")]),
        ("conducto_indicado", [(ROJO, "2")]),
    ],
)
def test_conductos_una_linea_por_raiz_con_su_trazo(tipo, esperado):
    svg = _dibujo([_h(16, tipo)])
    lineas = [l for l in _con(_vista(svg, 16, "vestibular"), "line") if l.get("stroke") in (AZUL, ROJO)]
    assert len(lineas) == 3 * len(esperado)  # 16 tiene 3 raices
    for color, grosor in esperado:
        assert len(_con(_vista(svg, 16, "vestibular"), "line", stroke=color, stroke_width=grosor)) == 3
    # van sobre el conducto del JSON de cada raiz
    assert {float(l.get("y1")) for l in lineas} == {_forma(16)["raices"][0]["conducto"][1]}


def test_ausente_linea_vertical_azul_por_las_tres_zonas_y_trazo_punteado_gris():
    svg = _dibujo([_h(16, "ausente")])
    w, _ = _ancho_y_cervical(16)
    lineas = [e for e in _diente(svg, 16) if _tag(e) == "line"]
    assert [(float(l.get("y1")), float(l.get("y2"))) for l in lineas] == [tuple(z) for z in JSON["layout"]["superior"]["zonas_ausente_y"]]
    assert all(l.get("stroke") == AZUL and float(l.get("x1")) == w / 2 == float(l.get("x2")) for l in lineas)
    for v in ("vestibular", "oclusal", "palatina"):
        punteado = _con(_vista(svg, 16, v), "path", stroke=COLORES["raiz_punteada"])
        assert punteado and all(p.get("stroke-dasharray") for p in punteado), v
        assert not _con(_vista(svg, 16, v), fill=COLORES["corona"])  # sin relleno de corona
    # inferior: zonas del arco inferior
    inf = _dibujo([_h(46, "ausente")])
    zonas = [tuple(z) for z in JSON["layout"]["inferior"]["zonas_ausente_y"]]
    assert [(float(l.get("y1")), float(l.get("y2"))) for l in _diente(inf, 46) if _tag(l) == "line"] == zonas


def test_ausente_pontico_de_un_puente_sin_linea_azul():
    dp = NS(numero_diente=45, rol=RolDientePuente.pontico, condicion_individual=TipoHallazgo.ausente)
    puente = NS(estado_general=EstadoGeneralPuente.ok)
    svg = _dibujo([], [], [(puente, [dp])])
    assert not [e for e in _diente(svg, 45) if _tag(e) == "line"]
    assert _con(_vista(svg, 45, "vestibular"), "path", stroke=COLORES["raiz_punteada"])  # pero si se ve ausente


def test_implante_sin_raices_con_tornillo_azul_en_la_vista_vestibular():
    svg = _dibujo([_h(46, "implante")])
    vest = _vista(svg, 46, "vestibular")
    assert not _con(vest, "path", fill=COLORES["raiz"])  # sin raices
    w, c = _ancho_y_cervical(46)
    tornillo = _con(vest, "line", stroke=AZUL)
    assert len(tornillo) == 2 + 4  # plataforma + eje + 4 roscas
    assert any(float(l.get("x1")) == w / 2 == float(l.get("x2")) and l.get("stroke-width") == "3" for l in tornillo)
    # el diente normal si tiene raices
    assert _con(_vista(_dibujo([]), 46, "vestibular"), "path", fill=COLORES["raiz"])


def test_periimplantitis_circulo_rojo_en_el_apice_del_tornillo():
    svg = _dibujo([_h(46, "implante")], [_lesion(46, "", TipoLesionApical.periimplantitis)])
    vest = _vista(svg, 46, "vestibular")
    eje = next(l for l in _con(vest, "line", stroke=AZUL) if l.get("stroke-width") == "3")
    circulo = _con(vest, "circle", fill=ROJO)
    assert len(circulo) == 1
    assert float(circulo[0].get("cx")) == float(eje.get("x1"))
    assert float(circulo[0].get("cy")) == pytest.approx(float(eje.get("y2")) - 1.5)


def test_resto_radicular_corona_punteada_y_RR_rojo():
    svg = _dibujo([_h(25, "resto_radicular")])
    vest = _vista(svg, 25, "vestibular")
    assert _con(vest, "path", stroke=COLORES["raiz_punteada"])  # corona punteada
    assert _con(vest, "path", fill=COLORES["raiz"])             # raices dibujadas normal
    assert not _con(vest, "rect", fill=COLORES["corona"])       # sin relleno de corona
    textos = [t for t in _diente(svg, 25).iter() if _tag(t) == "text" and t.text == "RR"]
    assert textos and textos[-1].get("fill") == ROJO


def test_diente_impactado_en_posicion_normal_con_IMP_rojo():
    for numero in (27, 47):
        svg = _dibujo([_h(numero, "diente_impactado")])
        assert not [g for g in _diente(svg, numero).iter() if (g.get("transform") or "").startswith("rotate")]
        textos = [t for t in _diente(svg, numero).iter() if _tag(t) == "text" and t.text == "IMP"]
        assert textos and textos[-1].get("fill") == ROJO
    assert not [t for t in _diente(_dibujo([]), 27).iter() if _tag(t) == "text" and t.text == "IMP"]


def _ys(e):
    """Coordenadas y de un simbolo de movimiento (line, polyline o el arco de la rotacion)."""
    if _tag(e) == "line":
        return [float(e.get("y1")), float(e.get("y2"))]
    if _tag(e) == "polyline":
        return [float(p.split(",")[1]) for p in e.get("points").split()]
    n = [float(v) for v in re.findall(r"-?\d+\.?\d*", e.get("d"))]  # M x y A rx ry rot f1 f2 x y
    return [n[1], n[8]]


def _simbolos_de_movimiento(svg, numero):
    """Hijos directos del diente (fuera de las vistas) dibujados en azul sin relleno."""
    return [e for e in _diente(svg, numero) if _tag(e) in ("line", "polyline", "path") and e.get("stroke") == AZUL
            and e.get("fill", "none") == "none" and e.get("stroke-width") == "1.5"]


@pytest.mark.parametrize(
    "tipo", ["movimiento_extrusion", "movimiento_intrusion", "movimiento_mesializacion",
             "movimiento_distalizacion", "movimiento_rotacion"],
)
def test_movimientos_fila_por_fuera_de_los_apices(tipo):
    arriba = _simbolos_de_movimiento(_dibujo([_h(16, tipo)]), 16)
    abajo = _simbolos_de_movimiento(_dibujo([_h(46, tipo)]), 46)
    assert arriba and abajo
    assert all(y < 0 for e in arriba for y in _ys(e)), tipo            # superior: sobre los apices
    numero_y = JSON["layout"]["inferior"]["numero_y"]
    assert all(y > numero_y for e in abajo for y in _ys(e)), tipo      # inferior: bajo los apices y el numero


def test_movimientos_varios_en_una_sola_fila():
    svg = _dibujo([_h(28, "movimiento_extrusion"), _h(28, "movimiento_intrusion"), _h(28, "movimiento_mesializacion")])
    lineas = [e for e in _simbolos_de_movimiento(svg, 28) if _tag(e) == "line"]
    assert len(lineas) == 3
    assert len({round(sum(_ys(e)) / 2, 1) for e in lineas}) == 1               # misma fila (mismo y central)
    assert len({round((float(e.get("x1")) + float(e.get("x2"))) / 2, 1) for e in lineas}) == 3  # lado a lado


def test_diastema_dos_lineas_verticales_azules_del_lado_indicado():
    # 12 (cuadrante 1): mesial a la derecha, distal a la izquierda. 22 (espejo): al reves.
    for numero, superficie, a_la_derecha in ((12, "mesial", True), (12, "distal", False),
                                             (22, "mesial", False), (22, "distal", True)):
        w, _ = _ancho_y_cervical(numero)
        svg = _dibujo([_h(numero, "diastema", superficie)])
        lineas = [e for e in _diente(svg, numero) if _tag(e) == "line"]
        assert len(lineas) == 2, (numero, superficie)
        xs = [float(l.get("x1")) for l in lineas]
        assert all(l.get("stroke") == AZUL and l.get("x1") == l.get("x2") for l in lineas)
        assert all((x > w) if a_la_derecha else (x < 0) for x in xs), (numero, superficie, xs)


def test_abfraccion_cuna_roja_en_la_zona_cervical_de_la_vista_vestibular():
    svg = _dibujo([_h(24, "afraccion")])
    w, c = _ancho_y_cervical(24)
    cunas = _con(_vista(svg, 24, "vestibular"), "polygon", fill=ROJO)
    assert len(cunas) == 1
    ys = [float(p.split(",")[1]) for p in cunas[0].get("points").split()]
    assert min(ys) == c and max(ys) <= c + 8  # pegada a la linea cervical, hacia la corona
    assert not _con(_vista(svg, 24, "oclusal"), "polygon") and not _con(_vista(svg, 24, "palatina"), "polygon")


@pytest.mark.parametrize("tipo,letra", [("exodoncia_simple", "S"), ("exodoncia_quirurgica", "Q")])
def test_exodoncia_x_roja_en_las_tres_vistas_y_letra_junto_al_numero(tipo, letra):
    svg = _dibujo([_h(11, tipo)])
    d = _diente(svg, 11)
    cruces = [e for e in d if _tag(e) == "line" and e.get("stroke") == ROJO]
    zonas = JSON["layout"]["superior"]["zonas_ausente_y"]
    assert len(cruces) == 6  # dos trazos por vista
    assert sorted({(min(float(l.get("y1")), float(l.get("y2"))), max(float(l.get("y1")), float(l.get("y2")))) for l in cruces}) == sorted(tuple(z) for z in zonas)
    letras = [t for t in d if _tag(t) == "text" and t.text == letra and t.get("fill") == ROJO]
    assert letras
    assert not [e for e in d if _tag(e) == "line" and e.get("stroke") == AZUL]  # no hay X azul


def test_supernumerario_SN_rojo_junto_al_numero_y_sin_dibujar_diente_extra():
    base = _dibujo([])
    svg = _dibujo([_h(13, "supernumerario")])
    textos = [t for t in _diente(svg, 13) if _tag(t) == "text" and t.text == "SN" and t.get("fill") == ROJO]
    assert len(textos) == 1
    assert len([g for g in svg.iter() if g.get("data-diente")]) == len([g for g in base.iter() if g.get("data-diente")]) == 32
    assert not [t for t in _diente(base, 13) if _tag(t) == "text" and t.text == "SN"]


def test_requiere_periodontal_PER_naranja_junto_al_numero_y_detras_de_SN():
    from app.services.odontograma_svg import NARANJA

    solo = [t for t in _diente(_dibujo([_h(45, "requiere_periodontal")]), 45)
            if _tag(t) == "text" and t.text == "PER" and t.get("fill") == NARANJA]
    assert len(solo) == 1
    assert not [t for t in _diente(_dibujo([]), 45) if _tag(t) == "text" and t.text == "PER"]
    ambos = _diente(_dibujo([_h(13, "supernumerario"), _h(13, "requiere_periodontal")]), 13)
    x = {t.text: float(t.get("x")) for t in ambos if _tag(t) == "text" and t.text in ("SN", "PER")}
    assert x["PER"] > x["SN"]


def test_spp_texto_azul_junto_a_la_corona_vestibular():
    svg = _dibujo([_h(23, "spp")])
    textos = [t for t in _diente(svg, 23) if _tag(t) == "text" and t.text == "SPP" and t.get("fill") == AZUL]
    assert len(textos) == 1
    _, c = _ancho_y_cervical(23)
    assert c < float(textos[0].get("y")) < 100  # a la altura de la corona de la vista vestibular


@pytest.mark.parametrize(
    "numero,raiz",
    [(n, r["nombre"]) for n in (16, 17, 18, 14, 46, 48, 26, 36) for r in _forma(n)["raices"]],
)
def test_lesion_apical_en_el_apice_de_la_raiz_por_nombre(numero, raiz):
    svg = _dibujo([], [_lesion(numero, raiz)])
    apice = next(r["apice"] for r in _forma(numero)["raices"] if r["nombre"] == raiz)
    circulos = _con(_vista(svg, numero, "vestibular"), "circle", fill=ROJO)
    assert len(circulos) == 1
    assert (float(circulos[0].get("cx")), float(circulos[0].get("cy"))) == (apice[0], pytest.approx(apice[1] - 1.5))


def test_lesion_apical_distingue_raices_del_mismo_diente():
    por_raiz = {}
    for r in _forma(16)["raices"]:
        c = _con(_vista(_dibujo([], [_lesion(16, r["nombre"])]), 16, "vestibular"), "circle", fill=ROJO)[0]
        por_raiz[r["nombre"]] = float(c.get("cx"))
    assert len(set(por_raiz.values())) == 3


def test_puente_circulos_azules_sobre_la_corona_unidos_por_barra():
    dientes = [NS(numero_diente=n, rol=rol, condicion_individual=TipoHallazgo(c)) for n, rol, c in (
        (44, RolDientePuente.pilar, "sano"), (45, RolDientePuente.pontico, "ausente"), (46, RolDientePuente.pilar, "sano"))]
    ok = ET.fromstring(str(odontograma_svg([], [], [(NS(estado_general=EstadoGeneralPuente.ok), dientes)], {})))
    capa = ok[-1]
    assert len(_con(capa, "circle", stroke=AZUL)) == 3 and len(_con(capa, "line", stroke=AZUL)) == 2
    assert not _con(capa, "circle", stroke=ROJO)
    defecto = ET.fromstring(str(odontograma_svg([], [], [(NS(estado_general=EstadoGeneralPuente.defecto), dientes)], {})))
    assert len(_con(defecto[-1], "circle", stroke=ROJO)) == 3


# ======================================================== modos y paleta


def _todos_los_hallazgos():
    tipos_sin_superficie = [t.value for t in TipoHallazgo if t.value not in ("caries", "obturacion_ok", "obturacion_defecto", "diastema")]
    hall = [_h(16, t) for t in tipos_sin_superficie] + [_h(46, t) for t in tipos_sin_superficie]
    for s in SUPERFICIES:
        hall += [_h(17, "caries", s), _h(17, "obturacion_ok", s), _h(17, "obturacion_defecto", s)]
    hall += [_h(12, "diastema", "mesial"), _h(12, "diastema", "distal")]
    return hall


def test_modo_color_solo_usa_los_colores_del_json():
    usados = {c.lower() for c in HEX.findall(str(odontograma_svg(_todos_los_hallazgos(), [_lesion(16, "Palatina")], [], {})))}
    assert usados <= {c.lower() for c in COLORES.values()}, usados - set(COLORES.values())


def test_modos_blanco_y_gris_sin_color_con_todos_los_tipos():
    for modo in (MODO_BLANCO, MODO_GRIS):
        svg = str(odontograma_svg(_todos_los_hallazgos(), [_lesion(16, "Palatina")], [], {}, modo))
        colores = {c.lower() for c in HEX.findall(svg)}
        assert colores and all(c[1:3] == c[3:5] == c[5:7] for c in colores), (modo, colores)
        assert AZUL not in svg and ROJO not in svg


def test_modo_blanco_ignora_los_hallazgos():
    assert odontograma_svg(_todos_los_hallazgos(), [], [], {}, MODO_BLANCO) == odontograma_svg([], [], [], {}, MODO_BLANCO)


def test_el_diente_sano_no_lleva_marcas():
    svg = _dibujo([_h(11, "sano")])
    assert not _con(_diente(svg, 11), stroke=AZUL) and not _con(_diente(svg, 11), fill=ROJO)
    assert [t.text for t in _diente(svg, 11) if _tag(t) == "text"] == ["11"]


# ============================ historia completa: leyenda y dibujo con el dibujo nuevo


async def test_historia_completa_genera_con_el_dibujo_nuevo(client, h_dra, session_factory):
    import uuid

    from app.routers import historia_clinica

    pid = await _paciente(client, h_dra)
    await _alta(client, h_dra, pid, 16, "caries", "palatino_lingual")
    await _alta(client, h_dra, pid, 46, "obturacion_ok", "palatino_lingual")
    async with session_factory() as s:
        odo_ctx = await historia_clinica._odontograma(s, uuid.UUID(pid))
    leyenda = dict(odo_ctx["leyenda"])
    assert leyenda[16] == ["Caries (palatina)"] and leyenda[46] == ["Obturación en buen estado (lingual)"]
    svg = ET.fromstring(str(odo_ctx["svg"]))
    assert len(_con(_vista(svg, 16, "palatina"), "ellipse", fill=ROJO)) == 1
    assert len(_con(_vista(svg, 46, "lingual"), "ellipse", fill=AZUL)) == 1
