# app/models/usuario.py — Etapa 3: login real (Fase 2). `nombre` funciona
# tambien como identificador de login (el modelo no tiene un campo de
# username/email separado), por eso es unico.

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, false
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import RolUsuario
from app.models.common import a_utc, ahora


class Usuario(Base):
    __tablename__ = "usuario"
    # Unico entre los no nulos (los NULL no chocan en Postgres ni en SQLite).
    __table_args__ = (Index("uq_usuario_email", "email", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    nombre: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    rol: Mapped[RolUsuario] = mapped_column(
        Enum(RolUsuario, name="rol_usuario", native_enum=True), nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora, nullable=False)
    # Gestion de contrasenas y usuarios (migracion 0018).
    # Minusculas y sin espacios; unico (ver __table_args__).
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    debe_cambiar_clave: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    # Los tokens emitidos antes de este momento dejan de servir.
    clave_cambiada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    intentos_fallidos: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ultimo_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    creado_por: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True
    )
    actualizado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def bloqueado(self) -> bool:
        """Calculado: bloqueado_hasta posterior a ahora (no es una columna)."""
        return self.bloqueado_hasta is not None and a_utc(self.bloqueado_hasta) > ahora()
