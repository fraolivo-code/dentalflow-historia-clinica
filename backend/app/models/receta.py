# app/models/receta.py — Documento 3 de 5 de la Etapa 5 (PDF): receta.
# Un catalogo editable de medicamentos, el encabezado de la receta y sus
# lineas (1 receta -> N medicamentos).

import uuid
from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Index, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import AuditMixin, UUIDPk


class Medicamento(Base, UUIDPk):
    """
    Catalogo de referencia, mismo patron que antecedente/profesional_tratante
    (sin auditoria). Texto libre al transcribir una receta se agrega solo si
    el nombre no existe. Sin borrado: un medicamento en desuso se deja de
    usar, y las recetas emitidas lo siguen referenciando.
    """

    __tablename__ = "medicamento"

    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    # Texto libre (ej. "Cápsulas de 500 mg"). Se imprime junto al nombre.
    presentacion_default: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Aparecen primero en el listado (y en la UI).
    es_favorito: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


# Unico sin distinguir mayusculas: "amoxicilina" y "Amoxicilina" son el mismo
# medicamento (lo necesita el auto-agregado de texto libre).
Index("uq_medicamento_nombre", func.lower(Medicamento.nombre), unique=True)


class Receta(Base, UUIDPk, AuditMixin):
    __tablename__ = "receta"

    paciente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paciente.id"), nullable=False, index=True
    )
    visita_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visita.id"), nullable=True
    )
    tratamiento_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tratamiento.id"), nullable=True
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    notas_generales: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Firma del PDF. Sale del profesional vinculado al usuario autenticado,
    # nunca del body (mismo criterio que constancia e indicaciones).
    emitida_por: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profesional_tratante.id"), nullable=False
    )


class RecetaMedicamento(Base, UUIDPk):
    """Una linea de la receta. Sin auditoria propia: se crea junto con la receta."""

    __tablename__ = "receta_medicamento"

    receta_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("receta.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Orden en que la Dra. cargo las lineas: es el orden impreso (1, 2, 3...).
    orden: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    medicamento_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("medicamento.id"), nullable=False
    )
    # Copia congelada al emitir (mismo criterio que contenido_final en
    # indicaciones): corregir el catalogo despues no altera una receta ya
    # entregada. El PDF imprime esto, no el nombre actual del catalogo.
    medicamento_nombre_impreso: Mapped[str] = mapped_column(String(200), nullable=False)
    presentacion_impresa: Mapped[str | None] = mapped_column(String(300), nullable=True)
    dosis: Mapped[str] = mapped_column(String(200), nullable=False)
    via: Mapped[str | None] = mapped_column(String(100), nullable=True)
    frecuencia: Mapped[str] = mapped_column(String(200), nullable=False)
    duracion: Mapped[str] = mapped_column(String(200), nullable=False)
    indicaciones_adicionales: Mapped[str | None] = mapped_column(Text, nullable=True)
