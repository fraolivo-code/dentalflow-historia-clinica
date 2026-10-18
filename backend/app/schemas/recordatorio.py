from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.common import AuditRead


class RecordatorioCreate(BaseModel):
    texto: str
    fecha: date
    visita_id: UUID | None = None

    @field_validator("texto")
    @classmethod
    def _texto_obligatorio(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Escriba de qué es el recordatorio")
        return v


class RecordatorioUpdate(BaseModel):
    """PATCH parcial: corregir texto o fecha, o marcarlo hecho / pendiente."""

    texto: str | None = None
    fecha: date | None = None
    hecho: bool | None = None

    @field_validator("texto")
    @classmethod
    def _texto_no_vacio(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("Escriba de qué es el recordatorio")
        return v


class RecordatorioRead(AuditRead):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paciente_id: UUID
    visita_id: UUID | None
    texto: str
    fecha: date
    hecho: bool
    hecho_fecha: date | None
