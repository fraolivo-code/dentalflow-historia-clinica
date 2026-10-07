# app/services/odontograma_svg.py — Odontograma anatomico como SVG para los PDF.
#
# Todo el dibujo sale de app/data/dientes_anatomicos.json (version
# 2026-10-05.1), el MISMO archivo que usa el frontend: contornos, linea
# cervical, raices con el nombre del catalogo, conductos, vista oclusal, layout
# de las tres vistas y zonas de cada superficie. Aqui no hay formas propias;
# si cambia una forma o un simbolo, cambia el JSON (y la tabla de la seccion 2
# de especificacion-tecnica-odontograma-anatomico.md).
#
# Cada diente se dibuja en tres vistas apiladas:
#   superior: vestibular (corona y raices) / oclusal / palatina (recortada)
#   inferior: lingual (recortada) / oclusal / vestibular (raices hacia abajo)
# y los cuadrantes 2 y 3 son el reflejo de 1 y 4 (lo mesial hacia la linea media).
#
# Diferencias deliberadas con el componente de pantalla: sin interaccion
# (seleccion, hover, foco), los estilos van como atributos de presentacion
# (WeasyPrint no resuelve bien var() dentro del SVG) y el halo blanco de los
# textos se dibuja con una copia debajo en vez de paint-order.

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from html import escape
from pathlib import Path

from markupsafe import Markup

RUTA_FORMAS = Path(__file__).resolve().parent.parent / "data" / "dientes_anatomicos.json"


@lru_cache(maxsize=1)
def cargar_formas() -> dict:
    return json.loads(RUTA_FORMAS.read_text(encoding="utf-8"))


_JSON = cargar_formas()
_FORMAS = _JSON["formas"]
_DIENTES = _JSON["dientes"]
_LAYOUT = _JSON["layout"]

ARCO_SUPERIOR = [18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28]
ARCO_INFERIOR = [48, 47, 46, 45, 44, 43, 42, 41, 31, 32, 33, 34, 35, 36, 37, 38]

# Paleta: solo los hex del JSON.
AZUL = _JSON["colores"]["azul"]
ROJO = _JSON["colores"]["rojo"]
NARANJA = _JSON["colores"]["naranja"]
TRAZO = _JSON["colores"]["trazo"]
RAIZ = _JSON["colores"]["raiz"]
CORONA = _JSON["colores"]["corona"]
SURCO = _JSON["colores"]["surco"]
CERVICAL = _JSON["colores"]["cervical"]
RAIZ_PUNTEADA = _JSON["colores"]["raiz_punteada"]

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
    NARANJA: _GRIS_ROJO,  # PER: igual que lo que es rojo
    TRAZO: "#000000",  # contornos de los dientes y numeros
    RAIZ: "#f2f2f2",
    CERVICAL: "#808080",
    RAIZ_PUNTEADA: "#999999",
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
    ("obturacion_ok", {"fill": AZUL}),
    ("obturacion_defecto", {"fill": AZUL, "stroke": ROJO, "stroke-width": 1.6}),
    ("caries", {"fill": ROJO}),
)

# --- Geometria del conjunto (todo sale del layout del JSON) -------------------------

SEPARACION = _LAYOUT["separacion"]
SEPARACION_LINEA_MEDIA = _LAYOUT["separacion_linea_media"]
MARGEN_X = 10
MARGEN_Y = 8
FILA_MOVIMIENTOS = 10        # distancia del centro de la fila de flechas al extremo del dibujo
RADIO_FLECHA = 4
ESPACIO_ENTRE_ARCADAS = 14
VISTAS_SUPERIOR = ("vestibular", "oclusal", "palatina")
VISTAS_INFERIOR = ("lingual", "oclusal", "vestibular")

_TRANSFORM = re.compile(
    r"translate\(\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\)(?:\s*scale\(\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\))?"
)


def _mapa_y(transform: str):
    """y local de una vista -> y del bloque del diente, segun el transform del layout."""
    m = _TRANSFORM.fullmatch(transform.strip())
    ty, sy = float(m.group(2)), float(m.group(4) or 1)
    return lambda y: ty + sy * y


