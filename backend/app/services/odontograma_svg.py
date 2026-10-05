# app/services/odontograma_svg.py — Odontograma como SVG para los PDF.
#
# Port a Python de OdontogramaBase.tsx del frontend
# (dentalflow-historia-clinica-frontend/src/components/Odontograma/), mismo
# dibujo y misma geometria, para que el documento salga de los datos
# guardados y no de lo que mande un navegador (decision del 26/09/2026,
# historia clinica completa / Habeas Data). Si cambia un simbolo alla, hay
# que cambiarlo aca tambien.
#
# Diferencias deliberadas con el componente: sin interaccion (seleccion,
# hover, foco), los estilos van como atributos de presentacion (WeasyPrint
# no resuelve bien var() dentro del SVG) y el halo blanco de los textos se
# dibuja con una copia debajo en vez de paint-order.

from collections import defaultdict
from dataclasses import dataclass
from html import escape

from markupsafe import Markup

ARCO_SUPERIOR = [18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28]
ARCO_INFERIOR = [48, 47, 46, 45, 44, 43, 42, 41, 31, 32, 33, 34, 35, 36, 37, 38]

TOOTH_W = 42
GAP = 4
MIDLINE_GAP = 16
MARGIN_X = 20
MOV_H = 14
ROOT_H = 26
CUELLO_H = 5
CROWN = 34
LABEL_H = 20
BLOCK_H = MOV_H + ROOT_H + CROWN + LABEL_H
ARCO_SUPERIOR_Y = 8
ARCO_INFERIOR_Y = ARCO_SUPERIOR_Y + BLOCK_H + 14
VIEWBOX_WIDTH = MARGIN_X * 2 + 16 * TOOTH_W + 15 * GAP + MIDLINE_GAP
VIEWBOX_HEIGHT = ARCO_INFERIOR_Y + BLOCK_H + 8
RADIO_PUENTE = 20

# Paleta (OdontogramaBase.css + tokens.css del frontend).
AZUL = "#1565c0"
ROJO = "#c62828"
SUPERFICIE = "#FFFFFF"
BORDE = "#D8DED9"
NUMERO = "#66806F"
RAIZ = "#eef1ee"

# Modos para imprimir (04/10/2026): se parte del mismo dibujo a color y se
# sustituye cada color de la paleta por su equivalente SIN color, para que el
# resultado se vea bien en una impresora en blanco y negro y no haya un segundo
# estilo que mantener. "blanco": solo los dientes (sin hallazgos). "gris": los
# hallazgos activos en grises claros y los contornos de los dientes en negro.
MODO_COLOR = "color"
MODO_BLANCO = "blanco"
MODO_GRIS = "gris"
_GRIS_AZUL = "#8c8c8c"  # lo que en pantalla es azul (existente / buen estado)
_GRIS_ROJO = "#a6a6a6"  # lo que en pantalla es rojo (caries, defectos, indicado)
_A_BLANCO_Y_NEGRO = {
    AZUL: _GRIS_AZUL,
    ROJO: _GRIS_ROJO,
    BORDE: "#000000",   # contorno de los dientes
    NUMERO: "#000000",  # numeros de diente
    RAIZ: "#f2f2f2",
}

TIPOS_ENDO = (
    "conducto_ok",
    "conducto_ok_perno",
    "conducto_defecto",
    "conducto_perno_defecto",
    "conducto_indicado",
)
TIPOS_MOVIMIENTO = (
    "movimiento_extrusion",
    "movimiento_intrusion",
    "movimiento_mesializacion",
    "movimiento_distalizacion",
    "movimiento_rotacion",
)
# Orden de pintado: la caries va por encima de una obturacion en la misma cara.
RELLENO_SUPERFICIE = (
    ("obturacion_ok", {"fill": AZUL, "stroke": BORDE, "stroke-width": 1}),
    ("obturacion_defecto", {"fill": AZUL, "stroke": ROJO, "stroke-width": 2}),
    ("caries", {"fill": ROJO, "stroke": BORDE, "stroke-width": 1}),
)
SUP = {"fill": SUPERFICIE, "stroke": BORDE, "stroke-width": 1}


