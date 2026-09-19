from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.enums import NUMEROS_DIENTE_VALIDOS, SuperficieDental, TipoHallazgo
from app.schemas.common import AuditRead


class BitacoraTratamientoCreate(BaseModel):
    visita_id: UUID | None = None
    fecha: date
    responsable: UUID
    descripcion: str
    numero_diente: int | None = None
    tratamiento_id: UUID | None = None
    # Si ambos vienen llenos, se crea automaticamente la fila correspondiente
    # en odontograma_hallazgo (seccion 7). Si numero_diente esta lleno pero
    # tipo_hallazgo no, no se crea nada ("se reviso el diente, sin hallazgo
    # nuevo que registrar").
    tipo_hallazgo: TipoHallazgo | None = None
    superficie: SuperficieDental | None = None
    creado_por: UUID

    @field_validator("numero_diente")
    @classmethod
    def _validar_numero_diente(cls, v: int | None) -> int | None:
        if v is not None and v not in NUMEROS_DIENTE_VALIDOS:
            raise ValueError(f"{v} no es un numero de diente valido (notacion FDI)")
        return v


class BitacoraTratamientoRead(AuditRead):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paciente_id: UUID
    visita_id: UUID | None
    fecha: date
    responsable: UUID
    descripcion: str
    numero_diente: int | None
    tratamiento_id: UUID | None
    tipo_hallazgo: TipoHallazgo | None
    superficie: SuperficieDental | None
