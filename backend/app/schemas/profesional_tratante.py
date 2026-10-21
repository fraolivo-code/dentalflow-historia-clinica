from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

# Datos del membrete (migracion 0039). `nombre` nunca puede quedar vacio; el resto es texto libre y se guarda sin
# espacios sobrantes (vacio = sin dato).
CAMPOS_MEMBRETE = ("especialidad", "direccion", "telefonos", "correo", "rif", "cov", "mpps")


def _limpio(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v or None


class ProfesionalTratanteCreate(BaseModel):
    nombre: str
    especialidad: str | None = None
    numero_colegiatura: str | None = None
    direccion: str | None = None
    telefonos: str | None = None
    correo: str | None = None
    rif: str | None = None
    cov: str | None = None
    mpps: str | None = None

    _limpiar = field_validator(*CAMPOS_MEMBRETE, "numero_colegiatura")(_limpio)

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El nombre no puede quedar vacío")
        return v


class ProfesionalTratanteUpdate(BaseModel):
    """PATCH parcial: solo se cambia lo que viene en el pedido."""

    nombre: str | None = None
    especialidad: str | None = None
    direccion: str | None = None
    telefonos: str | None = None
    correo: str | None = None
    rif: str | None = None
    cov: str | None = None
    mpps: str | None = None

    _limpiar = field_validator(*CAMPOS_MEMBRETE)(_limpio)

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("El nombre no puede quedar vacío")
        return v


class ProfesionalTratanteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nombre: str
    especialidad: str | None
    numero_colegiatura: str | None
    direccion: str | None = None
    telefonos: str | None = None
    correo: str | None = None
    rif: str | None = None
    cov: str | None = None
    mpps: str | None = None
