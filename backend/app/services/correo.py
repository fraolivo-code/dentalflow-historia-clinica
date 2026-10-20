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


async def _enviar(para: str, asunto: str, texto: str, que: str) -> bool:
    """Un correo por el puente. `que` solo nombra el aviso en los logs (nunca el destinatario ni el texto)."""
    if not correo_configurado():
        logger.warning("%s: no se envia correo, faltan CORREO_PUENTE_URL, CORREO_PUENTE_TOKEN o FRONTEND_URL.", que)
        return False
    payload = {"token": os.getenv("CORREO_PUENTE_TOKEN", "").strip(), "para": para, "asunto": asunto, "texto": texto}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SEGUNDOS, follow_redirects=True) as cliente:
            respuesta = await cliente.post(os.getenv("CORREO_PUENTE_URL", "").strip(), json=payload)
        cuerpo = respuesta.json()
        if respuesta.status_code == 200 and isinstance(cuerpo, dict) and cuerpo.get("ok") is True:
            return True
        # Codigo corto del puente (destinatario_no_permitido, no_autorizado...): ayuda a diagnosticar y no lleva datos.
        motivo = cuerpo.get("error") if isinstance(cuerpo, dict) else None
        motivo = motivo if isinstance(motivo, str) and motivo.replace("_", "").isalnum() and len(motivo) <= 40 else "?"
        logger.error("%s: el puente de correo rechazo el envio (HTTP %s, motivo: %s).", que, respuesta.status_code, motivo)
    except Exception as exc:  # noqa: BLE001 - la respuesta de la API no depende del envio
        # Solo el tipo: el texto de la excepcion podria incluir la URL.
        logger.error("%s: no se pudo enviar el correo: %s", que, type(exc).__name__)
    return False


def _producto() -> str:
    return os.getenv("NOMBRE_PRODUCTO", "DentalFlow").strip() or "DentalFlow"


async def enviar_recuperacion(para: str, token: str) -> bool:
    return await _enviar(
        para,
        f"Restablecer su contraseña — {_producto()}",
        f"{construir_enlace(token)}\n\n"
        "El enlace vence en 30 minutos.\n\n"
        "Si usted no lo solicitó, ignore este mensaje; su contraseña no cambió.",
        "Recuperacion de clave",
    )


async def enviar_aviso_remision(para: str) -> bool:
    """Avisa al especialista que la Dra. le remitio un paciente. Sin datos del paciente (privacidad)."""
    base = os.getenv("FRONTEND_URL", "").strip().rstrip("/")
    return await _enviar(
        para,
        f"Nuevo paciente remitido — {_producto()}",
        "La Dra. le remitió un paciente.\n\n"
        f"Ingrese a {base} y abra «Mis pacientes».\n\n"
        "Por privacidad, este mensaje no incluye datos del paciente.",
        "Aviso de remision",
    )