def _ancho(numero: int) -> float:
    return _FORMAS[_DIENTES[str(numero)]["forma"]]["ancho"]


def _fila(numeros: list[int]) -> tuple[list[float], float]:
    """x relativo de cada diente de la arcada y el ancho total de la fila."""
    xs, x = [], 0.0
    for i, n in enumerate(numeros):
        xs.append(x)
        x += _ancho(n) + (SEPARACION_LINEA_MEDIA if i == 7 else SEPARACION)
    return xs, xs[-1] + _ancho(numeros[-1])


_XS_SUP, _ANCHO_SUP = _fila(ARCO_SUPERIOR)
_XS_INF, _ANCHO_INF = _fila(ARCO_INFERIOR)
VIEWBOX_WIDTH = max(_ANCHO_SUP, _ANCHO_INF) + 2 * MARGEN_X

_SUP, _INF = _LAYOUT["superior"], _LAYOUT["inferior"]
_NUMERO_Y_INF_DEBAJO = _INF["numero_y"] + FILA_MOVIMIENTOS + 4   # fila de flechas del arco inferior
ARCO_SUPERIOR_Y = MARGEN_Y + FILA_MOVIMIENTOS + RADIO_FLECHA + 2  # deja lugar a la fila de flechas de arriba
_ALTO_SUPERIOR = _SUP["numero_y"] + 4
_TOPE_INFERIOR = _INF["zonas_ausente_y"][0][0]  # (negativo) donde empieza la vista lingual
ARCO_INFERIOR_Y = ARCO_SUPERIOR_Y + _ALTO_SUPERIOR + ESPACIO_ENTRE_ARCADAS - _TOPE_INFERIOR
VIEWBOX_HEIGHT = ARCO_INFERIOR_Y + _NUMERO_Y_INF_DEBAJO + RADIO_FLECHA + MARGEN_Y


def _posiciones() -> dict[int, tuple[float, float, bool]]:
    pos = {}
    for numeros, xs, ancho, y0, superior in (
        (ARCO_SUPERIOR, _XS_SUP, _ANCHO_SUP, ARCO_SUPERIOR_Y, True),
        (ARCO_INFERIOR, _XS_INF, _ANCHO_INF, ARCO_INFERIOR_Y, False),
    ):
        desplazamiento = (VIEWBOX_WIDTH - ancho) / 2  # cada fila centrada en la linea media
        for n, x in zip(numeros, xs):
            pos[n] = (desplazamiento + x, y0, superior)
    return pos


POSICION = _posiciones()


# --- SVG minimo -------------------------------------------------------------------

