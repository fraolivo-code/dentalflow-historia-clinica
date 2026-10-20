# app/services/especialista.py — Reglas del rol de especialista (19/10/2026, docs/proceso-trabajo-caso-334.md sec. 16).
from collections import defaultdict
from datetime import date, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import RolUsuario
from app.models.common import a_utc, ahora
from app.models.remision import AccesoPaciente, AtencionDiente, Remision, RemisionDiente
from app.models.usuario import Usuario
from app.security import verificar_password

MAX_PIN_FALLIDOS = 5
VENTANA_PIN = timedelta(minutes=15)


def edad_en_anios(nacimiento: date | None, hoy: date | None = None) -> int | None:
    if nacimiento is None:
        return None
    hoy = hoy or date.today()
    return hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))


async def remision_activa(session: AsyncSession, usuario: Usuario, paciente_id: UUID) -> Remision:
    """
    La remision vigente de este especialista para este paciente. Sin ella el paciente «no existe»
    para el: la respuesta es la misma que la de un paciente inexistente.
    """
    remision = (
        await session.execute(
            select(Remision).where(
                Remision.paciente_id == paciente_id,
                Remision.especialista_id == usuario.id,
                Remision.retirada_en.is_(None),
            )
        )
    ).scalar_one_or_none()
    if remision is None:
        raise HTTPException(404, "Paciente no encontrado")
    return remision


async def dientes_por_remision(session: AsyncSession, remision_ids: list[UUID]) -> dict[UUID, list[int]]:
    resultado: dict[UUID, list[int]] = defaultdict(list)
    if remision_ids:
        filas = await session.execute(
            select(RemisionDiente.remision_id, RemisionDiente.numero_diente)
            .where(RemisionDiente.remision_id.in_(remision_ids))
            .order_by(RemisionDiente.numero_diente)
        )
        for remision_id, diente in filas:
            resultado[remision_id].append(diente)
    return resultado


async def dientes_por_atencion(session: AsyncSession, atencion_ids: list[UUID]) -> dict[UUID, list[int]]:
    resultado: dict[UUID, list[int]] = defaultdict(list)
    if atencion_ids:
        filas = await session.execute(
            select(AtencionDiente.atencion_id, AtencionDiente.numero_diente)
            .where(AtencionDiente.atencion_id.in_(atencion_ids))
            .order_by(AtencionDiente.numero_diente)
        )
        for atencion_id, diente in filas:
            resultado[atencion_id].append(diente)
    return resultado


def registrar_acceso(session: AsyncSession, usuario_id: UUID, paciente_id: UUID | None, accion: str) -> None:
    """Agrega la fila; la confirma quien llama."""
    session.add(AccesoPaciente(usuario_id=usuario_id, paciente_id=paciente_id, accion=accion))


async def autorizar_con_pin(session: AsyncSession, especialista: Usuario, pin: str | None) -> Usuario:
    """
    La clave de autorizacion (PIN de 6 digitos) de la Dra.: no es su clave de acceso. Tras 5 intentos fallidos
    en 15 minutos el especialista debe esperar. Devuelve la cuenta de la Dra. que autorizo.
    """
    desde = ahora() - VENTANA_PIN
    recientes = (
        await session.execute(
            select(AccesoPaciente.momento)
            .where(AccesoPaciente.usuario_id == especialista.id, AccesoPaciente.accion == "pin_fallido")
            .order_by(AccesoPaciente.momento.desc())
            .limit(MAX_PIN_FALLIDOS)
        )
    ).scalars().all()
    if sum(1 for m in recientes if a_utc(m) > desde) >= MAX_PIN_FALLIDOS:
        raise HTTPException(429, "Demasiados intentos con la clave de autorización. Espere 15 minutos.")

    dras = (
        await session.execute(
            select(Usuario).where(
                Usuario.rol == RolUsuario.dra,
                Usuario.activo.is_(True),
                Usuario.pin_autorizacion_hash.is_not(None),
            )
        )
    ).scalars().all()
    if not dras:
        raise HTTPException(409, "La Dra. todavía no definió su clave de autorización.")
    if pin:
        for dra in dras:
            if verificar_password(pin, dra.pin_autorizacion_hash):
                return dra
    registrar_acceso(session, especialista.id, None, "pin_fallido")
    await session.commit()
    raise HTTPException(403, "Clave de autorización incorrecta.")
