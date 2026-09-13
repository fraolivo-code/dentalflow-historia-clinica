from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.enums import RolUsuario


class UsuarioCreate(BaseModel):
    nombre: str
    rol: RolUsuario
    activo: bool = True


class UsuarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nombre: str
    rol: RolUsuario
    activo: bool
    creado_en: datetime
