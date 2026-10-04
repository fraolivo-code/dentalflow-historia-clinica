import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import ROLES_ACCESO_TOTAL, get_session, requerir_acceso_total
from app.enums import RolUsuario
from app.models.common import ahora
from app.models.usuario import Usuario
from app.schemas.usuario import ReinicioClaveRespuesta, UsuarioCreate, UsuarioRead, UsuarioUpdate
from app.security import hash_password
from app.services import auditoria
from app.services.passwords import (
    generar_temporal,
    normalizar_email,
    normalizar_nombre,
    validar_password,
)

router = APIRouter(
    prefix="/usuarios", tags=["usuarios"], dependencies=[Depends(requerir_acceso_total)]
)

# No se crean (ni se asignan) cuentas admin por la API.
ROLES_ASIGNABLES = (RolUsuario.dra, RolUsuario.asistente)
_PATRON_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validar_rol(rol: RolUsuario) -> None:
    if rol not in ROLES_ASIGNABLES:
        raise HTTPException(422, "Solo se pueden asignar los tipos de acceso dra y asistente.")


def _validar_email(email: str | None, rol: RolUsuario) -> str | None:
    """Devuelve el correo normalizado; el rol con acceso total lo exige."""
    email = normalizar_email(email)
    if email is None:
        if rol in ROLES_ACCESO_TOTAL:
            raise HTTPException(422, "El correo es obligatorio para las cuentas con acceso total.")
        return None
    if len(email) > 254 or not _PATRON_EMAIL.match(email):
        raise HTTPException(422, "El correo no tiene un formato válido.")
    return email


async def _existe(session: AsyncSession, columna, valor, excepto: UUID | None = None) -> bool:
    consulta = select(Usuario.id).where(columna == valor)
    if excepto is not None:
        consulta = consulta.where(Usuario.id != excepto)
    return (await session.execute(consulta.limit(1))).first() is not None


async def quedaria_sin_acceso_total(session: AsyncSession, objetivo: Usuario) -> bool:
    """True si, sin `objetivo`, no quedaria ninguna cuenta activa con acceso total."""
    otros = await session.scalar(
        select(func.count())
        .select_from(Usuario)
        .where(
            Usuario.id != objetivo.id,
            Usuario.activo.is_(True),
            Usuario.rol.in_(ROLES_ACCESO_TOTAL),
        )
    )
    return (otros or 0) == 0


@router.post("", response_model=UsuarioRead, status_code=201)
async def crear_usuario(
    datos: UsuarioCreate,
    session: AsyncSession = Depends(get_session),
    actor: Usuario = Depends(requerir_acceso_total),
):
    _validar_rol(datos.rol)
    nombre = normalizar_nombre(datos.nombre)
    if not nombre:
        raise HTTPException(422, "El nombre de usuario es obligatorio.")
    if len(nombre) > 200:
        raise HTTPException(422, "El nombre de usuario es demasiado largo (máximo 200).")
    email = _validar_email(datos.email, datos.rol)
    error = validar_password(datos.password, nombre, email)
    if error:
        raise HTTPException(422, error)

    if await _existe(session, Usuario.nombre, nombre):
        raise HTTPException(409, "Ya existe un usuario con ese nombre.")
    if email is not None and await _existe(session, Usuario.email, email):
        raise HTTPException(409, "Ya existe un usuario con ese correo.")

    usuario = Usuario(
        nombre=nombre,
        rol=datos.rol,
        email=email,
        activo=datos.activo,
        password_hash=hash_password(datos.password),
        debe_cambiar_clave=True,
        creado_por=actor.id,
    )
    session.add(usuario)
    try:
        await session.flush()
    except IntegrityError:  # pedido simultaneo con el mismo nombre o correo
        await session.rollback()
        raise HTTPException(409, "Ya existe un usuario con ese nombre o correo.")
    auditoria.registrar(
        session,
        "usuario_creado",
        actor_id=actor.id,
        objetivo_id=usuario.id,
        detalle=f"rol={datos.rol.value}",
    )
    await session.commit()
    await session.refresh(usuario)
    return usuario


