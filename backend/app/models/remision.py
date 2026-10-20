# app/models/remision.py — Rol de especialista (19/10/2026, migracion 0038).
# Diseno: docs/proceso-trabajo-caso-334.md, seccion 16.
#
# - Remision: la Dra. remite un paciente a un especialista (con los dientes que le conciernen, o toda la
#   boca). Es lo que le da acceso a ESE paciente; termina solo cuando la Dra. la retira.
# - AtencionEspecialista: lo que el especialista hizo, firmado por el.
# - AccesoPaciente: registro de quien miro que paciente (y de los intentos fallidos de clave de autorizacion).
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, SmallInteger, String, Text, false
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import AuditMixin, UUIDPk, ahora


class Remision(Base, UUIDPk, AuditMixin):
    __tablename__ = "remision"

    paciente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paciente.id"), nullable=False, index=True
    )
    # Cuenta (usuario con rol especialista) a la que se le da acceso.
    especialista_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=False, index=True
    )
    motivo: Mapped[str] = mapped_column(Text, nullable=False)
    # Sin dientes concretos (ej. periodoncia): ve las notas ligadas a cualquier diente.
    toda_la_boca: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    retirada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retirada_por: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True
    )


class RemisionDiente(Base):
    __tablename__ = "remision_diente"

    remision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("remision.id", ondelete="CASCADE"), primary_key=True
    )
    numero_diente: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)


class AtencionEspecialista(Base, UUIDPk, AuditMixin):
    __tablename__ = "atencion_especialista"

    paciente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paciente.id"), nullable=False, index=True
    )
    remision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("remision.id"), nullable=False, index=True
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    procedimiento: Mapped[str] = mapped_column(String(300), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    indicaciones: Mapped[str | None] = mapped_column(Text, nullable=True)


class AtencionDiente(Base):
    __tablename__ = "atencion_diente"

    atencion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("atencion_especialista.id", ondelete="CASCADE"), primary_key=True
    )
    numero_diente: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)


class AccesoPaciente(Base, UUIDPk):
    """Quien abrio que paciente y cuando; tambien los intentos fallidos de clave de autorizacion."""

    __tablename__ = "acceso_paciente"

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=False, index=True
    )
    paciente_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paciente.id"), nullable=True, index=True
    )
    momento: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora, nullable=False)
    accion: Mapped[str] = mapped_column(String(60), nullable=False)
