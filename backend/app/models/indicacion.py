# app/models/indicacion.py — Documento 2 de 5 de la Etapa 5 (PDF):
# indicaciones de tratamiento. Un catalogo de plantillas editable por la Dra.
# y la instancia entregada a cada paciente.

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import AuditMixin, UUIDPk


class PlantillaIndicacion(Base, UUIDPk, AuditMixin):
    """
    Sin borrado: una plantilla obsoleta simplemente se deja de usar. Las
    indicaciones ya entregadas no dependen de ella (guardan su propia copia).
    """

    __tablename__ = "plantilla_indicacion"

    nombre: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    # Texto libre, mismo criterio que tratamiento.tipo (sin catalogo cerrado).
    tipo_tratamiento: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contenido: Mapped[str] = mapped_column(Text, nullable=False)


class IndicacionTratamiento(Base, UUIDPk, AuditMixin):
    __tablename__ = "indicacion_tratamiento"

    paciente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paciente.id"), nullable=False, index=True
    )
    visita_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visita.id"), nullable=True
    )
    tratamiento_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tratamiento.id"), nullable=True
    )
    # De que plantilla partio (solo referencia historica).
    plantilla_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plantilla_indicacion.id"), nullable=True
    )
    # Copia independiente: editar la plantilla despues no altera lo ya
    # entregado a pacientes anteriores.
    contenido_final: Mapped[str] = mapped_column(Text, nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    # Firma del PDF. Sale del profesional vinculado al usuario autenticado,
    # nunca del body (mismo criterio que constancia_asistencia).
    emitida_por: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profesional_tratante.id"), nullable=False
    )
