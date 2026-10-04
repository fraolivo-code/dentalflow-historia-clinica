# app/services/imagen_portada.py — Validacion y re-codificacion de la imagen de
# la portada (especificacion portada-configurable, A.2). El formato se decide por
# los primeros bytes, nunca por la extension ni por el Content-Type declarado.
# Solo PNG, JPEG y WebP: nunca SVG (puede llevar codigo) ni GIF.

import io

from PIL import Image, ImageOps

MAX_BYTES = 1024 * 1024  # 1 MB
MAX_LADO = 1200
# Una imagen de <= 1 MB puede declarar dimensiones enormes (bomba de descompresion).
MAX_PIXELES = 40_000_000

MENSAJE_FORMATO = "Formato no admitido. Use PNG, JPG o WebP."
MENSAJE_TAMANO = "La imagen supera el máximo de 1 MB."
MENSAJE_DIMENSIONES = "La imagen es demasiado grande en dimensiones."

_FORMATO_PILLOW = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}


class ImagenInvalida(Exception):
    def __init__(self, estado: int, mensaje: str):
        super().__init__(mensaje)
        self.estado = estado
        self.mensaje = mensaje


def detectar_tipo(datos: bytes) -> str | None:
    """Tipo MIME segun la firma del archivo, o None si no es PNG/JPEG/WebP."""
    if datos.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if datos.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(datos) >= 12 and datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
        return "image/webp"
    return None


def procesar(datos: bytes) -> tuple[bytes, str]:
    """
    Valida y re-codifica: devuelve (bytes, tipo MIME). Sin metadatos (EXIF, GPS,
    texto, perfiles), orientacion ya aplicada, lado mayor <= 1200 px y mismo
    formato que el original (PNG con transparencia sigue en PNG).
    Levanta ImagenInvalida con el codigo HTTP que corresponde.
    """
    if len(datos) > MAX_BYTES:
        raise ImagenInvalida(413, MENSAJE_TAMANO)
    tipo = detectar_tipo(datos)
    if tipo is None:
        raise ImagenInvalida(415, MENSAJE_FORMATO)

    try:
        with Image.open(io.BytesIO(datos)) as original:
            if original.format != _FORMATO_PILLOW[tipo]:
                raise ImagenInvalida(415, MENSAJE_FORMATO)
            ancho, alto = original.size
            if ancho * alto > MAX_PIXELES:
                raise ImagenInvalida(413, MENSAJE_DIMENSIONES)
            original.load()  # decodifica todo: un archivo corrupto falla aqui
            imagen = ImageOps.exif_transpose(original)  # aplica la rotacion antes de borrar el EXIF
    except ImagenInvalida:
        raise
    except Image.DecompressionBombError:
        raise ImagenInvalida(413, MENSAJE_DIMENSIONES)
    except Exception:  # noqa: BLE001 - cualquier fallo de Pillow = no es una imagen real
        raise ImagenInvalida(415, MENSAJE_FORMATO)

    con_alfa = "A" in imagen.getbands() or "transparency" in imagen.info
    if tipo == "image/jpeg":
        if imagen.mode not in ("RGB", "L"):
            imagen = imagen.convert("RGB")
    elif imagen.mode not in ("RGB", "RGBA", "L", "LA"):
        imagen = imagen.convert("RGBA" if con_alfa else "RGB")
    imagen.info = {}  # fuera metadatos heredados (perfil ICC, texto, dpi, transparencia de paleta)

    if max(imagen.size) > MAX_LADO:
        imagen.thumbnail((MAX_LADO, MAX_LADO), Image.Resampling.LANCZOS)

    salida = io.BytesIO()
    if tipo == "image/png":
        imagen.save(salida, format="PNG", optimize=True)
    elif tipo == "image/jpeg":
        imagen.save(salida, format="JPEG", quality=85, optimize=True)
    else:
        imagen.save(salida, format="WEBP", quality=85)
    return salida.getvalue(), tipo
