from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.enums import (
    RANGO_MARGEN_GINGIVAL,
    RANGO_PROFUNDIDAD_SONDAJE,
    RANGO_RECESION_MM,
    FurcacionGlickman,
    RecesionCairo,
    SitioPeriodontal,
    admite_furcacion,
)
from app.schemas.common import AuditRead, NumeroDienteValidoMixin


def _en_rango(campo: str, valor: int | None, rango: tuple[int, int]) -> int | None:
    """Rangos de red de seguridad (24/09/2026); None pasa (lo usan los PATCH)."""
    minimo, maximo = rango
    if valor is not None and not minimo <= valor <= maximo:
        raise ValueError(f"{campo} debe estar entre {minimo} y {maximo} mm")
    return valor


def _validar_movilidad(v: int | None) -> int | None:
    if v is not None and not 0 <= v <= 3:
        raise ValueError("movilidad debe estar entre 0 y 3 (escala Miller)")
    return v


def validar_furcacion(numero_diente: int, furcacion: FurcacionGlickman | None) -> None:
    if furcacion is not None and not admite_furcacion(numero_diente):
        raise ValueError(
            f"El diente {numero_diente} no admite furcacion: solo molares y los premolares 14/24"
        )


class _MedidasSitio(BaseModel):
    """Validacion de rangos compartida por el alta y la correccion de un sitio."""

    @field_validator("margen_gingival", check_fields=False)
    @classmethod
    def _margen(cls, v):
        return _en_rango("margen_gingival", v, RANGO_MARGEN_GINGIVAL)

    @field_validator("profundidad_sondaje", check_fields=False)
    @classmethod
    def _sondaje(cls, v):
        return _en_rango("profundidad_sondaje", v, RANGO_PROFUNDIDAD_SONDAJE)

    @field_validator("recesion_mm", check_fields=False)
    @classmethod
    def _recesion(cls, v):
        return _en_rango("recesion_mm", v, RANGO_RECESION_MM)


class PeriodontogramaRegistroCreate(NumeroDienteValidoMixin, _MedidasSitio):
    numero_diente: int
    sitio: SitioPeriodontal
    margen_gingival: int
    profundidad_sondaje: int
    # nivel_insercion ya NO se acepta del cliente (24/09/2026): lo calcula el
    # backend. Si llega en el body se ignora (extra="ignore" de Pydantic).
    recesion_mm: int = 0
    recesion_cairo: RecesionCairo | None = None
    sangrado: bool = False
    placa: bool = False


class PeriodontogramaRegistroRead(AuditRead):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paciente_id: UUID
    visita_id: UUID
    numero_diente: int
    sitio: SitioPeriodontal
    margen_gingival: int
    profundidad_sondaje: int
    nivel_insercion: int
    recesion_mm: int
    recesion_cairo: RecesionCairo | None
    sangrado: bool
    placa: bool


class PeriodontogramaRegistroUpdate(_MedidasSitio):
    """
    Correccion puntual de un sitio (PATCH, 24/09/2026): solo los campos
    enviados. recesion_cairo acepta null (borra la clasificacion); el resto
    no. nivel_insercion se recalcula, no se acepta.
    """

    margen_gingival: int | None = None
    profundidad_sondaje: int | None = None
    recesion_mm: int | None = None
    recesion_cairo: RecesionCairo | None = None
    sangrado: bool | None = None
    placa: bool | None = None

    @model_validator(mode="after")
    def _validar(self) -> "PeriodontogramaRegistroUpdate":
        if not self.model_fields_set:
            raise ValueError("No hay ningun campo para corregir")
        nulos = sorted(
            c for c in self.model_fields_set if c != "recesion_cairo" and getattr(self, c) is None
        )
        if nulos:
            raise ValueError(f"No pueden quedar vacios: {', '.join(nulos)}")
        return self


