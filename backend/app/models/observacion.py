# app/models/observacion.py — Etapa 3, seccion 9. Espacio propio del
# paciente, no atado a que exista una visita activa (visita_id queda
# nullable). Tampoco tiene tabla de campos en ningun documento — se
# reconstruye igual que bitacora_tratamiento (ver ese archivo).

import uuid
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import TipoObservacion
from app.models.common import AuditMixin, UUIDPk


class Observacion(Base, UUIDPk, AuditMixin):
    __tablename__ = "observacion"

    paciente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paciente.id"), nullable=False, index=True
    )
    visita_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visita.id"), nullable=True
    )
    tipo: Mapped[TipoObservacion] = mapped_column(
        Enum(TipoObservacion, name="tipo_observacion", native_enum=True), nullable=False
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
