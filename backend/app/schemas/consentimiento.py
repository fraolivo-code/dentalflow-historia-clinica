from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.enums import TipoConsentimiento


class ConsentimientoCreate(BaseModel):
    tipo: TipoConsentimiento
    fecha: date
    archivo: str
    tratamiento_id: UUID | None = None


class ConsentimientoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paciente_id: UUID
    tratamiento_id: UUID | None
    tipo: TipoConsentimiento
    fecha: date
    archivo: str
    creado_en: datetime
    creado_por: UUID
