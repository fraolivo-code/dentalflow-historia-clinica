import re
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.enums import NUMEROS_DIENTE_VALIDOS
from app.schemas.common import AuditRead


def _dientes_validos(dientes: list[int]) -> list[int]:
    for numero in dientes:
        if numero not in NUMEROS_DIENTE_VALIDOS:
            raise ValueError(f"{numero} no es un numero de diente valido (notacion FDI)")
    return list(dict.fromkeys(dientes))


def _limpio(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v or None


# --- Remision (la crea la Dra.) -------------------------------------------------------------------------------

class RemisionCreate(BaseModel):
    especialista_id: UUID
    motivo: str
    dientes: list[int] = []
    toda_la_boca: bool = False

    @field_validator("motivo")
    @classmethod
    def _motivo(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Escriba el motivo de la remisión")
        return v

    @field_validator("dientes")
    @classmethod
    def _dientes(cls, v: list[int]) -> list[int]:
        return _dientes_validos(v)

    @model_validator(mode="after")
    def _area(self) -> "RemisionCreate":
        if not self.toda_la_boca and not self.dientes:
            raise ValueError("Indique los dientes de la remisión o marque «toda la boca»")
        return self


class RemisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paciente_id: UUID
    especialista_id: UUID
    especialista_nombre: str | None = None
    motivo: str
    dientes: list[int] = []   # se completa aparte (tabla remision_diente)
    toda_la_boca: bool
    creado_en: datetime
    retirada_en: datetime | None
    # Solo al remitir: si el aviso por correo al especialista salio (None en los listados).
    aviso_correo: bool | None = None


class EspecialistaRead(BaseModel):
    id: UUID
    nombre: str
    especialidad: str | None = None


# --- Atencion del especialista --------------------------------------------------------------------------------

class AtencionCreate(BaseModel):
    fecha: date
    procedimiento: str
    descripcion: str | None = None
    indicaciones: str | None = None
    dientes: list[int] = []

    @field_validator("procedimiento")
    @classmethod
    def _procedimiento(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Escriba el procedimiento realizado")
        if len(v) > 300:
            raise ValueError("El procedimiento no puede superar 300 caracteres")
        return v

    @field_validator("descripcion", "indicaciones")
    @classmethod
    def _texto(cls, v: str | None) -> str | None:
        return _limpio(v)

    @field_validator("dientes")
    @classmethod
    def _dientes(cls, v: list[int]) -> list[int]:
        return _dientes_validos(v)


class AtencionUpdate(BaseModel):
    """PATCH parcial (lo corrige la Dra.)."""

    fecha: date | None = None
    procedimiento: str | None = None
    descripcion: str | None = None
    indicaciones: str | None = None
    dientes: list[int] | None = None

    @field_validator("procedimiento")
    @classmethod
    def _procedimiento(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("Escriba el procedimiento realizado")
        return v

    @field_validator("descripcion", "indicaciones")
    @classmethod
    def _texto(cls, v: str | None) -> str | None:
        return _limpio(v)

    @field_validator("dientes")
    @classmethod
    def _dientes(cls, v: list[int] | None) -> list[int] | None:
        return None if v is None else _dientes_validos(v)


class AtencionRead(AuditRead):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paciente_id: UUID
    remision_id: UUID
    fecha: date
    procedimiento: str
    descripcion: str | None
    indicaciones: str | None
    dientes: list[int] = []   # se completa aparte (tabla atencion_diente)
    autor_nombre: str | None = None


# --- Clave de autorizacion (PIN de la Dra.) --------------------------------------------------------------------

_PATRON_PIN = re.compile(r"^\d{6}$")


class PinFijar(BaseModel):
    pin: str
    clave_actual: str

    @field_validator("pin")
    @classmethod
    def _pin(cls, v: str) -> str:
        if not _PATRON_PIN.match(v):
            raise ValueError("La clave de autorización son 6 dígitos")
        return v


class AccesoRead(BaseModel):
    usuario_nombre: str | None
    momento: datetime
    accion: str
