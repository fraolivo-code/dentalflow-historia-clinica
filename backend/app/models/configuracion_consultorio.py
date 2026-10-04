# app/models/configuracion_consultorio.py — Portada configurable (Etapa 7).
# UNA sola fila (id fijo = 1, creada vacia por la migracion 0019). La imagen se
# guarda en la base (entra en el backup) y ya viene re-codificada y <= 1 MB.
# Lectura publica: no debe contener nada de pacientes.

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

ID_UNICO = 1


class ConfiguracionConsultorio(Base):
    __tablename__ = "configuracion_consultorio"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False, default=ID_UNICO)
    nombre: Mapped[str | None] = mapped_column(String(120), nullable=True)
    frase: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # deferred: la portada se lee en cada inicio de sesion y no necesita los bytes.
    imagen: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    # Cantidad de digitos (con ceros a la izquierda) del numero de historia.
    numero_ancho: Mapped[int] = mapped_column(Integer, nullable=False, default=4, server_default="4")
    imagen_tipo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    imagen_actualizada_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    actualizado_por: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=True
    )
    actualizado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
