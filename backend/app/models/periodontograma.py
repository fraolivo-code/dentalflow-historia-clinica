# app/models/periodontograma.py — 1.5, con la estructura confirmada:
# periodontograma_registro es por sitio (6 filas/diente); movilidad y
# furcacion, al ser a nivel de diente, viven en periodontograma_diente_resumen
# para no repetirse 6 veces por diente.
#
# NOTA PENDIENTE DE CONFIRMAR: "recesion (Cairo)" en la seccion 1.5 podria
# referirse a la clasificacion Cairo (RT1/RT2/RT3, diagnostica) en vez de a
# una medida en mm por sitio. Se modelo aqui como medida en mm (recesion_mm)
# por ser lo que encaja con el resto de las metricas por sitio (margen
# gingival, profundidad de sondaje) — confirmar con la Dra. antes de dar esto
# por cerrado; si es la clasificacion, se agrega como enum aparte.

import uuid

from sqlalchemy import Boolean, CheckConstraint, Enum, ForeignKey, SmallInteger
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import FurcacionGlickman, SitioPeriodontal
from app.models.common import AuditMixin, UUIDPk


class PeriodontogramaRegistro(Base, UUIDPk, AuditMixin):
    __tablename__ = "periodontograma_registro"

    paciente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paciente.id"), nullable=False, index=True
    )
    # No nullable: un levantamiento periodontal siempre ocurre dentro de una
    # visita formal (a diferencia de odontograma_hallazgo).
    visita_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visita.id"), nullable=False, index=True
    )
    numero_diente: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("diente_anatomia.numero_diente"), nullable=False, index=True
    )
    sitio: Mapped[SitioPeriodontal] = mapped_column(
        Enum(SitioPeriodontal, name="sitio_periodontal", native_enum=True), nullable=False
    )
    margen_gingival: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    profundidad_sondaje: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    nivel_insercion: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # calculado
    recesion_mm: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    sangrado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    placa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class PeriodontogramaDienteResumen(Base, UUIDPk, AuditMixin):
    """Movilidad (Miller) y furcacion (Glickman): a nivel de diente, no de sitio."""

    __tablename__ = "periodontograma_diente_resumen"

    paciente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paciente.id"), nullable=False, index=True
    )
    visita_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visita.id"), nullable=False, index=True
    )
    numero_diente: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("diente_anatomia.numero_diente"), nullable=False, index=True
    )
    movilidad: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # escala Miller 0-3
    # Solo aplica a molares: nullable.
    furcacion: Mapped[FurcacionGlickman | None] = mapped_column(
        Enum(
            FurcacionGlickman,
            name="furcacion_glickman",
            native_enum=True,
            # Mismo caso que HigieneBucal en app/models/visita.py: el tipo
            # Postgres se creo con los .value (I/II/III), no con los .name
            # (grado_i/...).
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint("movilidad BETWEEN 0 AND 3", name="ck_periodontograma_movilidad"),
    )
