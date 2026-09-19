from collections.abc import AsyncGenerator
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session
from app.enums import RolUsuario
from app.models.usuario import Usuario
from app.security import decodificar_access_token

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


async def get_current_usuario(
    credenciales: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> Usuario:
    """Valida el JWT del header Authorization: Bearer <token> (Etapa 3)."""
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

    usuario_id = payload.get("sub")
    if usuario_id is None:
        raise no_autorizado

    usuario = await session.get(Usuario, UUID(usuario_id))
    if usuario is None or not usuario.activo:
        raise no_autorizado
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
