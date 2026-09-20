from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.enums import TipoObservacion
from app.schemas.common import AuditRead


class ObservacionCreate(BaseModel):
    visita_id: UUID | None = None
    tipo: TipoObservacion
    fecha: date
    texto: str


class ObservacionRead(AuditRead):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paciente_id: UUID
    visita_id: UUID | None
    tipo: TipoObservacion
    fecha: date
    texto: str
