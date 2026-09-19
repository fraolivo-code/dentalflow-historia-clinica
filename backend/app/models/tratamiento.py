# app/models/tratamiento.py — Etapa 3, seccion 6. El "expediente" de un
# proceso clinico multisesion (endodoncia, protesis, ortodoncia, etc.),
# distinto de una entrada suelta de bitacora_tratamiento.

import uuid
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import EstadoTratamiento, OrigenTratamiento
from app.models.common import AuditMixin, UUIDPk


class Tratamiento(Base, UUIDPk, AuditMixin):
    __tablename__ = "tratamiento"

    paciente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paciente.id"), nullable=False, index=True
    )
    # Texto libre, no lista fija: el tipo de tratamiento no esta acotado a un
    # catalogo cerrado en la especificacion ("endodoncia, protesis fija,
    # implante, ortodoncia, limpieza (multisesion), etc.") — mismo criterio de
    # papel->digital sin desplegable cerrado usado en profesional_tratante.
    tipo: Mapped[str] = mapped_column(String(200), nullable=False)
    estado: Mapped[EstadoTratamiento] = mapped_column(
        Enum(EstadoTratamiento, name="estado_tratamiento", native_enum=True), nullable=False
    )
    origen: Mapped[OrigenTratamiento] = mapped_column(
        Enum(OrigenTratamiento, name="origen_tratamiento", native_enum=True), nullable=False
    )
    # Solo si origen = remitido_externo.
    origen_detalle: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date | None] = mapped_column(Date, nullable=True)
    profesional_tratante_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profesional_tratante.id"), nullable=False
    )
    notas_relevantes: Mapped[str | None] = mapped_column(Text, nullable=True)


class TratamientoDiente(Base, UUIDPk, AuditMixin):
    """Puente para tratamientos sobre varios dientes o un espacio (ej. protesis)."""

    __tablename__ = "tratamiento_diente"

    tratamiento_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tratamiento.id"), nullable=False, index=True
    )
    numero_diente: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("diente_anatomia.numero_diente"), nullable=False, index=True
    )
