# app/models/periodontograma.py — 1.5, con la estructura confirmada:
# periodontograma_registro es por sitio (6 filas/diente); movilidad y
# furcacion, al ser a nivel de diente, viven en periodontograma_diente_resumen
# para no repetirse 6 veces por diente.
#
# Modelo clinico cerrado con la Dra. (24/09/2026, migracion 0010): recesion
# se registra de dos formas independientes, en mm (recesion_mm) y con la
# clasificacion de Cairo (recesion_cairo, opcional); nivel_insercion lo
# calcula el backend (margen_gingival + profundidad_sondaje).

import uuid

from sqlalchemy import Boolean, CheckConstraint, Enum, ForeignKey, SmallInteger, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import FurcacionGlickman, RecesionCairo, SitioPeriodontal
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
    # Con signo: positivo = recesion, negativo = inflamacion/cobertura.
    margen_gingival: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # Siempre positivo; puede superar 12 mm (tope 30 solo contra typos).
    profundidad_sondaje: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # Calculado por el backend: margen_gingival + profundidad_sondaje.
    nivel_insercion: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    recesion_mm: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    recesion_cairo: Mapped[RecesionCairo | None] = mapped_column(
        Enum(
            RecesionCairo,
            name="recesion_cairo",
            native_enum=True,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=True,
    )
    sangrado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    placa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        CheckConstraint("margen_gingival BETWEEN -6 AND 12", name="ck_perio_margen_gingival_rango"),
        CheckConstraint(
            "profundidad_sondaje BETWEEN 0 AND 30", name="ck_perio_profundidad_sondaje_rango"
        ),
        CheckConstraint("recesion_mm BETWEEN 0 AND 12", name="ck_perio_recesion_mm_rango"),
        CheckConstraint(
            "nivel_insercion = margen_gingival + profundidad_sondaje",
            name="ck_perio_nivel_insercion_calculado",
        ),
        UniqueConstraint(
            "visita_id", "numero_diente", "sitio", name="uq_perio_registro_visita_diente_sitio"
        ),
    )


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
    # Solo molares y 14/24 (ver admite_furcacion): nullable.
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
        CheckConstraint(
            "furcacion IS NULL OR numero_diente % 10 IN (6, 7, 8) OR numero_diente IN (14, 24)",
            name="ck_perio_furcacion_diente",
        ),
        UniqueConstraint("visita_id", "numero_diente", name="uq_perio_resumen_visita_diente"),
    )
