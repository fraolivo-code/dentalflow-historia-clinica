from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.common import AuditRead


class PacienteCreate(BaseModel):
    telefono_fijo: str | None = None
    movil: str
    nombre_completo: str
    fecha_nacimiento: date | None = None
    direccion: str | None = None
    email: str | None = None
    empresa_profesion_cargo: str | None = None
    referido_por: str = "N/A"
    fuma: bool = False
    fuma_detalle: str | None = None
    medicamentos_actuales: bool = False
    medicamentos_actuales_detalle: str | None = None
    tratamiento_medico_actual: str | None = None
    fecha_registro: date
    creado_por: UUID


class PacienteRead(AuditRead):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    telefono_fijo: str | None
    movil: str
    nombre_completo: str
    fecha_nacimiento: date | None
    direccion: str | None
    email: str | None
    empresa_profesion_cargo: str | None
    referido_por: str
    fuma: bool
    fuma_detalle: str | None
    medicamentos_actuales: bool
    medicamentos_actuales_detalle: str | None
    tratamiento_medico_actual: str | None
    fecha_registro: date
