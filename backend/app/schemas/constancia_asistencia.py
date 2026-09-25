from datetime import date, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.schemas.common import AuditRead


class ConstanciaAsistenciaCreate(BaseModel):
    # emitida_por NO se acepta del cliente: sale del profesional vinculado al
    # usuario autenticado (ver constancias_asistencia.py).
    visita_id: UUID
    fecha_emision: date | None = None  # None = hoy (hora de Venezuela)
    hora_inicio: time | None = None
    hora_fin: time | None = None
    texto_adicional: str | None = None

    @field_validator("texto_adicional")
    @classmethod
    def _vacio_es_none(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        return v.strip()

    @model_validator(mode="after")
    def _horario_en_orden(self):
        if self.hora_inicio and self.hora_fin and self.hora_fin <= self.hora_inicio:
            raise ValueError("hora_fin debe ser posterior a hora_inicio")
        return self


class ConstanciaAsistenciaRead(AuditRead):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paciente_id: UUID
    visita_id: UUID
    fecha_emision: date
    hora_inicio: time | None
    hora_fin: time | None
    texto_adicional: str | None
    emitida_por: UUID
