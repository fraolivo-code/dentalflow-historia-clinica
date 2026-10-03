# app/models/consulta_vinculacion.py — Etapa 6, A.4: registro de las consultas
# de Alma. Minimo a proposito: NO guarda el nombre que escribio la persona.
# Retencion: 90 dias (ver services/vinculacion.py).

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import ahora


class ConsultaVinculacion(Base):
    __tablename__ = "consulta_vinculacion"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Con indice: la purga filtra por esta columna.
    fecha: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ahora, nullable=False, index=True
    )
    endpoint: Mapped[str] = mapped_column(String(50), nullable=False)
    # None si el telefono recibido no se pudo normalizar.
    movil_normalizado: Mapped[str | None] = mapped_column(String(15), nullable=True)
    # registrado | no_registrado | coincide | no_coincide | pedir_apellido
    resultado: Mapped[str] = mapped_column(String(20), nullable=False)
