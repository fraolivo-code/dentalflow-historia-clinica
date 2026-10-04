# app/services/auditoria.py — Registro de acciones sobre usuarios (spec A.1/A.3).
# `detalle` es texto corto y nunca lleva contrasenas, tokens ni el nombre
# escrito en un login fallido. Purga perezosa una vez al dia (mismo patron que
# services/vinculacion.py): auditoria 365 dias; tokens de recuperacion
# vencidos o usados con mas de 7 dias.

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auditoria_usuario import AuditoriaUsuario
from app.models.token_recuperacion import TokenRecuperacion

DIAS_RETENCION_AUDITORIA = 365
DIAS_RETENCION_TOKENS = 7
INTERVALO_PURGA = timedelta(hours=24)

_ultima_purga: datetime | None = None


def registrar(
    session: AsyncSession,
    accion: str,
    actor_id: uuid.UUID | None = None,
    objetivo_id: uuid.UUID | None = None,
    detalle: str | None = None,
) -> None:
    """Agrega la fila a la sesion; la confirma quien llama (misma transaccion)."""
    session.add(
        AuditoriaUsuario(
            accion=accion, actor_id=actor_id, usuario_objetivo_id=objetivo_id, detalle=detalle
        )
    )


async def purgar_antiguos(session: AsyncSession, ahora: datetime | None = None) -> None:
    referencia = ahora or datetime.now(timezone.utc)
    if referencia.tzinfo is None:
        referencia = referencia.replace(tzinfo=timezone.utc)
    limite_tokens = referencia - timedelta(days=DIAS_RETENCION_TOKENS)
    await session.execute(
        delete(AuditoriaUsuario).where(
            AuditoriaUsuario.fecha < referencia - timedelta(days=DIAS_RETENCION_AUDITORIA)
        )
    )
    await session.execute(
        delete(TokenRecuperacion).where(
            or_(
                TokenRecuperacion.expira_en < limite_tokens,
                and_(
                    TokenRecuperacion.usado_en.is_not(None),
                    TokenRecuperacion.usado_en < limite_tokens,
                ),
            )
        )
    )
    await session.commit()


async def purgar_si_corresponde(session: AsyncSession, ahora: datetime | None = None) -> bool:
    """Purga como maximo una vez cada 24 h. Nunca levanta excepciones."""
    global _ultima_purga
    try:
        referencia = ahora or datetime.now(timezone.utc)
        if _ultima_purga is not None and referencia - _ultima_purga < INTERVALO_PURGA:
            return False
        _ultima_purga = referencia  # antes de purgar: un fallo no se reintenta en cada llamada
        await purgar_antiguos(session, referencia)
        return True
    except Exception:  # noqa: BLE001
        return False
