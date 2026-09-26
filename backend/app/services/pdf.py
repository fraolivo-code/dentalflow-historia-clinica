# app/services/pdf.py — Generacion de PDF con WeasyPrint (HTML/CSS -> PDF).
#
# Las plantillas son Jinja2 (app/templates/pdf/) y las fuentes de marca
# (Inter y Fraunces, licencia OFL) viven en app/static/fonts/: cada plantilla
# las carga por @font-face con rutas relativas a app/static/, sin depender de
# las fuentes del sistema (la imagen slim solo trae DejaVu, que fontconfig usa
# como fallback).

import re
from datetime import date, time
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.concurrency import run_in_threadpool
from weasyprint import HTML
from weasyprint.text.fonts import FontConfiguration

APP_DIR = Path(__file__).resolve().parent.parent
# Unico lugar donde vive la ciudad que imprimen los documentos ("se expide en ...").
CIUDAD_CONSULTORIO = "Caracas"
# Barra final: sin ella las rutas relativas se resolverian contra app/.
BASE_URL_ESTATICOS = (APP_DIR / "static").as_uri() + "/"

_plantillas = Environment(
    loader=FileSystemLoader(APP_DIR / "templates" / "pdf"),
    autoescape=select_autoescape(["html"]),
)

MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
    "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def fecha_larga(d: date) -> str:
    """25 de septiembre de 2026"""
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def hora_12(t: time) -> str:
    """8:30 a. m. — espacios no separables para que no se corte al final de linea."""
    h = t.hour % 12 or 12
    sufijo = "a.\u00a0m." if t.hour < 12 else "p.\u00a0m."
    return f"{h}:{t.minute:02d}\u00a0{sufijo}"


_VINETA = re.compile(r"^\s*[-•*]\s+(.*)$")


def bloques_texto(texto: str) -> list[list[tuple[str, str | list[str]]]]:
    """
    Texto libre (contenido de la Dra.) -> parrafos, para no aplastarlo en un
    solo bloque. Una linea en blanco separa parrafos; dentro de cada uno, las
    lineas que empiezan con "- " (o "•", "*") forman una lista y el resto se
    agrupa como texto (sus saltos de linea simples se respetan con pre-line).
    Cada parrafo: [("texto", str) | ("lista", [items])].
    """
    parrafos = []
    for crudo in re.split(r"\n\s*\n", texto.replace("\r\n", "\n").strip()):
        bloques: list[tuple[str, str | list[str]]] = []
        for linea in crudo.split("\n"):
            vineta = _VINETA.match(linea)
            if vineta:
                if not bloques or bloques[-1][0] != "lista":
                    bloques.append(("lista", []))
                bloques[-1][1].append(vineta.group(1).strip())
            elif bloques and bloques[-1][0] == "texto":
                bloques[-1] = ("texto", f"{bloques[-1][1]}\n{linea.strip()}")
            else:
                bloques.append(("texto", linea.strip()))
        parrafos.append(bloques)
    return parrafos


_plantillas.filters["fecha_larga"] = fecha_larga
_plantillas.filters["bloques_texto"] = bloques_texto
_plantillas.filters["hora_12"] = hora_12
_plantillas.globals["ciudad_consultorio"] = CIUDAD_CONSULTORIO


def _renderizar(plantilla: str, contexto: dict) -> bytes:
    html = _plantillas.get_template(plantilla).render(**contexto)
    return HTML(string=html, base_url=BASE_URL_ESTATICOS).write_pdf(
        font_config=FontConfiguration()
    )


async def generar_pdf(plantilla: str, contexto: dict) -> bytes:
    # WeasyPrint es sincrono y usa CPU: corre en un hilo para no trabar el
    # event loop del resto de la API mientras arma el documento.
    return await run_in_threadpool(_renderizar, plantilla, contexto)
