# app/models/paciente_cambio.py — Historial de correcciones de los datos del
# paciente (migracion 0021): quien, cuando, que campo, valor anterior y nuevo.
# Parte del registro de la historia clinica: SIN retencion automatica, nunca se
# purga ni se edita. Los valores son texto (fechas en ISO).

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import ahora


class PacienteCambio(Base):
    __tablename__ = "paciente_cambio"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paciente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paciente.id"), nullable=False, index=True
    )
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora, nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=False
    )
    campo: Mapped[str] = mapped_column(String(60), nullable=False)
    valor_anterior: Mapped[str | None] = mapped_column(Text, nullable=True)
    valor_nuevo: Mapped[str | None] = mapped_column(Text, nullable=True)
