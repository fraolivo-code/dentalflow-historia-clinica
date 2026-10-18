from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.enums import EstadoExamen, TipoExamen
from app.schemas.common import AuditRead


def _limpio(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v or None


class ExamenCreate(BaseModel):
    tipo: TipoExamen
    descripcion: str | None = None
    fecha_indicacion: date
    visita_id: UUID | None = None
    tratamiento_id: UUID | None = None
    enlace: str | None = None

    @field_validator("enlace")
    @classmethod
    def _enlace_limpio(cls, v: str | None) -> str | None:
        v = _limpio(v)
        if v is not None and len(v) > 1000:
            raise ValueError("El enlace no puede superar 1000 caracteres")
        return v

    @field_validator("descripcion")
    @classmethod
    def _descripcion_limpia(cls, v: str | None) -> str | None:
        v = _limpio(v)
        if v is not None and len(v) > 300:
            raise ValueError("La descripción no puede superar 300 caracteres")
        return v


class ExamenTraido(BaseModel):
    fecha_traido: date
    hallazgos: str | None = None

    @field_validator("hallazgos")
    @classmethod
    def _hallazgos_limpios(cls, v: str | None) -> str | None:
        return _limpio(v)


class ExamenUpdate(BaseModel):
    """Correccion de texto (PATCH parcial): lo que se escribio mal al indicarlo o al registrarlo."""

    descripcion: str | None = None
    hallazgos: str | None = None
    enlace: str | None = None

    @field_validator("descripcion", "hallazgos", "enlace")
    @classmethod
    def _limpio(cls, v: str | None) -> str | None:
        return _limpio(v)


class ExamenRead(AuditRead):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paciente_id: UUID
    visita_id: UUID | None
    tratamiento_id: UUID | None
    tipo: TipoExamen
    descripcion: str | None
    fecha_indicacion: date
    estado: EstadoExamen
    fecha_traido: date | None
    hallazgos: str | None
    enlace: str | None
