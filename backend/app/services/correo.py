# app/services/correo.py — Envio de correo por el puente HTTPS (Apps Script),
# mismo contrato que usan Alma y el backup: POST JSON {token, para, asunto,
# texto}, el puente responde 302 (se sigue) y el exito es {"ok": true}.
# El puente solo envia a su lista DESTINATARIOS_PERMITIDOS.
# Nunca levanta excepciones ni registra el enlace, el token ni el correo.

import logging
import os

import httpx

logger = logging.getLogger(__name__)

TIMEOUT_SEGUNDOS = 15


def correo_configurado() -> bool:
    return bool(
        os.getenv("CORREO_PUENTE_URL", "").strip()
        and os.getenv("CORREO_PUENTE_TOKEN", "").strip()
        and os.getenv("FRONTEND_URL", "").strip()
    )


def construir_enlace(token: str) -> str:
    base = os.getenv("FRONTEND_URL", "").strip().rstrip("/")
    return f"{base}/restablecer?token={token}"


async def enviar_recuperacion(para: str, token: str) -> bool:
    if not correo_configurado():
        logger.warning(
            "Recuperacion de clave: no se envia correo, faltan CORREO_PUENTE_URL, "
            "CORREO_PUENTE_TOKEN o FRONTEND_URL."
        )
        return False
    producto = os.getenv("NOMBRE_PRODUCTO", "DentalFlow").strip() or "DentalFlow"
    payload = {
        "token": os.getenv("CORREO_PUENTE_TOKEN", "").strip(),
        "para": para,
        "asunto": f"Restablecer su contraseña — {producto}",
        "texto": (
            f"{construir_enlace(token)}\n\n"
            "El enlace vence en 30 minutos.\n\n"
            "Si usted no lo solicitó, ignore este mensaje; su contraseña no cambió."
        ),
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SEGUNDOS, follow_redirects=True) as cliente:
            respuesta = await cliente.post(os.getenv("CORREO_PUENTE_URL", "").strip(), json=payload)
        cuerpo = respuesta.json()
        if respuesta.status_code == 200 and isinstance(cuerpo, dict) and cuerpo.get("ok") is True:
            return True
        logger.error("El puente de correo rechazo el envio (HTTP %s).", respuesta.status_code)
    except Exception as exc:  # noqa: BLE001 - la respuesta de la API no depende del envio
        # Solo el tipo: el texto de la excepcion podria incluir la URL.
        logger.error("No se pudo enviar el correo de recuperacion: %s", type(exc).__name__)
    return False