def _n(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _attrs(a: dict) -> str:
    return "".join(f' {k}="{escape(_n(v) if isinstance(v, (int, float)) else str(v))}"' for k, v in a.items())


def _el(tag: str, **a) -> str:
    return f"<{tag}{_attrs({k.replace('_', '-'): v for k, v in a.items()})}/>"


def _g(contenido: str, **a) -> str:
    return f"<g{_attrs({k.replace('_', '-'): v for k, v in a.items()})}>{contenido}</g>"


def _puntos(ps) -> str:
    return " ".join(f"{_n(x)},{_n(y)}" for x, y in ps)


def _linea(x1, y1, x2, y2, **estilo) -> str:
    return _el("line", x1=x1, y1=y1, x2=x2, y2=y2, **estilo)


def _rect(x, y, w, h, **estilo) -> str:
    return _el("rect", x=x, y=y, width=w, height=h, **estilo)


def _texto(x, y, contenido, color, tamano, anchor="start", halo=True) -> str:
    base = {"x": _n(x), "y": _n(y), "font-family": "Inter, sans-serif", "font-size": tamano,
            "font-weight": 700, "text-anchor": anchor}
    # Halo blanco (paint-order: stroke en el frontend): copia debajo con trazo.
    debajo = (f"<text{_attrs(base | {'fill': CORONA, 'stroke': CORONA, 'stroke-width': 2.5})}>"
              f"{escape(contenido)}</text>") if halo else ""
    return debajo + f"<text{_attrs(base | {'fill': color})}>{escape(contenido)}</text>"


# --- Estado de un diente ------------------------------------------------------------

@dataclass
class _Estado:
    tipos: set
    ausente: bool
    implante: bool
    tipo_endo: str | None
    movimientos: list
    exodoncia: str | None
    rellenos: list          # [(tipo, superficie)] de caries / obturaciones, en orden de pintado
    diastemas: list         # superficies ("mesial" | "distal")
    lesiones: list
    en_puente: object = None

    def tiene(self, tipo: str) -> bool:
        return tipo in self.tipos


def _estado(hallazgos, lesiones, en_puente) -> _Estado:
    tipos = {h.tipo_hallazgo.value for h in hallazgos}
    # Dentro de un puente activo, el estado del diente sale de su condicion
    # individual, no de los hallazgos.
    condicion = en_puente.condicion_individual.value if en_puente else None
    ausente = condicion == "ausente" if condicion else "ausente" in tipos
    implante = condicion == "implante" if condicion else "implante" in tipos
    if condicion:
        tipo_endo = condicion if condicion in TIPOS_ENDO else None
    else:
        tipo_endo = next((h.tipo_hallazgo.value for h in hallazgos if h.tipo_hallazgo.value in TIPOS_ENDO), None)
    rellenos = [
        (tipo, h.superficie.value)
        for tipo, _ in RELLENO_SUPERFICIE
        for h in hallazgos
        if h.tipo_hallazgo.value == tipo and h.superficie
    ]
    return _Estado(
        tipos=tipos,
        ausente=ausente,
        implante=implante and not ausente,
        tipo_endo=tipo_endo,
        movimientos=[t for t in TIPOS_MOVIMIENTO if t in tipos],
        exodoncia="Q" if "exodoncia_quirurgica" in tipos else "S" if "exodoncia_simple" in tipos else None,
        rellenos=rellenos,
        diastemas=[h.superficie.value for h in hallazgos if h.tipo_hallazgo.value == "diastema" and h.superficie],
        lesiones=lesiones,
        en_puente=en_puente,
    )


# --- Zonas de cada superficie (seccion "zonas" del JSON) ---------------------------------

def _zona(superficie: str, vista: str, ancho: float, cervical: float, centro: str, **estilo) -> str | None:
    """
    Elemento SVG (en coordenadas locales de la vista, con `estilo`) de la zona
    de una superficie, o None si esa cara no se ve en esa vista. vista:
    "vestibular", "palatina" (tambien la lingual) u "oclusal". Se recorta
    despues con el contorno del diente.
    """
    w = ancho
    oclusal = vista == "oclusal"
    if superficie == "oclusal":
        return _el("path", d=centro, **estilo) if oclusal else None
    if superficie in ("mesial", "distal"):
        mesial = superficie == "mesial"
        if oclusal:
            x0, x1 = (0.78 * w, w + 6) if mesial else (-6, 0.22 * w)
            return _rect(x0, -40, x1 - x0, 80, **estilo)
        x0, x1 = (0.73 * w, w + 6) if mesial else (-6, 0.27 * w)
        return _rect(x0, cervical + 6, x1 - x0, 40, **estilo)
    if superficie == "vestibular":
        if oclusal:
            return _rect(-6, -40, w + 12, 31, **estilo)  # franja y <= -9
        if vista == "vestibular":
            return _el("ellipse", cx=w / 2, cy=cervical + 18, rx=0.16 * w, ry=7, **estilo)
        return None
    if superficie == "palatino_lingual":
        if oclusal:
            return _rect(-6, 9, w + 12, 31, **estilo)    # franja y >= 9
        if vista == "palatina":
            return _el("ellipse", cx=w / 2, cy=cervical + 18, rx=0.17 * w, ry=7.5, **estilo)
        return None
    if superficie == "cervical":
        return _rect(-6, cervical, w + 12, 6, **estilo) if vista == "vestibular" else None
    return None


# --- Vistas -----------------------------------------------------------------------------

class _Diente:
    """Forma y recortes de un diente (ids unicos por numero dentro del SVG)."""

    def __init__(self, numero: int):
        self.numero = numero
        info = _DIENTES[str(numero)]
        self.forma = _FORMAS[info["forma"]]
        self.espejo = info["espejo"]
        self.superior = info["arcada"] == "superior"
        self.ancho = self.forma["ancho"]
        self.cervical = self.forma["cervical"]
        self.contorno = self.forma["contorno"]
        self.oclusal = self.forma["oclusal"]
        self.id_contorno, self.id_corona = f"cc{numero}", f"ck{numero}"
        self.id_raiz, self.id_recorte = f"cr{numero}", f"cw{numero}"
        self.id_oclusal = f"co{numero}"

    def definiciones(self) -> str:
        c, w = self.cervical, self.ancho
        # Recorte de las vistas palatina/lingual: desde cervical-12 hasta y=112 (corona + inicio de raiz).
        clips = {
            self.id_contorno: _el("path", d=self.contorno),
            self.id_corona: _rect(-10, c, w + 20, 130 - c),
            self.id_raiz: _rect(-10, -10, w + 20, c + 10),
            self.id_recorte: _rect(-10, c - 12, w + 20, 112 - (c - 12)),
            self.id_oclusal: _el("path", d=self.oclusal["contorno"]),
        }
        return "<defs>" + "".join(f'<clipPath id="{i}">{c_}</clipPath>' for i, c_ in clips.items()) + "</defs>"

    # -- piezas comunes ---------------------------------------------------------------

    def _rellenos(self, e: _Estado, vista: str) -> str:
        """Caries y obturaciones en la(s) zona(s) de su superficie, en esta vista."""
        id_clip = self.id_oclusal if vista == "oclusal" else self.id_contorno
        piezas = []
        for tipo, estilo in RELLENO_SUPERFICIE:
            for t, superficie in e.rellenos:
                if t != tipo:
                    continue
                z = _zona(superficie, vista, self.ancho, self.cervical, self.oclusal["centro"], **estilo)
                if z:
                    piezas.append(z)
        return _g("".join(piezas), clip_path=f"url(#{id_clip})") if piezas else ""

    def _contorno_corona(self, e: _Estado, vista: str) -> str:
        """Corona protesica: contorno de la corona en azul (y rojo por fuera si tiene defecto)."""
        if not (e.tiene("corona_ok") or e.tiene("corona_defecto")):
            return ""
        if vista == "oclusal":
            trazo = lambda **est: _el("path", d=self.oclusal["contorno"], fill="none", **est)  # noqa: E731
            envoltura = lambda s: s  # noqa: E731
        else:
            trazo = lambda **est: _el("path", d=self.contorno, fill="none", **est)  # noqa: E731
            envoltura = lambda s: _g(s, clip_path=f"url(#{self.id_corona})")  # noqa: E731
        fuera = trazo(stroke=ROJO, stroke_width=5) if e.tiene("corona_defecto") else ""
        return envoltura(fuera + trazo(stroke=AZUL, stroke_width=2))

    def _marcas_corona(self, e: _Estado, vista: str) -> str:
        """Lo que se ve igual en vestibular y palatina: rellenos y corona protesica."""
        return self._rellenos(e, vista) + self._contorno_corona(e, vista)

    def _tornillo(self) -> tuple[str, float]:
        """Implante (vista vestibular): tornillo azul en el lugar de la raiz. Devuelve (svg, y del apice)."""
        c, cx = self.cervical, self.ancho / 2
        y_apice = min(r["apice"][1] for r in self.forma["raices"]) + 3
        y_base = c - 2
        imp = {"stroke": AZUL, "stroke-width": 1.5, "stroke-linecap": "round"}
        s = [_linea(cx - 6, y_base, cx + 6, y_base, **imp),
             _linea(cx, y_base, cx, y_apice, **(imp | {"stroke-width": 3}))]
        for f in (0.25, 0.45, 0.65, 0.85):
            yy = y_base + (y_apice - y_base) * f
            s.append(_linea(cx - 4.5, yy, cx + 4.5, yy, **imp))
        return "".join(s), y_apice

    def _conductos(self, tipo: str) -> str:
        azul = {"stroke": AZUL, "stroke-width": 2, "stroke-linecap": "round"}
        grueso = {"stroke": AZUL, "stroke-width": 3.5, "stroke-linecap": "round"}
        rojo = {"stroke": ROJO, "stroke-width": 2, "stroke-linecap": "round"}
        s = []
        for r in self.forma["raices"]:
            x1, y1, x2, y2 = r["conducto"]
            l = lambda dx, est: _linea(x1 + dx, y1, x2 + dx, y2, **est)  # noqa: E731
            s.append({
                "conducto_ok": lambda: l(0, azul),
                "conducto_ok_perno": lambda: l(0, grueso),
                "conducto_defecto": lambda: l(-1.5, azul) + l(1.5, rojo),
                "conducto_perno_defecto": lambda: l(-2, grueso) + l(2.5, rojo),
                "conducto_indicado": lambda: l(0, rojo),
            }[tipo]())
        return "".join(s)

    def _apice(self, nombre: str) -> tuple[float, float]:
        raices = self.forma["raices"]
        raiz = next((r for r in raices if r["nombre"] == nombre), raices[0])
        return raiz["apice"]

    # -- vistas ------------------------------------------------------------------------

    def vista_vestibular(self, e: _Estado) -> str:
        c, w = self.cervical, self.ancho
        contorno = self.contorno
        if e.ausente:
            return _el("path", d=contorno, fill="none", stroke=RAIZ_PUNTEADA, stroke_width=1.4, stroke_dasharray="3 2")

        d = []
        resto = e.tiene("resto_radicular")
        if self.forma["raiz_palatina_punteada"] and not e.implante:
            d.append(_el("path", d=self.forma["raiz_palatina_punteada"], fill="none", stroke=RAIZ_PUNTEADA,
                         stroke_width=1, stroke_dasharray="2 2"))
        if not e.implante:
            d.append(_el("path", d=contorno, fill=RAIZ))
        if not resto:
            d.append(_g(_rect(-10, c, w + 20, 130 - c, fill=CORONA), clip_path=f"url(#{self.id_contorno})"))
        d.append(self._rellenos(e, "vestibular"))
        d.append(_g(_linea(-10, c, w + 10, c, stroke=CERVICAL, stroke_width=1), clip_path=f"url(#{self.id_contorno})"))

        # Carilla: banda azul sobre la cara vestibular de la corona (+ linea roja si tiene defecto).
        if e.tiene("carilla_ok") or e.tiene("carilla_defecto"):
            banda = _rect(-6, c + 27, w + 12, 8, fill=AZUL)
            if e.tiene("carilla_defecto"):
                banda += _linea(-6, c + 36.5, w + 6, c + 36.5, stroke=ROJO, stroke_width=1.5)
            d.append(_g(banda, clip_path=f"url(#{self.id_contorno})"))

        # Conductos (en cada raiz del JSON) o tornillo del implante.
        y_apice_tornillo = None
        if e.implante:
            tornillo, y_apice_tornillo = self._tornillo()
            d.append(tornillo)
        elif e.tipo_endo:
            d.append(self._conductos(e.tipo_endo))

        # Contorno del diente. Con resto radicular la corona va en punteado.
        if resto:
            d.append(_g(_el("path", d=contorno, fill="none", stroke=TRAZO, stroke_width=1.1),
                        clip_path=f"url(#{self.id_raiz})"))
            d.append(_g(_el("path", d=contorno, fill="none", stroke=RAIZ_PUNTEADA, stroke_width=1.4,
                            stroke_dasharray="3 2"), clip_path=f"url(#{self.id_corona})"))
        elif e.implante:
            # Sin raices: solo la corona (y su borde cervical).
            d.append(_g(_el("path", d=contorno, fill="none", stroke=TRAZO, stroke_width=1.1),
                        clip_path=f"url(#{self.id_corona})"))
            d.append(_g(_linea(-10, c, w + 10, c, stroke=TRAZO, stroke_width=1.1),
                        clip_path=f"url(#{self.id_contorno})"))
        else:
            d.append(_el("path", d=contorno, fill="none", stroke=TRAZO, stroke_width=1.1))
        d.append(self._contorno_corona(e, "vestibular"))

        # Abfraccion: cuna roja en la zona cervical, junto a la linea cervical.
        if e.tiene("afraccion"):
            mitad = min(0.16 * w, 7)
            d.append(_el("polygon", fill=ROJO, points=_puntos([(w / 2 - mitad, c), (w / 2 + mitad, c),
                                                              (w / 2, c + 8)])))

        # Lesion apical: circulo rojo en el apice de la raiz por nombre; periimplantitis en el del tornillo.
        for les in e.lesiones:
            if les.tipo.value == "periimplantitis":
                if y_apice_tornillo is None:
                    continue
                lx, ly = w / 2, y_apice_tornillo
            else:
                lx, ly = self._apice(les.raiz)
            d.append(_el("circle", cx=lx, cy=ly - 1.5, r=3.5, fill=ROJO, stroke=CORONA, stroke_width=1))
        return "".join(d)

    def vista_palatina(self, e: _Estado) -> str:
        """Palatina (superiores) o lingual (inferiores): corona y el inicio de la raiz."""
        c, w = self.cervical, self.ancho
        contorno = self.contorno
        if e.ausente:
            return _el("path", d=contorno, fill="none", stroke=RAIZ_PUNTEADA, stroke_width=1.4, stroke_dasharray="3 2")
        resto = e.tiene("resto_radicular")
        d = []
        if not e.implante:
            d.append(_el("path", d=contorno, fill=RAIZ))
        if not resto:
            d.append(_g(_rect(-10, c, w + 20, 130 - c, fill=CORONA), clip_path=f"url(#{self.id_contorno})"))
        d.append(self._rellenos(e, "palatina"))
        d.append(_g(_linea(-10, c, w + 10, c, stroke=CERVICAL, stroke_width=1), clip_path=f"url(#{self.id_contorno})"))
        if resto:
            d.append(_g(_el("path", d=contorno, fill="none", stroke=TRAZO, stroke_width=1.1),
                        clip_path=f"url(#{self.id_raiz})"))
            d.append(_g(_el("path", d=contorno, fill="none", stroke=RAIZ_PUNTEADA, stroke_width=1.4,
                            stroke_dasharray="3 2"), clip_path=f"url(#{self.id_corona})"))
        else:
            d.append(_el("path", d=contorno, fill="none", stroke=TRAZO, stroke_width=1.1))
        d.append(self._contorno_corona(e, "palatina"))
        if e.implante:
            # Sin raices: se oculta lo que queda por encima de la linea cervical.
            return _g("".join(d), clip_path=f"url(#{self.id_corona})")
        return "".join(d)

    def vista_oclusal(self, e: _Estado) -> str:
        o = self.oclusal
        if e.ausente:
            return _el("path", d=o["contorno"], fill="none", stroke=RAIZ_PUNTEADA, stroke_width=1.4,
                       stroke_dasharray="3 2")
        d = [_el("path", d=o["contorno"], fill=CORONA)]
        d.append(self._rellenos(e, "oclusal"))
        d.append(_el("path", d=o["surcos"], fill="none", stroke=SURCO, stroke_width=0.8, stroke_linecap="round",
                     stroke_linejoin="round"))
        if e.tiene("resto_radicular"):
            d.append(_el("path", d=o["contorno"], fill="none", stroke=RAIZ_PUNTEADA, stroke_width=1.4,
                         stroke_dasharray="3 2"))
        else:
            d.append(_el("path", d=o["contorno"], fill="none", stroke=TRAZO, stroke_width=1.1))
        # Carilla: banda azul en la franja vestibular de la oclusal (+ linea roja si tiene defecto).
        if e.tiene("carilla_ok") or e.tiene("carilla_defecto"):
            franja = _rect(-6, -40, self.ancho + 12, 31, fill=AZUL)
            if e.tiene("carilla_defecto"):
                franja += _linea(-6, -9, self.ancho + 6, -9, stroke=ROJO, stroke_width=1.5)
            d.append(_g(franja, clip_path=f"url(#{self.id_oclusal})"))
        d.append(self._contorno_corona(e, "oclusal"))
        return "".join(d)


# --- Simbolos fuera de las vistas ---------------------------------------------------------

MOV = {"fill": "none", "stroke": AZUL, "stroke-width": 1.5, "stroke-linecap": "round", "stroke-linejoin": "round"}


def _flecha(x, y, dx, dy) -> str:
    x1, y1, x2, y2 = x - dx * 4, y - dy * 4, x + dx * 4, y + dy * 4
    cabeza = [
        (x2 - dx * 3 - dy * 3, y2 - dy * 3 - dx * 3),
        (x2, y2),
        (x2 - dx * 3 + dy * 3, y2 - dy * 3 + dx * 3),
    ]
    return _linea(x1, y1, x2, y2, **MOV) + _el("polyline", points=_puntos(cabeza), **MOV)


def _simbolo_movimiento(tipo: str, x: float, y: float, hacia_oclusal: int, mesial: int) -> str:
    if tipo == "movimiento_extrusion":
        return _flecha(x, y, 0, hacia_oclusal)
    if tipo == "movimiento_intrusion":
        return _flecha(x, y, 0, -hacia_oclusal)
    if tipo == "movimiento_mesializacion":
        return _flecha(x, y, mesial, 0)
    if tipo == "movimiento_distalizacion":
        return _flecha(x, y, -mesial, 0)
    return _el("path", d=f"M {_n(x + 4)} {_n(y)} A 4 4 0 1 1 {_n(x)} {_n(y - 4)}", **MOV) + _el(
        "polyline", points=_puntos([(x - 2.5, y - 6.5), (x, y - 4), (x - 2.5, y - 1.5)]), **MOV
    )


def _diente(numero: int, x: float, y0: float, hallazgos, lesiones, en_puente) -> str:
    t = _Diente(numero)
    e = _estado(hallazgos, lesiones, en_puente)
    w, c, superior = t.ancho, t.cervical, t.superior
    capa = _SUP if superior else _INF
    nombres_vistas = VISTAS_SUPERIOR if superior else VISTAS_INFERIOR
    mesial_a_la_derecha = not t.espejo
    centro_corona_local = (c + 100) / 2

    vistas = []
    for nombre in nombres_vistas:
        if nombre == "oclusal":
            dibujo = t.vista_oclusal(e)
        else:
            dibujo = t.vista_vestibular(e) if nombre == "vestibular" else t.vista_palatina(e)
        if nombre in ("palatina", "lingual"):
            dibujo = _g(dibujo, clip_path=f"url(#{t.id_recorte})")
        vistas.append(_g(dibujo, transform=capa[nombre], data_vista=nombre))
    cuerpo = "".join(vistas)
    if t.espejo:
        cuerpo = _g(cuerpo, transform=f"translate({_n(w)} 0) scale(-1 1)")

    # Todo lo que sigue va fuera del grupo reflejado: textos y flechas no se espejan.
    extra = []
    y_vest = _mapa_y(capa["vestibular"])
    zonas = capa["zonas_ausente_y"]
    cx = w / 2

    if e.tiene("resto_radicular"):
        extra.append(_texto(cx, y_vest(centro_corona_local) + 4, "RR", ROJO, 10, "middle"))
    if e.tiene("diente_impactado"):
        extra.append(_texto(cx, y_vest(centro_corona_local) + 4, "IMP", ROJO, 9, "middle"))
    if e.tiene("spp"):
        extra.append(_texto(cx, y_vest(c + 31), "SPP", AZUL, 7.5, "middle"))

    # Exodoncia: X roja sobre las tres vistas (+ S / Q junto al numero).
    if e.exodoncia:
        ex = {"stroke": ROJO, "stroke-width": 2.5, "stroke-linecap": "round"}
        for ya, yb in zonas:
            extra.append(_linea(3, ya, w - 3, yb, **ex))
            extra.append(_linea(w - 3, ya, 3, yb, **ex))

    # Diastema: dos lineas verticales azules entre el diente y su vecino, del lado indicado.
    for superficie in e.diastemas:
        hacia_derecha = (superficie == "mesial") == mesial_a_la_derecha
        ys = sorted((y_vest(c - 4), y_vest(102)))
        for dd in (1.5, 4.5):
            xx = w + dd if hacia_derecha else -dd
            extra.append(_linea(xx, ys[0], xx, ys[1], stroke=AZUL, stroke_width=1.5))

    # Ausente: linea azul vertical que atraviesa las tres vistas (no en un pontico).
    if e.ausente and not en_puente:
        for ya, yb in zonas:
            extra.append(_linea(cx, ya, cx, yb, stroke=AZUL, stroke_width=3))

    # Movimientos: una fila por fuera de los apices (arriba en los superiores, abajo en los inferiores).
    if e.movimientos:
        ym = -FILA_MOVIMIENTOS if superior else _NUMERO_Y_INF_DEBAJO
        hacia_oclusal = 1 if superior else -1
        mesial = 1 if mesial_a_la_derecha else -1
        for idx, tipo in enumerate(e.movimientos):
            extra.append(_simbolo_movimiento(tipo, cx - ((len(e.movimientos) - 1) * 10) / 2 + idx * 10, ym,
                                             hacia_oclusal, mesial))

    numero_y = capa["numero_y"]
    if e.exodoncia:
        extra.append(_texto(cx - 9, numero_y, e.exodoncia, ROJO, 7.5, "end"))
    if e.tiene("supernumerario"):
        extra.append(_texto(cx + 9, numero_y, "SN", ROJO, 7.5))
    if e.tiene("requiere_periodontal"):
        # Detras de "SN" si el diente tambien lo lleva.
        dx = 22 if e.tiene("supernumerario") else 9
        extra.append(_texto(cx + dx, numero_y, "PER", NARANJA, 7.5))
    extra.append(f'<text x="{_n(cx)}" y="{_n(numero_y)}" text-anchor="middle" font-family="Inter, sans-serif" '
                 f'font-size="9" fill="{TRAZO}">{numero}</text>')
    return _g(t.definiciones() + cuerpo + "".join(extra), transform=f"translate({_n(x)} {_n(y0)})",
              data_diente=numero)


def _radio_puente(numero: int) -> float:
    return min(max(0.42 * _ancho(numero), 12), 20)


def _circulo_puente(cx, cy, r, defecto: bool) -> str:
    s = _el("circle", cx=cx, cy=cy, r=r, fill="none", stroke=AZUL, stroke_width=2.5)
    if defecto:
        s += _el("circle", cx=cx, cy=cy, r=r + 2.5, fill="none", stroke=ROJO, stroke_width=2)
    return s


def _capa_puente(dientes_puente, defecto: bool) -> str:
    """Circulo sobre la corona vestibular de cada diente del puente, unidos por una barra."""
    centros = []
    for dp in dientes_puente:
        x, y0, superior = POSICION[dp.numero_diente]
        t = _Diente(dp.numero_diente)
        capa = _SUP if superior else _INF
        y_corona = y0 + _mapa_y(capa["vestibular"])((t.cervical + 100) / 2)
        centros.append((x + t.ancho / 2, y_corona, _radio_puente(dp.numero_diente)))
    s = []
    for (px, py, pr), (cx, cy, cr) in zip(centros, centros[1:]):
        s.append(_linea(px + pr, py, cx - cr, cy, stroke=AZUL, stroke_width=2.5, stroke_linecap="round"))
    s.extend(_circulo_puente(cx, cy, r, defecto) for cx, cy, r in centros)
    return "<g>" + "".join(s) + "</g>"


def odontograma_svg(
    hallazgos, lesiones, puentes, raices_por_diente=None, modo: str = MODO_COLOR
) -> Markup:
    """
    hallazgos / lesiones: activos (no resueltos). puentes: lista de
    (puente, dientes en orden anatomico). raices_por_diente: se conserva por
    compatibilidad de la firma; las raices (y sus nombres) salen del JSON.

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
    for numero in ARCO_SUPERIOR + ARCO_INFERIOR:
        x, y0, _ = POSICION[numero]
        partes.append(_diente(numero, x, y0, por_diente[numero], lesiones_por_diente[numero],
                              en_puente.get(numero)))
    for puente, dientes in puentes:
        partes.append(_capa_puente(dientes, puente.estado_general.value == "defecto"))

    cuerpo = "".join(partes)
    if modo != MODO_COLOR:
        for color, equivalente in _A_BLANCO_Y_NEGRO.items():
            cuerpo = cuerpo.replace(f'"{color}"', f'"{equivalente}"')

    return Markup(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_n(VIEWBOX_WIDTH)} {_n(VIEWBOX_HEIGHT)}" '
        f'class="odontograma" role="img" aria-label="Odontograma">{cuerpo}</svg>'
    )
