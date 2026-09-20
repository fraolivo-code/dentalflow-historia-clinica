from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.common import AuditRead


class AntecedenteCreate(BaseModel):
    """Permite ampliar el catalogo (seccion 2: "apertura a agregar categorias")."""

    nombre: str
    requiere_detalle: bool = False


class AntecedenteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nombre: str
    requiere_detalle: bool


class PacienteAntecedenteUpsert(BaseModel):
    antecedente_id: UUID
    presente: bool = False
    detalle: str | None = None


class PacienteAntecedenteRead(AuditRead):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paciente_id: UUID
    antecedente_id: UUID
    presente: bool
    detalle: str | None
