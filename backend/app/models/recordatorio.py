# app/models/recordatorio.py — Aviso con fecha que la Dra. deja en la ficha: proximo control,
# «Rx pan para tal fecha», blanqueamiento... La nota de la visita sigue siendo el registro principal.
import uuid
from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Text, false
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import AuditMixin, UUIDPk


class Recordatorio(Base, UUIDPk, AuditMixin):
    __tablename__ = "recordatorio"

    paciente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paciente.id"), nullable=False, index=True
    )
    visita_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visita.id"), nullable=True
    )
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    hecho: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    hecho_fecha: Mapped[date | None] = mapped_column(Date, nullable=True)
