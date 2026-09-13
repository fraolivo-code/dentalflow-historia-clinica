# app/models/paciente.py — Version minima acordada para tener FK reales desde
# el odontograma. Definida a partir de lo ya conversado con la Dra. en el
# proceso (proceso-automatizacion-odontologo-v2.md), no es el cierre formal
# completo de la Etapa 1: se espera ampliar (antecedentes estructurados via
# `antecedente`/`paciente_antecedente`, etc.) sin romper este esquema base.

from datetime import date

from sqlalchemy import Boolean, Date, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import AuditMixin, UUIDPk


class Paciente(Base, UUIDPk, AuditMixin):
    __tablename__ = "paciente"

    telefono_fijo: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Llave de vinculacion con Alma (fase1-whatsapp-bot): mismo numero de WhatsApp.
    movil: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    nombre_completo: Mapped[str] = mapped_column(String(300), nullable=False)
    fecha_nacimiento: Mapped[date | None] = mapped_column(Date, nullable=True)
    direccion: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(String(300), nullable=True)
    empresa_profesion_cargo: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # "N/A" para pacientes ya existentes transcritos sin este dato (confirmado con la Dra.).
    referido_por: Mapped[str] = mapped_column(String(300), nullable=False, default="N/A")
    fuma: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fuma_detalle: Mapped[str | None] = mapped_column(Text, nullable=True)
    medicamentos_actuales: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    medicamentos_actuales_detalle: Mapped[str | None] = mapped_column(Text, nullable=True)
    tratamiento_medico_actual: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha_registro: Mapped[date] = mapped_column(Date, nullable=False)
