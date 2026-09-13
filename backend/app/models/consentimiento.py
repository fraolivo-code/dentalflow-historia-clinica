# app/models/consentimiento.py — 0.1. Reemplaza el antiguo campo unico
# consentimiento_archivo en paciente: permite guardar el de tratamiento
# (ya aprobado por la Dra.) y el de almacenamiento digital por separado.
#
# Solo lleva creado_en/creado_por (no actualizado_en/actualizado_por): un
# consentimiento no se edita, se agrega uno nuevo si cambia.
#
# `archivo`: ruta o URL de texto al escaneo/foto. El almacenamiento fisico
# (Railway volume, S3, u otro) todavia no esta decidido — no bloquea el
# esquema, se resuelve cuando se construya la subida de archivos.

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import TipoConsentimiento
from app.models.common import ahora


class Consentimiento(Base):
    __tablename__ = "consentimiento"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    paciente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("paciente.id"), nullable=False, index=True
    )
    tipo: Mapped[TipoConsentimiento] = mapped_column(
        Enum(TipoConsentimiento, name="tipo_consentimiento", native_enum=True), nullable=False
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    archivo: Mapped[str] = mapped_column(String(1000), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora, nullable=False)
    creado_por: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=False
    )