class PeriodontogramaDienteResumenCreate(NumeroDienteValidoMixin):
    numero_diente: int
    movilidad: int
    furcacion: FurcacionGlickman | None = None

    @field_validator("movilidad")
    @classmethod
    def _movilidad_en_rango(cls, v: int) -> int:
        return _validar_movilidad(v)

    @model_validator(mode="after")
    def _furcacion(self) -> "PeriodontogramaDienteResumenCreate":
        validar_furcacion(self.numero_diente, self.furcacion)
        return self


class PeriodontogramaDienteResumenRead(AuditRead):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paciente_id: UUID
    visita_id: UUID
    numero_diente: int
    movilidad: int
    furcacion: FurcacionGlickman | None


class PeriodontogramaDienteResumenUpdate(BaseModel):
    """Correccion puntual de un diente (PATCH). furcacion acepta null; movilidad no."""

    movilidad: int | None = None
    furcacion: FurcacionGlickman | None = None

    @field_validator("movilidad")
    @classmethod
    def _movilidad_en_rango(cls, v: int | None) -> int | None:
        return _validar_movilidad(v)

    @model_validator(mode="after")
    def _validar(self) -> "PeriodontogramaDienteResumenUpdate":
        if not self.model_fields_set:
            raise ValueError("No hay ningun campo para corregir")
        if "movilidad" in self.model_fields_set and self.movilidad is None:
            raise ValueError("No pueden quedar vacios: movilidad")
        return self


class PeriodontogramaVisitaCreate(BaseModel):
    """
    Carga completa de un levantamiento periodontal para una visita.
    Error duro (422) si queda a medio cargar (24/09/2026): cada diente con
    registros trae sus 6 sitios, sin repetir, y exactamente un resumen; no hay
    resumen de un diente sin registros. Se informan TODOS los problemas juntos.
    """

    registros: list[PeriodontogramaRegistroCreate]
    resumenes: list[PeriodontogramaDienteResumenCreate]

    @model_validator(mode="after")
    def _completo(self) -> "PeriodontogramaVisitaCreate":
        if not self.registros:
            raise ValueError("El periodontograma no tiene ningun registro")
        todos = list(SitioPeriodontal)
        problemas: list[str] = []

        sitios_por_diente: dict[int, list[SitioPeriodontal]] = {}
        for r in self.registros:
            sitios_por_diente.setdefault(r.numero_diente, []).append(r.sitio)
        for diente in sorted(sitios_por_diente):
            sitios = sitios_por_diente[diente]
            repetidos = sorted({s.value for s in sitios if sitios.count(s) > 1})
            if repetidos:
                problemas.append(f"diente {diente}: sitios repetidos ({', '.join(repetidos)})")
            faltan = [s.value for s in todos if s not in sitios]
            if faltan:
                problemas.append(f"diente {diente}: faltan sitios ({', '.join(faltan)})")

        dientes_resumen = [r.numero_diente for r in self.resumenes]
        for diente in sorted({d for d in dientes_resumen if dientes_resumen.count(d) > 1}):
            problemas.append(f"diente {diente}: resumen repetido")
        for diente in sorted(set(dientes_resumen) - set(sitios_por_diente)):
            problemas.append(f"diente {diente}: tiene resumen pero ningun registro por sitio")
        for diente in sorted(set(sitios_por_diente) - set(dientes_resumen)):
            problemas.append(f"diente {diente}: falta el resumen (movilidad/furcacion)")

        if problemas:
            raise ValueError("Periodontograma incompleto o inconsistente: " + "; ".join(problemas))
        return self


class PeriodontogramaVisitaRead(BaseModel):
    registros: list[PeriodontogramaRegistroRead]
    resumenes: list[PeriodontogramaDienteResumenRead]


class PeriodontogramaHistorialItem(BaseModel):
    """Una visita del paciente con periodontograma cargado (GET .../periodontograma/visitas)."""

    visita_id: UUID
    fecha: date
    dientes: int
    cargado_en: datetime
