from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_usuario, get_session
from app.models.usuario import Usuario
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.usuario import UsuarioRead
from app.security import crear_access_token, verificar_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(datos: LoginRequest, session: AsyncSession = Depends(get_session)):
    resultado = await session.execute(select(Usuario).where(Usuario.nombre == datos.nombre))
    usuario = resultado.scalar_one_or_none()

    # Mensaje generico: no revela si fallo el usuario o la contrasena.
    if usuario is None or not usuario.activo or not verificar_password(
        datos.password, usuario.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contrasena incorrectos",
        )

    token = crear_access_token(usuario.id, usuario.rol.value)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UsuarioRead)
async def me(usuario: Usuario = Depends(get_current_usuario)):
    return usuario
