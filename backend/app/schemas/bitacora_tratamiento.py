from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.enums import (
    NUMEROS_DIENTE_VALIDOS,
    SuperficieDental,
    TipoHallazgo,
    validar_superficie,
)
from app.schemas.common import AuditRead


class BitacoraTratamientoCreate(BaseModel):
    # responsable y creado_por ya NO se aceptan del cliente (19/09/2026): este
    # endpoint esta bloqueado a dra, se derivan del usuario autenticado (JWT).
    visita_id: UUID | None = None
    fecha: date
    descripcion: str
    # Varios dientes por entrada (04/10/2026). `numero_diente` suelto se sigue
    # aceptando por compatibilidad: se suma a la lista (ver dientes_de_la_entrada).
    dientes: list[int] = []
    numero_diente: int | None = None
    tratamiento_id: UUID | None = None
    # Si hay dientes y vienen llenos, se crea automaticamente la fila correspondiente
    # en odontograma_hallazgo (seccion 7). Si numero_diente esta lleno pero
    # tipo_hallazgo no, no se crea nada ("se reviso el diente, sin hallazgo
    # nuevo que registrar").
    tipo_hallazgo: TipoHallazgo | None = None
    superficie: SuperficieDental | None = None

    @field_validator("numero_diente")
    @classmethod
    def _validar_numero_diente(cls, v: int | None) -> int | None:
        if v is not None and v not in NUMEROS_DIENTE_VALIDOS:
            raise ValueError(f"{v} no es un numero de diente valido (notacion FDI)")
        return v

    @field_validator("dientes")
    @classmethod
    def _validar_dientes(cls, v: list[int]) -> list[int]:
        for numero in v:
            if numero not in NUMEROS_DIENTE_VALIDOS:
                raise ValueError(f"{numero} no es un numero de diente valido (notacion FDI)")
        return v

    def dientes_de_la_entrada(self) -> list[int]:
        """`dientes` + `numero_diente` suelto, sin repetidos y en el orden recibido."""
        lista = list(self.dientes)
        if self.numero_diente is not None:
            lista.append(self.numero_diente)
        return list(dict.fromkeys(lista))

    @model_validator(mode="after")
    def _validar_superficie(self) -> "BitacoraTratamientoCreate":
        # Misma regla que OdontogramaHallazgoCreate, validada al recibir el
        # request: asi nunca se guarda la entrada con un hallazgo invalido.
        if self.tipo_hallazgo is not None:
            validar_superficie(self.tipo_hallazgo, self.superficie)
        return self


class BitacoraTratamientoRead(AuditRead):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paciente_id: UUID
    visita_id: UUID | None
    fecha: date
    responsable: UUID
    descripcion: str
    # Primer diente (compatibilidad); la lista completa va en `dientes`.
    numero_diente: int | None
    dientes: list[int]
    tratamiento_id: UUID | None
    tipo_hallazgo: TipoHallazgo | None
    superficie: SuperficieDental | None
