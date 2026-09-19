# app/models/antecedente.py — Etapa 3, seccion 2. Catalogo editable (no lista
# fija): la Dra. puede agregar categorias sin tocar el esquema.

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import AuditMixin, UUIDPk


class Antecedente(Base, UUIDPk):
    """
    Catalogo de referencia, igual en espiritu a diente_anatomia (sin campos
    de auditoria: no es un dato clinico de un paciente, es la lista de
    categorias disponible).

    requiere_detalle: no viene textual en la especificacion — se agrega para
    que Hepatitis/Convulsiones/Operaciones (las 3 que piden detalle
    obligatorio en paciente_antecedente.detalle) queden marcadas en el propio
    catalogo, en vez de hardcodear sus nombres en la capa de API. Si una
    categoria nueva que la Dra. agregue tambien necesita detalle, se marca
    aqui sin tocar codigo.
    """

    __tablename__ = "antecedente"

    nombre: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    requiere_detalle: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class PacienteAntecedente(Base, UUIDPk, AuditMixin):
    """Estado actual de cada categoria de antecedente para un paciente."""

    __tablename__ = "paciente_antecedente"

    paciente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paciente.id"), nullable=False, index=True
    )
    antecedente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("antecedente.id"), nullable=False, index=True
    )
    presente: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Obligatorio en la UI (no en la DB) cuando presente=True para las 3
    # categorias con requiere_detalle=True (seccion 2 de la especificacion).
    detalle: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("paciente_id", "antecedente_id", name="uq_paciente_antecedente"),
    )
