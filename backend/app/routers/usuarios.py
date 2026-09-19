from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, requerir_dra
from app.models.usuario import Usuario
from app.schemas.usuario import UsuarioCreate, UsuarioRead
from app.security import hash_password

router = APIRouter(prefix="/usuarios", tags=["usuarios"], dependencies=[Depends(requerir_dra)])


@router.post("", response_model=UsuarioRead, status_code=201)
async def crear_usuario(datos: UsuarioCreate, session: AsyncSession = Depends(get_session)):
    datos_usuario = datos.model_dump(exclude={"password"})
    usuario = Usuario(**datos_usuario, password_hash=hash_password(datos.password))
    session.add(usuario)
    await session.commit()
    await session.refresh(usuario)
    return usuario


@router.get("", response_model=list[UsuarioRead])
async def listar_usuarios(session: AsyncSession = Depends(get_session)):
    resultado = await session.execute(select(Usuario))
    return resultado.scalars().all()


@router.get("/{usuario_id}", response_model=UsuarioRead)
async def obtener_usuario(usuario_id: UUID, session: AsyncSession = Depends(get_session)):
    usuario = await session.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(404, "Usuario no encontrado")
    return usuario
