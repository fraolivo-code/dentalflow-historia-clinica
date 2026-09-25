# app/models/constancia_asistencia.py — Documento 1 de 5 de la Etapa 5 (PDF),
# especificado el 19/09/2026. Solo confirma que el paciente asistio a consulta,
# para uso laboral: a proposito NO guarda motivo ni diagnostico, para no
# exponer informacion clinica al empleador.

import uuid
from datetime import date, time

from sqlalchemy import CheckConstraint, Date, ForeignKey, Text, Time
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import AuditMixin, UUIDPk


class ConstanciaAsistencia(Base, UUIDPk, AuditMixin):
    __tablename__ = "constancia_asistencia"
    __table_args__ = (
        CheckConstraint(
            "hora_inicio IS NULL OR hora_fin IS NULL OR hora_fin > hora_inicio",
            name="ck_constancia_asistencia_horario",
        ),
    )

    paciente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paciente.id"), nullable=False, index=True
    )
    visita_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visita.id"), nullable=False
    )
    fecha_emision: Mapped[date] = mapped_column(Date, nullable=False)
    # Se cargan al emitir: la visita no registra hora.
    hora_inicio: Mapped[time | None] = mapped_column(Time, nullable=True)
    hora_fin: Mapped[time | None] = mapped_column(Time, nullable=True)
    texto_adicional: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Sale del profesional vinculado al usuario autenticado, nunca del body.
    emitida_por: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profesional_tratante.id"), nullable=False
    )
