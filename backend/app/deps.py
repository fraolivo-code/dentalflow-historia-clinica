import logging
import os
import secrets
from collections.abc import AsyncGenerator
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session
from app.enums import RolUsuario
from app.models.common import a_utc
from app.models.usuario import Usuario
from app.security import decodificar_access_token

_bearer_scheme = HTTPBearer(auto_error=False)

CODIGO_DEBE_CAMBIAR_CLAVE = "debe_cambiar_clave"


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


async def get_usuario_autenticado(
    credenciales: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> Usuario:
    """
    Valida el JWT del header Authorization: Bearer <token> (Etapa 3): firma,
    usuario activo y sesion no cerrada por un cambio de contrasena. NO exige
    que la clave este al dia: solo lo usan /auth/me y /auth/cambiar-clave.
    """
    no_autorizado = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalido o expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credenciales is None:
        raise no_autorizado

    try:
        payload = decodificar_access_token(credenciales.credentials)
    except jwt.PyJWTError:
        raise no_autorizado

    try:
        usuario_id = UUID(payload.get("sub"))
    except (ValueError, TypeError, AttributeError):
        raise no_autorizado

    usuario = await session.get(Usuario, usuario_id)
    if usuario is None or not usuario.activo:
        raise no_autorizado

    # Un token emitido antes del ultimo cambio de clave deja de servir. `iat`
    # viene en segundos enteros: se compara contra la clave truncada al segundo.
    if usuario.clave_cambiada_en is not None:
        emitido = payload.get("iat")
        if not isinstance(emitido, int | float) or emitido < int(
            a_utc(usuario.clave_cambiada_en).timestamp()
        ):
            raise no_autorizado
    return usuario


async def get_current_usuario(
    usuario: Usuario = Depends(get_usuario_autenticado),
) -> Usuario:
    """Como get_usuario_autenticado, pero con cambio de clave obligatorio pendiente -> 403."""
    if usuario.debe_cambiar_clave:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "codigo": CODIGO_DEBE_CAMBIAR_CLAVE,
                "mensaje": "Debe cambiar su contraseña antes de continuar.",
            },
        )
    return usuario


def requerir_rol(*roles: RolUsuario):
    """Fabrica de dependencia: exige ademas que el usuario tenga uno de `roles`."""

    async def _verificar(usuario: Usuario = Depends(get_current_usuario)) -> Usuario:
        if usuario.rol not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permiso para esta accion",
            )
        return usuario

    return _verificar


requerir_dra = requerir_rol(RolUsuario.dra)

# "Cuenta con acceso total" = hoy el rol dra. La gestion de usuarios usa estos
# nombres genericos para que el futuro renombrado de roles sea un cambio acotado.
ROLES_ACCESO_TOTAL = (RolUsuario.dra,)
requerir_acceso_total = requerir_rol(*ROLES_ACCESO_TOTAL)


logger = logging.getLogger(__name__)

LARGO_MINIMO_CLAVE_SERVICIO = 32


async def requerir_clave_servicio(x_api_key: str | None = Header(default=None)) -> None:
    """
    Acceso de servicio de Alma (Etapa 6): compara X-Api-Key con VINCULACION_API_KEY.
    Solo se usa en los endpoints /interno/vinculacion; no crea usuarios ni JWT.
    Sin la variable (o con menos de 32 caracteres) la funcion esta apagada: 503.
    """
    clave = os.getenv("VINCULACION_API_KEY", "")
    if len(clave) < LARGO_MINIMO_CLAVE_SERVICIO:
        if clave:
            logger.error("VINCULACION_API_KEY tiene menos de 32 caracteres: funcion apagada")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Vinculacion no disponible")
    if x_api_key is None or not secrets.compare_digest(
        x_api_key.encode("utf-8"), clave.encode("utf-8")
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Clave de servicio invalida")
