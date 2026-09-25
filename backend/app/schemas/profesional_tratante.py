from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ProfesionalTratanteCreate(BaseModel):
    nombre: str
    especialidad: str | None = None
    numero_colegiatura: str | None = None


class ProfesionalTratanteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nombre: str
    especialidad: str | None
    numero_colegiatura: str | None
