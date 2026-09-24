from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.enums import (
    CondicionIndividualPuente,
    EstadoGeneralPuente,
    OrigenHallazgo,
    RolDientePuente,
    SuperficieDental,
    TipoHallazgo,
    TipoLesionApical,
    validar_superficie,
)
from app.schemas.common import AuditRead, NumeroDienteValidoMixin


class DienteAnatomiaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    numero_diente: int
    num_raices: int
    nombres_raices: list[str]


class OdontogramaHallazgoCreate(NumeroDienteValidoMixin):
    numero_diente: int
    visita_id: UUID | None = None
    tipo_hallazgo: TipoHallazgo
    superficie: SuperficieDental | None = None
    fecha: date
    notas: str | None = None
    # creado_por ya NO se acepta del cliente (19/09/2026) — se deriva del
    # usuario autenticado (JWT), este endpoint esta bloqueado a dra.
    # Etapa 3: vinculo con el tratamiento multisesion del que este hallazgo
    # forma parte. None cuando se crea directo desde la pantalla del
    # odontograma sin pasar por un tratamiento.
    tratamiento_id: UUID | None = None

    @model_validator(mode="after")
    def _validar_superficie(self) -> "OdontogramaHallazgoCreate":
        validar_superficie(self.tipo_hallazgo, self.superficie)
        return self


class OdontogramaHallazgoResolver(BaseModel):
    """Cierre manual de un hallazgo (PATCH .../resolver, 23/09/2026)."""

    fecha: date


class OdontogramaHallazgoRead(AuditRead):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paciente_id: UUID
    numero_diente: int
    visita_id: UUID | None
    tipo_hallazgo: TipoHallazgo
    superficie: SuperficieDental | None
    fecha: date
    resuelto: bool
    resuelto_fecha: date | None
    resuelto_por_hallazgo_id: UUID | None
    origen: OrigenHallazgo
    tratamiento_id: UUID | None
    notas: str | None


class OdontogramaLesionApicalCreate(NumeroDienteValidoMixin):
    numero_diente: int
    visita_id: UUID | None = None
    # Debe coincidir con un nombre de raiz de diente_anatomia para ese diente,
    # o con "Periimplantitis" si el diente tiene "implante" activo — validado
    # en app/services/odontograma_logic.py, no aqui (requiere consultar la DB).
    raiz: str
    fecha: date


class OdontogramaLesionApicalRead(AuditRead):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paciente_id: UUID
    numero_diente: int
    visita_id: UUID | None
    raiz: str
    tipo: TipoLesionApical
    fecha: date
    resuelto: bool
    resuelto_fecha: date | None
    resuelto_por_hallazgo_id: UUID | None


class OdontogramaLesionApicalResolver(BaseModel):
    """Cierre manual de una lesion apical (PATCH .../resolver, 23/09/2026)."""

    fecha: date


class PuenteFijoDienteCreate(NumeroDienteValidoMixin):
    numero_diente: int
    rol: RolDientePuente
    # Enum angosto (8 valores), no TipoHallazgo completo (26): el subconjunto
    # se restringe ya en el schema, no solo en el servicio o el CHECK de la DB.
    condicion_individual: CondicionIndividualPuente


class PuenteFijoCreate(BaseModel):
    visita_id: UUID | None = None
    estado_general: EstadoGeneralPuente
    fecha: date
    dientes: list[PuenteFijoDienteCreate]

    @field_validator("dientes")
    @classmethod
    def _minimo_dos_dientes(cls, v: list[PuenteFijoDienteCreate]) -> list[PuenteFijoDienteCreate]:
        if len(v) < 2:
            raise ValueError("Un puente fijo necesita al menos 2 dientes")
        return v


class PuenteFijoDienteRead(AuditRead):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    puente_id: UUID
    numero_diente: int
    rol: RolDientePuente
    condicion_individual: CondicionIndividualPuente


class PuenteFijoRead(AuditRead):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paciente_id: UUID
    visita_id: UUID | None
    estado_general: EstadoGeneralPuente
    fecha: date
    # En orden anatomico real (seccion 3.2), no numerico ascendente — se
    # ordena en el router antes de construir esta respuesta.
    dientes: list[PuenteFijoDienteRead]
