# app/routers/interno.py — Consulta que hace el puente de correo (Apps Script), no la interfaz (20/10/2026).
# El puente solo envia a una lista fija de correos; para que un especialista nuevo reciba avisos sin que nadie edite
# el script, el puente pregunta aqui si el correo es de un usuario ACTIVO de la app. No usa sesion de usuario: se
# autentica con la misma clave compartida del puente (CORREO_PUENTE_TOKEN). Responde solo si/no.
import hmac
import os

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.models.usuario import Usuario
from app.services.passwords import normalizar_email

router = APIRouter(prefix="/interno", tags=["interno"])


def _token_valido(recibido: str | None) -> bool:
    esperado = os.getenv("CORREO_PUENTE_TOKEN", "").strip()
    if len(esperado) < 32 or not recibido:  # sin clave configurada nadie entra
        return False
    return hmac.compare_digest(recibido.strip().encode(), esperado.encode())


@router.get("/correo-permitido")
async def correo_permitido(
    email: str = Query(max_length=254),
    x_puente_token: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    """¿Ese correo es de un usuario activo? (lo consulta el puente antes de rechazar un destinatario)."""
    if not _token_valido(x_puente_token):
        raise HTTPException(401, "No autorizado")
    correo = normalizar_email(email)
    if correo is None:
        return {"permitido": False}
    existe = (
        await session.execute(select(Usuario.id).where(Usuario.email == correo, Usuario.activo.is_(True)).limit(1))
    ).first()
    return {"permitido": existe is not None}
