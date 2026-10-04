# app/models/auditoria_usuario.py — Registro de acciones sobre usuarios e inicios
# de sesion. NUNCA guarda contrasenas, tokens ni el nombre escrito en un login
# fallido (podria ser una contrasena tipeada en el campo equivocado).
# Retencion: 365 dias (ver services/auditoria.py).

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import ahora


class AuditoriaUsuario(Base):
    __tablename__ = "auditoria_usuario"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Con indice: la purga filtra por esta columna.
    fecha: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ahora, nullable=False, index=True
    )
    # None en acciones sin sesion (login fallido).
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True
    )
    accion: Mapped[str] = mapped_column(String(40), nullable=False)
    usuario_objetivo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True
    )
    detalle: Mapped[str | None] = mapped_column(String(200), nullable=True)
