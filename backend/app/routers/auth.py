import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, get_usuario_autenticado
from app.models.common import a_utc, ahora
from app.models.token_recuperacion import TokenRecuperacion
from app.models.usuario import Usuario
from app.schemas.auth import (
    CambiarClaveRequest,
    LoginRequest,
    MensajeResponse,
    OlvideClaveRequest,
    RestablecerClaveRequest,
    TokenResponse,
)
from app.schemas.usuario import UsuarioRead
from app.security import crear_access_token, hash_password, verificar_password
from app.services import auditoria, correo
from app.services.passwords import normalizar_email, normalizar_nombre, validar_password

router = APIRouter(prefix="/auth", tags=["auth"])

INTENTOS_PARA_BLOQUEO = 5
MINUTOS_BLOQUEO = 15
MINUTOS_VIGENCIA_TOKEN = 30
PEDIDOS_RECUPERACION_POR_HORA = 3

# Mensaje unico para todos los rechazos de login: no revela si fallo el usuario,
# la contrasena o si la cuenta esta bloqueada.
MENSAJE_LOGIN_RECHAZADO = (
    "Usuario o contraseña incorrectos, o la cuenta está bloqueada temporalmente. "
    "Intente de nuevo en unos minutos."
)
MENSAJE_CAMBIAR_CLAVE_RECHAZADO = (
    "La contraseña actual no es correcta, o la cuenta está bloqueada temporalmente. "
    "Intente de nuevo en unos minutos."
)
MENSAJE_OLVIDE_CLAVE = (
    "Si el correo está registrado, recibirá un enlace para restablecer su contraseña."
)
MENSAJE_ENLACE_INVALIDO = "El enlace no es válido o ya venció. Solicite uno nuevo."


def _registrar_clave_incorrecta(
    session: AsyncSession, usuario: Usuario, momento: datetime, detalle: str | None = None
) -> None:
    """Suma un intento fallido (mismo contador para login y cambiar-clave) y bloquea al 5.o."""
    usuario.intentos_fallidos += 1
    auditoria.registrar(
        session, "login_fallido", actor_id=None if detalle is None else usuario.id,
        objetivo_id=usuario.id, detalle=detalle,
    )
    if usuario.intentos_fallidos >= INTENTOS_PARA_BLOQUEO:
        usuario.bloqueado_hasta = momento + timedelta(minutes=MINUTOS_BLOQUEO)
        usuario.intentos_fallidos = 0
        auditoria.registrar(session, "cuenta_bloqueada", objetivo_id=usuario.id)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@router.post("/login", response_model=TokenResponse)
async def login(datos: LoginRequest, session: AsyncSession = Depends(get_session)):
    momento = ahora()
    resultado = await session.execute(
        select(Usuario).where(Usuario.nombre == normalizar_nombre(datos.nombre))
    )
    usuario = resultado.scalar_one_or_none()

    rechazo = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail=MENSAJE_LOGIN_RECHAZADO
    )

    # Nunca se guarda el nombre escrito: podria ser una contrasena en el campo equivocado.
    if usuario is None:
        auditoria.registrar(session, "login_fallido")
        await session.commit()
        raise rechazo

    bloqueada = usuario.bloqueado_hasta is not None and a_utc(usuario.bloqueado_hasta) > momento
    if bloqueada or not usuario.activo:
        auditoria.registrar(
            session,
            "login_fallido",
            objetivo_id=usuario.id,
            detalle="cuenta bloqueada" if bloqueada else "cuenta inactiva",
        )
        await session.commit()
        raise rechazo

    if not verificar_password(datos.password, usuario.password_hash):
        _registrar_clave_incorrecta(session, usuario, momento)
        await session.commit()
        raise rechazo

    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    usuario.ultimo_login = momento
    auditoria.registrar(session, "login_ok", actor_id=usuario.id, objetivo_id=usuario.id)
    await session.commit()
    await auditoria.purgar_si_corresponde(session)

    token = crear_access_token(usuario.id, usuario.rol.value)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UsuarioRead)
async def me(usuario: Usuario = Depends(get_usuario_autenticado)):
    # Sin exigir clave al dia: el frontend lo usa para detectar debe_cambiar_clave.
    return usuario


