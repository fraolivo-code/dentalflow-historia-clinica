from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.enums import (
    NUMEROS_DIENTE_VALIDOS,
    CondicionIndividualPuente,
    EstadoGeneralPuente,
    OrigenHallazgo,
    RolDientePuente,
    SuperficieDental,
    TipoHallazgo,
    TipoLesionApical,
    TratamientoRealizado,
    validar_superficie,
)
from app.schemas.common import AuditRead, NumeroDientePermanenteMixin, NumeroDienteValidoMixin


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


class HallazgosLoteCreate(BaseModel):
    """Un mismo hallazgo en varios dientes de una vez (15/10/2026): la primera cita de una evaluacion."""

    dientes: list[int]
    tipo_hallazgo: TipoHallazgo
    # Una por cada superficie (caries, obturaciones, diastema las exigen); vacio si el tipo no usa superficie.
    superficies: list[SuperficieDental] = []
    fecha: date
    visita_id: UUID | None = None

    @model_validator(mode="after")
    def _validar(self) -> "HallazgosLoteCreate":
        if not self.dientes:
            raise ValueError("Elija al menos un diente")
        if len(set(self.dientes)) != len(self.dientes):
            raise ValueError("Hay dientes repetidos")
        for numero in self.dientes:
            if numero not in NUMEROS_DIENTE_VALIDOS:
                raise ValueError(f"{numero} no es un numero de diente valido (notacion FDI)")
        for superficie in self.superficies or [None]:
            validar_superficie(self.tipo_hallazgo, superficie)
        return self


class TratamientoRealizadoCreate(NumeroDienteValidoMixin):
    """Accion «Tratamiento realizado» (15/10/2026): cierra los hallazgos «antes» y abre los «despues»."""

    numero_diente: int
    tratamiento: TratamientoRealizado
    fecha: date
    superficies: list[SuperficieDental] = []
    # Solo para la carilla: carilla_ok, corona_ok o ausente (lo elige la Dra. al terminar).
    resultado: TipoHallazgo | None = None
    # None = el cierre propuesto por defecto; una lista (aunque vacia) = exactamente esos.
    cierra_ids: list[UUID] | None = None
    descripcion: str | None = None
    visita_id: UUID | None = None
    tratamiento_id: UUID | None = None


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


class TratamientoRealizadoItem(NumeroDienteValidoMixin):
    numero_diente: int
    tratamiento: TratamientoRealizado
    superficies: list[SuperficieDental] = []
    resultado: TipoHallazgo | None = None
    cierra_ids: list[UUID] | None = None
    descripcion: str | None = None


class TratamientoRealizadoLoteCreate(BaseModel):
    """Varios «Tratamiento realizado» de una misma fecha en una sola transaccion (15/10/2026)."""

    fecha: date
    visita_id: UUID | None = None
    items: list[TratamientoRealizadoItem]

    @model_validator(mode="after")
    def _validar(self) -> "TratamientoRealizadoLoteCreate":
        if not self.items:
            raise ValueError("Elija al menos un tratamiento")
        return self


class TratamientoRealizadoRead(BaseModel):
    cerrados: list[OdontogramaHallazgoRead]
    abiertos: list[OdontogramaHallazgoRead]
    bitacora_id: UUID


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


class PuenteFijoDienteCreate(NumeroDientePermanenteMixin):
    numero_diente: int
    rol: RolDientePuente
    # Enum angosto (8 valores), no TipoHallazgo completo (26): el subconjunto
    # se restringe ya en el schema, no solo en el servicio o el CHECK de la DB.
    condicion_individual: CondicionIndividualPuente

    @model_validator(mode="after")
    def _validar_rol_condicion(self) -> "PuenteFijoDienteCreate":
        """
        Capa 1 de la regla rol <-> condicion (24/09/2026): un pontico es un
        diente ausente por definicion, y un pilar nunca lo es. Capa 3: el
        CHECK ck_puente_fijo_diente_rol_condicion (migracion 0009).
        """
        es_ausente = self.condicion_individual == CondicionIndividualPuente.ausente
        if self.rol == RolDientePuente.pontico and not es_ausente:
            raise ValueError(
                f"El diente {self.numero_diente} es pontico: su condicion debe ser 'ausente'"
            )
        if self.rol == RolDientePuente.pilar and es_ausente:
            raise ValueError(
                f"El diente {self.numero_diente} es pilar: su condicion no puede ser 'ausente'"
            )
        return self


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


class PuenteFijoResolver(BaseModel):
    """Cierre de un puente (PATCH .../puentes/{id}/resolver, 24/09/2026)."""

    fecha: date


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
    resuelto: bool
    resuelto_fecha: date | None
    # En orden anatomico real (seccion 3.2), no numerico ascendente — se
    # ordena en el router antes de construir esta respuesta.
    dientes: list[PuenteFijoDienteRead]