def nombres_raices_por_defecto(numero: int) -> list[str]:
    """Espejo de diente_anatomia (y de nombresRaicesPorDefecto del frontend)."""
    cuadrante, posicion = divmod(numero, 10)
    superior = cuadrante in (1, 2)
    if posicion >= 6:
        return ["Mesiovestibular", "Palatina", "Distovestibular"] if superior else ["Mesial", "Distal"]
    if posicion == 4 and superior:
        return ["Vestibular", "Palatina"]
    return ["Única"]


# --- SVG minimo -------------------------------------------------------------------

def _n(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _attrs(a: dict) -> str:
    return "".join(f' {k}="{escape(_n(v) if isinstance(v, (int, float)) else str(v))}"' for k, v in a.items())


def _el(tag: str, **a) -> str:
    return f"<{tag}{_attrs({k.replace('_', '-'): v for k, v in a.items()})}/>"


def _puntos(ps) -> str:
    return " ".join(f"{_n(x)},{_n(y)}" for x, y in ps)


def _linea(x1, y1, x2, y2, **estilo) -> str:
    return _el("line", x1=x1, y1=y1, x2=x2, y2=y2, **estilo)


def _texto(x, y, contenido, color, tamano, anchor="start", halo=True) -> str:
    base = {"x": _n(x), "y": _n(y), "font-family": "Inter, sans-serif", "font-size": tamano,
            "font-weight": 700, "text-anchor": anchor}
    # Halo blanco (paint-order: stroke en el frontend): copia debajo con trazo.
    debajo = (f"<text{_attrs(base | {'fill': SUPERFICIE, 'stroke': SUPERFICIE, 'stroke-width': 2.5})}>"
              f"{escape(contenido)}</text>") if halo else ""
    return debajo + f"<text{_attrs(base | {'fill': color})}>{escape(contenido)}</text>"


# --- Geometria (identica al frontend) ------------------------------------------------

def _x_para_indice(i: int) -> float:
    return MARGIN_X + i * (TOOTH_W + GAP) + (MIDLINE_GAP if i >= 8 else 0)


@dataclass
class _Geo:
    cx: float
    crown_x: float
    crown_top: float
    crown_cy: float
    oclusal_y: float
    hacia_oclusal: int
    cuello_y: float
    raiz_base_y: float
    apice_y: float
    mov_y: float
    numero_y: float
    mesial_a_la_derecha: bool
    superficies: dict


def _geometria(numero: int, x: float, y0: float, superior: bool) -> _Geo:
    cx = x + TOOTH_W / 2
    crown_x = x + (TOOTH_W - CROWN) / 2
    crown_top = y0 + MOV_H + ROOT_H if superior else y0 + LABEL_H
    crown_bottom = crown_top + CROWN
    mesial_a_la_derecha = numero // 10 in (1, 4)
    a, b, s, i = crown_x, crown_top, CROWN, 11
    j = s - i
    arriba = [(a, b), (a + s, b), (a + j, b + i), (a + i, b + i)]
    abajo = [(a, b + s), (a + s, b + s), (a + j, b + j), (a + i, b + j)]
    izquierda = [(a, b), (a + i, b + i), (a + i, b + j), (a, b + s)]
    derecha = [(a + s, b), (a + j, b + i), (a + j, b + j), (a + s, b + s)]
    centro = [(a + i, b + i), (a + j, b + i), (a + j, b + j), (a + i, b + j)]
    return _Geo(
        cx=cx,
        crown_x=crown_x,
        crown_top=crown_top,
        crown_cy=crown_top + CROWN / 2,
        oclusal_y=crown_bottom if superior else crown_top,
        hacia_oclusal=1 if superior else -1,
        cuello_y=crown_top - CUELLO_H if superior else crown_bottom,
        raiz_base_y=crown_top - CUELLO_H if superior else crown_bottom + CUELLO_H,
        apice_y=y0 + MOV_H + 2 if superior else crown_bottom + ROOT_H - 2,
        mov_y=y0 + MOV_H / 2 if superior else crown_bottom + ROOT_H + MOV_H / 2,
        numero_y=crown_bottom + LABEL_H - 4 if superior else y0 + 12,
        mesial_a_la_derecha=mesial_a_la_derecha,
        # Mismo orden de dibujo que Object.values() en el frontend.
        superficies={
            "oclusal": centro,
            "vestibular": arriba if superior else abajo,
            "lingual": abajo if superior else arriba,
            "mesial": derecha if mesial_a_la_derecha else izquierda,
            "distal": izquierda if mesial_a_la_derecha else derecha,
        },
    )


def _posiciones_raices(cx: float, n: int) -> list[float]:
    if n >= 3:
        return [cx - 10, cx, cx + 10]
    if n == 2:
        return [cx - 7, cx + 7]
    return [cx]


def _x_de_raiz(nombre: str, nombres: list[str], g: _Geo) -> float:
    xs = _posiciones_raices(g.cx, len(nombres))
    mesial_x = xs[-1] if g.mesial_a_la_derecha else xs[0]
    distal_x = xs[0] if g.mesial_a_la_derecha else xs[-1]
    if len(xs) == 1:
        return xs[0]
    if nombre.startswith("Mesio") or nombre == "Mesial":
        return mesial_x
    if nombre.startswith("Disto") or nombre == "Distal":
        return distal_x
    if len(xs) == 3 and nombre == "Palatina":
        return xs[1]
    return xs[max(0, nombres.index(nombre) if nombre in nombres else 0)]


def _linea_endo(tipo: str, rx: float, g: _Geo) -> str:
    y1, y2 = g.raiz_base_y, g.apice_y + 1
    azul = {"stroke": AZUL, "stroke-width": 2, "stroke-linecap": "round"}
    grueso = {"stroke": AZUL, "stroke-width": 3.5, "stroke-linecap": "round"}
    rojo = {"stroke": ROJO, "stroke-width": 2, "stroke-linecap": "round"}
    l = lambda dx, est: _linea(rx + dx, y1, rx + dx, y2, **est)  # noqa: E731
    return {
        "conducto_ok": lambda: l(0, azul),
        "conducto_ok_perno": lambda: l(0, grueso),
        "conducto_defecto": lambda: l(-1.5, azul) + l(1.5, rojo),
        "conducto_perno_defecto": lambda: l(-2, grueso) + l(2.5, rojo),
        "conducto_indicado": lambda: l(0, rojo),
    }[tipo]()


MOV = {"fill": "none", "stroke": AZUL, "stroke-width": 1.5, "stroke-linecap": "round", "stroke-linejoin": "round"}


def _flecha(x, y, dx, dy) -> str:
    x1, y1, x2, y2 = x - dx * 4, y - dy * 4, x + dx * 4, y + dy * 4
    cabeza = [
        (x2 - dx * 3 - dy * 3, y2 - dy * 3 - dx * 3),
        (x2, y2),
        (x2 - dx * 3 + dy * 3, y2 - dy * 3 + dx * 3),
    ]
    return _linea(x1, y1, x2, y2, **MOV) + _el("polyline", points=_puntos(cabeza), **MOV)


def _simbolo_movimiento(tipo: str, x: float, g: _Geo) -> str:
    y = g.mov_y
    mesial = 1 if g.mesial_a_la_derecha else -1
    if tipo == "movimiento_extrusion":
        return _flecha(x, y, 0, g.hacia_oclusal)
    if tipo == "movimiento_intrusion":
        return _flecha(x, y, 0, -g.hacia_oclusal)
    if tipo == "movimiento_mesializacion":
        return _flecha(x, y, mesial, 0)
    if tipo == "movimiento_distalizacion":
        return _flecha(x, y, -mesial, 0)
    return _el("path", d=f"M {_n(x + 4)} {_n(y)} A 4 4 0 1 1 {_n(x)} {_n(y - 4)}", **MOV) + _el(
        "polyline", points=_puntos([(x - 2.5, y - 6.5), (x, y - 4), (x - 2.5, y - 1.5)]), **MOV
    )


def _circulo_corona(cx, cy, r, defecto: bool) -> str:
    s = _el("circle", cx=cx, cy=cy, r=r, fill="none", stroke=AZUL, stroke_width=2.5)
    if defecto:
        s += _el("circle", cx=cx, cy=cy, r=r + 2.5, fill="none", stroke=ROJO, stroke_width=2)
    return s


def _diente(numero, x, y0, superior, nombres_raices, hallazgos, lesiones, en_puente) -> str:
    g = _geometria(numero, x, y0, superior)
    tipos = {h.tipo_hallazgo.value for h in hallazgos}
    tiene = tipos.__contains__

    # Dentro de un puente activo, el estado del diente sale de su condicion
    # individual, no de los hallazgos.
    condicion = en_puente.condicion_individual.value if en_puente else None
    ausente = condicion == "ausente" if condicion else tiene("ausente")
    implante = condicion == "implante" if condicion else tiene("implante")
    if condicion:
        tipo_endo = condicion if condicion in TIPOS_ENDO else None
    else:
        tipo_endo = next((h.tipo_hallazgo.value for h in hallazgos if h.tipo_hallazgo.value in TIPOS_ENDO), None)
    movimientos = [t for t in TIPOS_MOVIMIENTO if tiene(t)]
    exodoncia = "Q" if tiene("exodoncia_quirurgica") else "S" if tiene("exodoncia_simple") else None
    raices = _posiciones_raices(g.cx, len(nombres_raices))
    borde_vestibular_y = g.crown_top if superior else g.crown_top + CROWN
    hacia_afuera = -g.hacia_oclusal

    d = []
    if not ausente and not implante:
        for rx in raices:
            d.append(_el("polygon", points=_puntos([(rx - 3.5, g.raiz_base_y), (rx + 3.5, g.raiz_base_y),
                                                    (rx + 1, g.apice_y), (rx - 1, g.apice_y)]),
                         fill=RAIZ, stroke=BORDE, stroke_width=1))
        if tipo_endo:
            d.extend(_linea_endo(tipo_endo, rx, g) for rx in raices)
    if implante and not ausente:
        imp = {"stroke": AZUL, "stroke-width": 1.5, "stroke-linecap": "round"}
        d.append(_linea(g.cx - 6, g.raiz_base_y, g.cx + 6, g.raiz_base_y, **imp))
        d.append(_linea(g.cx, g.raiz_base_y, g.cx, g.apice_y, **(imp | {"stroke-width": 3})))
        for f in (0.25, 0.45, 0.65, 0.85):
            yy = g.raiz_base_y + (g.apice_y - g.raiz_base_y) * f
            d.append(_linea(g.cx - 4.5, yy, g.cx + 4.5, yy, **imp))

    # Lesion apical / periimplantitis: circulo rojo en el apice.
    if not ausente:
        for l in lesiones:
            lx = g.cx if l.tipo.value == "periimplantitis" else _x_de_raiz(l.raiz, nombres_raices, g)
            d.append(_el("circle", cx=lx, cy=g.apice_y - g.hacia_oclusal * 1.5, r=3.5,
                         fill=ROJO, stroke=SUPERFICIE, stroke_width=1))

    # Cuello (superficie cervical)
    if not ausente:
        d.append(_el("rect", x=g.crown_x + 3, y=g.cuello_y, width=CROWN - 6, height=CUELLO_H, **SUP))

    # Corona dividida en caras
    if ausente:
        d.append(_el("rect", x=g.crown_x, y=g.crown_top, width=CROWN, height=CROWN, rx=3, fill="none",
                     stroke=BORDE, stroke_width=1.5, stroke_dasharray="3 2"))
    else:
        d.extend(_el("polygon", points=_puntos(ps), **SUP) for ps in g.superficies.values())
        for tipo, estilo in RELLENO_SUPERFICIE:
            for h in hallazgos:
                if h.tipo_hallazgo.value != tipo or not h.superficie:
                    continue
                if h.superficie.value == "cervical":
                    d.append(_el("rect", x=g.crown_x + 3, y=g.cuello_y, width=CROWN - 6, height=CUELLO_H, **estilo))
                else:
                    d.append(_el("polygon", points=_puntos(g.superficies[h.superficie.value]), **estilo))

    # Carilla: banda sobre el borde vestibular
    if tiene("carilla_ok") or tiene("carilla_defecto"):
        if tiene("carilla_defecto"):
            yb = borde_vestibular_y + hacia_afuera * 1.5
            d.append(_linea(g.crown_x, yb, g.crown_x + CROWN, yb, stroke=ROJO, stroke_width=2))
        yc = borde_vestibular_y - hacia_afuera * 2
        d.append(_linea(g.crown_x + 1, yc, g.crown_x + CROWN - 1, yc, stroke=AZUL, stroke_width=4))

    # Corona protesica
    if tiene("corona_ok") or tiene("corona_defecto"):
        d.append(_circulo_corona(g.cx, g.crown_cy, 20, tiene("corona_defecto")))

    # Afraccion: muesca roja en el borde incisal/oclusal
    if tiene("afraccion"):
        d.append(_el("polygon", fill=ROJO, points=_puntos([
            (g.cx - 5, g.oclusal_y + g.hacia_oclusal * 6),
            (g.cx + 5, g.oclusal_y + g.hacia_oclusal * 6),
            (g.cx, g.oclusal_y - g.hacia_oclusal * 2),
        ])))

    if tiene("resto_radicular"):
        d.append(_texto(g.cx, g.crown_cy + 4, "RR", ROJO, 10, "middle"))
    if tiene("spp"):
        d.append(_texto(g.cx, g.crown_top + CROWN - 3 if superior else g.crown_top + 9, "SPP", AZUL, 7.5, "middle"))

    # Exodoncia: X roja sobre la corona (+ S / Q junto al numero)
    if exodoncia:
        ex = {"stroke": ROJO, "stroke-width": 2.5, "stroke-linecap": "round"}
        d.append(_linea(g.crown_x, g.crown_top, g.crown_x + CROWN, g.crown_top + CROWN, **ex))
        d.append(_linea(g.crown_x + CROWN, g.crown_top, g.crown_x, g.crown_top + CROWN, **ex))

    # Diastema: dos lineas verticales paralelas del lado indicado
    for h in hallazgos:
        if h.tipo_hallazgo.value != "diastema" or not h.superficie:
            continue
        hacia_derecha = (h.superficie.value == "mesial") == g.mesial_a_la_derecha
        borde = g.crown_x + CROWN if hacia_derecha else g.crown_x
        signo = 1 if hacia_derecha else -1
        for dd in (2.5, 5.5):
            d.append(_linea(borde + signo * dd, g.crown_top - 2, borde + signo * dd, g.crown_top + CROWN + 2,
                            stroke=AZUL, stroke_width=1.5))

    # Ausente: linea azul vertical sobre todo el diente (no en un pontico).
    if ausente and not en_puente:
        d.append(_linea(g.cx, min(g.apice_y, g.oclusal_y), g.cx, max(g.apice_y, g.oclusal_y),
                        stroke=AZUL, stroke_width=3))

    # Movimientos: fila apical, fuera de la corona
    for idx, tipo in enumerate(movimientos):
        d.append(_simbolo_movimiento(tipo, g.cx - ((len(movimientos) - 1) * 10) / 2 + idx * 10, g))

    dibujo = "".join(d)
    if tiene("diente_impactado"):
        # Fuera de posicion: inclinado y corrido hacia apical.
        dibujo = (f'<g transform="translate(0 {_n(-g.hacia_oclusal * 3)}) '
                  f'rotate({16 if superior else -16} {_n(g.cx)} {_n(g.crown_cy)})">{dibujo}</g>')

    extra = _texto(g.crown_x + 1, g.numero_y, exodoncia, ROJO, 7.5) if exodoncia else ""
    numero_txt = (f'<text x="{_n(g.cx)}" y="{_n(g.numero_y)}" text-anchor="middle" '
                  f'font-family="Inter, sans-serif" font-size="9" fill="{NUMERO}">{numero}</text>')
    return f"<g>{dibujo}{extra}{numero_txt}</g>"


POSICION = {
    **{n: (_x_para_indice(i), ARCO_SUPERIOR_Y, True) for i, n in enumerate(ARCO_SUPERIOR)},
    **{n: (_x_para_indice(i), ARCO_INFERIOR_Y, False) for i, n in enumerate(ARCO_INFERIOR)},
}


def _capa_puente(dientes_puente, defecto: bool) -> str:
    """Circulo de corona en cada diente del puente, unidos por una barra."""
    centros = []
    for dp in dientes_puente:
        x, y0, sup = POSICION[dp.numero_diente]
        g = _geometria(dp.numero_diente, x, y0, sup)
        centros.append((g.cx, g.crown_cy))
    s = []
    for (px, py), (cx, cy) in zip(centros, centros[1:]):
        s.append(_linea(px + RADIO_PUENTE, py, cx - RADIO_PUENTE, cy, stroke=AZUL, stroke_width=2.5,
                        stroke_linecap="round"))
    s.extend(_circulo_corona(cx, cy, RADIO_PUENTE, defecto) for cx, cy in centros)
    return "<g>" + "".join(s) + "</g>"


def odontograma_svg(
    hallazgos, lesiones, puentes, raices_por_diente: dict[int, list[str]], modo: str = MODO_COLOR
) -> Markup:
    """
    hallazgos / lesiones: activos (no resueltos). puentes: lista de
    (puente, dientes en orden anatomico). raices_por_diente: de diente_anatomia.

    modo: "color" (pantalla/historia completa), "blanco" (dientes sin
    hallazgos; ignora lo recibido) o "gris" (hallazgos activos en gris). Ver
    _A_BLANCO_Y_NEGRO.
    """
    if modo not in (MODO_COLOR, MODO_BLANCO, MODO_GRIS):
        raise ValueError(f"modo de odontograma desconocido: {modo}")
    if modo == MODO_BLANCO:
        hallazgos, lesiones, puentes = [], [], []

    por_diente = defaultdict(list)
    for h in hallazgos:
        por_diente[h.numero_diente].append(h)
    lesiones_por_diente = defaultdict(list)
    for l in lesiones:
        lesiones_por_diente[l.numero_diente].append(l)
    en_puente = {dp.numero_diente: dp for _, dientes in puentes for dp in dientes}

    partes = []
    for numeros, y0, superior in ((ARCO_SUPERIOR, ARCO_SUPERIOR_Y, True), (ARCO_INFERIOR, ARCO_INFERIOR_Y, False)):
        for i, n in enumerate(numeros):
            partes.append(_diente(n, _x_para_indice(i), y0, superior,
                                  raices_por_diente.get(n) or nombres_raices_por_defecto(n),
                                  por_diente[n], lesiones_por_diente[n], en_puente.get(n)))
    for puente, dientes in puentes:
        partes.append(_capa_puente(dientes, puente.estado_general.value == "defecto"))

    cuerpo = "".join(partes)
    if modo != MODO_COLOR:
        for color, equivalente in _A_BLANCO_Y_NEGRO.items():
            cuerpo = cuerpo.replace(f'"{color}"', f'"{equivalente}"')

    return Markup(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEWBOX_WIDTH} {VIEWBOX_HEIGHT}" '
        f'class="odontograma" role="img" aria-label="Odontograma">{cuerpo}</svg>'
    )
