# app/services/pdf.py — Generacion de PDF con WeasyPrint (HTML/CSS -> PDF).
#
# Las plantillas son Jinja2 (app/templates/pdf/) y las fuentes de marca
# (Inter y Fraunces, licencia OFL) viven en app/static/fonts/: cada plantilla
# las carga por @font-face con rutas relativas a app/static/, sin depender de
# las fuentes del sistema (la imagen slim solo trae DejaVu, que fontconfig usa
# como fallback).

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.concurrency import run_in_threadpool
from weasyprint import HTML
from weasyprint.text.fonts import FontConfiguration

APP_DIR = Path(__file__).resolve().parent.parent
# Barra final: sin ella las rutas relativas se resolverian contra app/.
BASE_URL_ESTATICOS = (APP_DIR / "static").as_uri() + "/"

_plantillas = Environment(
    loader=FileSystemLoader(APP_DIR / "templates" / "pdf"),
    autoescape=select_autoescape(["html"]),
)


def _renderizar(plantilla: str, contexto: dict) -> bytes:
    html = _plantillas.get_template(plantilla).render(**contexto)
    return HTML(string=html, base_url=BASE_URL_ESTATICOS).write_pdf(
        font_config=FontConfiguration()
    )


async def generar_pdf(plantilla: str, contexto: dict) -> bytes:
    # WeasyPrint es sincrono y usa CPU: corre en un hilo para no trabar el
    # event loop del resto de la API mientras arma el documento.
    return await run_in_threadpool(_renderizar, plantilla, contexto)
