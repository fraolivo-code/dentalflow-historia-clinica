# app/models/visita.py — Un registro por cada vez que el paciente entra
# fisicamente al consultorio (confirmado: incluye sesiones de un mismo
# tratamiento, controles, limpiezas). Version minima acordada, igual que
# `paciente` — ver nota en ese archivo.

import uuid
from datetime import date

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import HigieneBucal
from app.models.common import AuditMixin, UUIDPk


class Visita(Base, UUIDPk, AuditMixin):
    __tablename__ = "visita"

    paciente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paciente.id"), nullable=False, index=True
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    responsable: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=False
    )
    motivo_consulta: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Examen extraoral
    examen_extraoral_atm: Mapped[str | None] = mapped_column(Text, nullable=True)
    examen_extraoral_ganglios: Mapped[str | None] = mapped_column(Text, nullable=True)
    examen_extraoral_otros: Mapped[str | None] = mapped_column(Text, nullable=True)

    higiene: Mapped[HigieneBucal] = mapped_column(
        Enum(
            HigieneBucal,
            name="higiene_bucal",
            native_enum=True,
            # El tipo Postgres se creo con los .value (E/B/R/M/P, ver migracion
            # 0001), no con los .name (excelente/buena/...) — sin esto,
            # SQLAlchemy manda el .name por defecto y Postgres lo rechaza.
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    tejidos_blandos: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Examen complementario
    examen_rx_periapical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    examen_ex_pc: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    examen_rx_panoramica: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    examen_rutina_quirurgica: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    examen_otras: Mapped[str | None] = mapped_column(Text, nullable=True)

    hallazgos: Mapped[str | None] = mapped_column(Text, nullable=True)
