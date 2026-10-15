# app/models/examen.py — Examenes solicitados (flujo de visitas, fase 3, 15/10/2026).
# La Dra. INDICA un examen (radiografia, tomografia...); cuando el paciente lo trae se
# registra que lo trajo, la fecha y los hallazgos si existen. No se guarda la imagen
# (eso es la Fase 3 del roadmap: imagenes clinicas).

import uuid
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import EstadoExamen, TipoExamen
from app.models.common import AuditMixin, UUIDPk


class ExamenSolicitado(Base, UUIDPk, AuditMixin):
    __tablename__ = "examen_solicitado"

    paciente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paciente.id"), nullable=False, index=True
    )
    visita_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visita.id"), nullable=True
    )
    tratamiento_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tratamiento.id"), nullable=True
    )
    tipo: Mapped[TipoExamen] = mapped_column(
        Enum(TipoExamen, name="tipo_examen", native_enum=True), nullable=False
    )
    # Texto libre: diente o zona ("diente 22"), o el nombre del examen si el tipo es "otro".
    descripcion: Mapped[str | None] = mapped_column(String(300), nullable=True)
    fecha_indicacion: Mapped[date] = mapped_column(Date, nullable=False)
    estado: Mapped[EstadoExamen] = mapped_column(
        Enum(EstadoExamen, name="estado_examen", native_enum=True),
        nullable=False,
        default=EstadoExamen.indicado,
    )
    fecha_traido: Mapped[date | None] = mapped_column(Date, nullable=True)
    hallazgos: Mapped[str | None] = mapped_column(Text, nullable=True)
