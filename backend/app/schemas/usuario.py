from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.enums import RolUsuario


class UsuarioCreate(BaseModel):
    nombre: str
    rol: RolUsuario
    password: str
    email: str | None = None
    activo: bool = True


class UsuarioUpdate(BaseModel):
    """Campos opcionales: solo se cambia lo que viene en el pedido."""

    activo: bool | None = None
    rol: RolUsuario | None = None
    email: str | None = None
    # UUID para vincular, null para desvincular, ausente para no tocar (04/10/2026).
    profesional_tratante_id: UUID | None = None


class ProfesionalVinculadoRead(BaseModel):
    id: UUID
    nombre: str


class UsuarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nombre: str
    rol: RolUsuario
    activo: bool
    creado_en: datetime
    email: str | None = None
    debe_cambiar_clave: bool = False
    ultimo_login: datetime | None = None
    bloqueado: bool = False
    # Profesional que firma los documentos con esta cuenta (null si no hay).
    profesional: ProfesionalVinculadoRead | None = None


class ReinicioClaveRespuesta(BaseModel):
    # Se devuelve una sola vez; no se guarda en claro ni se registra.
    password_temporal: str