@router.post("/cambiar-clave", response_model=TokenResponse)
async def cambiar_clave(
    datos: CambiarClaveRequest,
    usuario: Usuario = Depends(get_usuario_autenticado),
    session: AsyncSession = Depends(get_session),
):
    momento = ahora()
    # Misma defensa que el login: con la cuenta bloqueada no se prueba ninguna clave, y
    # una clave actual incorrecta suma al mismo contador (5 intentos -> 15 minutos).
    bloqueada = usuario.bloqueado_hasta is not None and a_utc(usuario.bloqueado_hasta) > momento
    if bloqueada or not verificar_password(datos.clave_actual, usuario.password_hash):
        if bloqueada:
            auditoria.registrar(
                session, "login_fallido", actor_id=usuario.id, objetivo_id=usuario.id,
                detalle="cambiar-clave",
            )
        else:
            _registrar_clave_incorrecta(session, usuario, momento, detalle="cambiar-clave")
        await session.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, MENSAJE_CAMBIAR_CLAVE_RECHAZADO)
    error = validar_password(datos.clave_nueva, usuario.nombre, usuario.email)
    if error is None and datos.clave_nueva == datos.clave_actual:
        error = "La nueva contraseña debe ser distinta de la actual."
    if error:
        raise HTTPException(422, error)

    usuario.password_hash = hash_password(datos.clave_nueva)
    usuario.clave_cambiada_en = momento
    usuario.debe_cambiar_clave = False
    usuario.intentos_fallidos = 0
    usuario.actualizado_en = momento
    auditoria.registrar(session, "clave_cambiada", actor_id=usuario.id, objetivo_id=usuario.id)
    await session.commit()

    # Token nuevo: el anterior queda invalidado por clave_cambiada_en.
    return TokenResponse(access_token=crear_access_token(usuario.id, usuario.rol.value))


@router.post("/olvide-clave", response_model=MensajeResponse)
async def olvide_clave(
    datos: OlvideClaveRequest,
    segundo_plano: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """Siempre 200 con el mismo mensaje; el correo se envia despues de responder."""
    respuesta = MensajeResponse(mensaje=MENSAJE_OLVIDE_CLAVE)
    email = normalizar_email(datos.email)
    if email is None:
        return respuesta
    resultado = await session.execute(
        select(Usuario).where(Usuario.email == email, Usuario.activo.is_(True))
    )
    usuario = resultado.scalar_one_or_none()
    if usuario is None:
        return respuesta

    momento = ahora()
    pedidos = await session.scalar(
        select(func.count())
        .select_from(TokenRecuperacion)
        .where(
            TokenRecuperacion.usuario_id == usuario.id,
            TokenRecuperacion.creado_en > momento - timedelta(hours=1),
        )
    )
    if (pedidos or 0) >= PEDIDOS_RECUPERACION_POR_HORA:
        return respuesta

    # Los enlaces anteriores sin usar dejan de servir.
    anteriores = await session.execute(
        select(TokenRecuperacion).where(
            TokenRecuperacion.usuario_id == usuario.id, TokenRecuperacion.usado_en.is_(None)
        )
    )
    for anterior in anteriores.scalars():
        anterior.usado_en = momento

    token = secrets.token_urlsafe(32)
    session.add(
        TokenRecuperacion(
            usuario_id=usuario.id,
            token_hash=_hash_token(token),
            expira_en=momento + timedelta(minutes=MINUTOS_VIGENCIA_TOKEN),
        )
    )
    auditoria.registrar(session, "recuperacion_solicitada", objetivo_id=usuario.id)
    await session.commit()

    segundo_plano.add_task(correo.enviar_recuperacion, email, token)
    return respuesta


@router.post("/restablecer-clave", response_model=MensajeResponse)
async def restablecer_clave(
    datos: RestablecerClaveRequest, session: AsyncSession = Depends(get_session)
):
    momento = ahora()
    invalido = HTTPException(status.HTTP_400_BAD_REQUEST, MENSAJE_ENLACE_INVALIDO)

    resultado = await session.execute(
        select(TokenRecuperacion).where(TokenRecuperacion.token_hash == _hash_token(datos.token))
    )
    registro = resultado.scalar_one_or_none()
    if registro is None or registro.usado_en is not None or a_utc(registro.expira_en) <= momento:
        raise invalido
    usuario = await session.get(Usuario, registro.usuario_id)
    if usuario is None or not usuario.activo:
        raise invalido

    # Si la clave no cumple las reglas el enlace NO se consume: puede reintentar.
    error = validar_password(datos.clave_nueva, usuario.nombre, usuario.email)
    if error:
        raise HTTPException(422, error)

    usuario.password_hash = hash_password(datos.clave_nueva)
    usuario.clave_cambiada_en = momento
    usuario.debe_cambiar_clave = False
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    usuario.actualizado_en = momento
    registro.usado_en = momento
    auditoria.registrar(session, "clave_restablecida", objetivo_id=usuario.id)
    await session.commit()
    return MensajeResponse(mensaje="Su contraseña fue actualizada. Ya puede iniciar sesión.")