@router.get("", response_model=list[UsuarioRead])
async def listar_usuarios(session: AsyncSession = Depends(get_session)):
    resultado = await session.execute(select(Usuario).order_by(Usuario.creado_en))
    return resultado.scalars().all()


@router.get("/{usuario_id}", response_model=UsuarioRead)
async def obtener_usuario(usuario_id: UUID, session: AsyncSession = Depends(get_session)):
    usuario = await session.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(404, "Usuario no encontrado")
    return usuario


@router.patch("/{usuario_id}", response_model=UsuarioRead)
async def actualizar_usuario(
    usuario_id: UUID,
    datos: UsuarioUpdate,
    session: AsyncSession = Depends(get_session),
    actor: Usuario = Depends(requerir_acceso_total),
):
    usuario = await session.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(404, "Usuario no encontrado")
    enviados = datos.model_fields_set
    es_el_mismo = usuario.id == actor.id

    cambia_activo = datos.activo is not None and datos.activo != usuario.activo
    cambia_rol = datos.rol is not None and datos.rol != usuario.rol
    rol_final = datos.rol if cambia_rol else usuario.rol

    if cambia_rol:
        _validar_rol(datos.rol)
    if es_el_mismo and cambia_activo and not datos.activo:
        raise HTTPException(409, "No puede desactivar su propia cuenta.")
    if es_el_mismo and cambia_rol:
        raise HTTPException(409, "No puede cambiar su propio tipo de acceso.")

    deja_acceso_total = (
        usuario.activo
        and usuario.rol in ROLES_ACCESO_TOTAL
        and ((cambia_activo and not datos.activo) or (cambia_rol and rol_final not in ROLES_ACCESO_TOTAL))
    )
    if deja_acceso_total and await quedaria_sin_acceso_total(session, usuario):
        raise HTTPException(409, "Debe quedar al menos una cuenta activa con acceso total.")

    # Con correo en el pedido se valida; si no, un cambio de rol a acceso total
    # exige que la cuenta ya tenga correo.
    cambia_email = False
    email = usuario.email
    if "email" in enviados:
        email = _validar_email(datos.email, rol_final)
        cambia_email = email != usuario.email
        if cambia_email and email is not None and await _existe(
            session, Usuario.email, email, excepto=usuario.id
        ):
            raise HTTPException(409, "Ya existe un usuario con ese correo.")
    elif cambia_rol:
        _validar_email(usuario.email, rol_final)

    if cambia_activo:
        usuario.activo = datos.activo
        auditoria.registrar(
            session,
            "usuario_activado" if datos.activo else "usuario_desactivado",
            actor_id=actor.id,
            objetivo_id=usuario.id,
        )
    if cambia_rol:
        auditoria.registrar(
            session,
            "rol_cambiado",
            actor_id=actor.id,
            objetivo_id=usuario.id,
            detalle=f"{usuario.rol.value}->{rol_final.value}",
        )
        usuario.rol = rol_final
    if cambia_email:
        usuario.email = email
        auditoria.registrar(session, "email_cambiado", actor_id=actor.id, objetivo_id=usuario.id)

    if cambia_activo or cambia_rol or cambia_email:
        usuario.actualizado_en = ahora()
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(409, "Ya existe un usuario con ese correo.")
        await session.refresh(usuario)
    return usuario


@router.post("/{usuario_id}/reiniciar-clave", response_model=ReinicioClaveRespuesta)
async def reiniciar_clave(
    usuario_id: UUID,
    respuesta: Response,
    session: AsyncSession = Depends(get_session),
    actor: Usuario = Depends(requerir_acceso_total),
):
    usuario = await session.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(404, "Usuario no encontrado")

    temporal = generar_temporal()
    momento = ahora()
    usuario.password_hash = hash_password(temporal)
    usuario.debe_cambiar_clave = True
    usuario.clave_cambiada_en = momento  # cierra las sesiones abiertas
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    usuario.actualizado_en = momento
    auditoria.registrar(session, "clave_reiniciada", actor_id=actor.id, objetivo_id=usuario.id)
    await session.commit()

    respuesta.headers["Cache-Control"] = "no-store"
    return ReinicioClaveRespuesta(password_temporal=temporal)
