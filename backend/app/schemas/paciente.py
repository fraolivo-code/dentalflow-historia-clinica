import re
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.schemas.common import AuditRead


def _limpiar_seguro(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    if len(v) > 120:
        raise ValueError("El seguro no puede superar 120 caracteres")
    return v or None


def _limpiar_ultima_visita(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    if len(v) > 120:
        raise ValueError("La última visita al odontólogo no puede superar 120 caracteres")
    return v or None


def _normalizar_cedula(v: str | None) -> str | None:
    """'v-012345' -> 'V-12345'; vacio -> None. Solo V o E y hasta 10 digitos."""
    if v is None:
        return None
    v = v.strip().upper()
    if not v:
        return None
    m = re.fullmatch(r"([VE])-?(\d{1,10})", v)
    if m is None or int(m[2]) == 0:
        raise ValueError("La cédula debe ser V o E seguida de solo números (ej. V-12345678)")
    return f"{m[1]}-{int(m[2])}"


class PacienteCreate(BaseModel):
    # creado_por no se acepta del cliente: se deriva del usuario autenticado (JWT).
    # numero_historia es opcional (04/10/2026): vacio -> lo asigna el sistema
    # (services/correlativos.py); con valor -> historia vieja, solo cuentas con
    # acceso total (lo valida el router).
    numero_historia: str | None = None
    telefono_fijo: str | None = None
    movil: str
    nombre_completo: str
    cedula: str | None = None
    fecha_nacimiento: date | None = None
    direccion: str | None = None
    email: str | None = None
    empresa_profesion_cargo: str | None = None
    referido_por: str = "N/A"
    fuma: bool = False
    fuma_detalle: str | None = None
    medicamentos_actuales: bool = False
    medicamentos_actuales_detalle: str | None = None
    tratamiento_medico_actual: str | None = None
    fecha_registro: date
    # Etapa 3, seccion 1.
    fecha_primera_consulta_real: date | None = None
    historia_origen: str | None = None
    # Solo la ruta/clave (aun no hay logica de storage real conectada — ver
    # especificacion seccion 1.1, pendiente de credenciales de Cloudflare R2).
    documento_historia_anterior: str | None = None
    foto: str | None = None
    seguro: str | None = None
    ultima_visita_odontologo: str | None = None

    @field_validator("ultima_visita_odontologo")
    @classmethod
    def _ultima_visita_limpia(cls, v: str | None) -> str | None:
        return _limpiar_ultima_visita(v)

    @field_validator("cedula")
    @classmethod
    def _cedula_normalizada(cls, v: str | None) -> str | None:
        return _normalizar_cedula(v)

    @field_validator("numero_historia")
    @classmethod
    def _numero_vacio_es_nulo(cls, v: str | None) -> str | None:
        return (v or "").strip() or None

    @field_validator("seguro")
    @classmethod
    def _seguro_limpio(cls, v: str | None) -> str | None:
        return _limpiar_seguro(v)


# Columnas NOT NULL de paciente: en un PATCH pueden cambiar, pero no borrarse.
CAMPOS_OBLIGATORIOS = (
    "movil",
    "nombre_completo",
    "referido_por",
    "fuma",
    "medicamentos_actuales",
    "fecha_registro",
)


class PacienteUpdate(BaseModel):
    """
    Correccion de los datos de alta (PATCH /pacientes/{id}, 25/09/2026) —
    solo dra. Mismos campos que PacienteCreate, todos opcionales:
    actualizacion parcial con exclude_unset en el router. numero_historia no
    se edita (queda fijo desde el alta). Los opcionales aceptan null (borran el
    dato); los obligatorios no.
    """

    telefono_fijo: str | None = None
    movil: str | None = None
    nombre_completo: str | None = None
    cedula: str | None = None
    fecha_nacimiento: date | None = None
    direccion: str | None = None
    email: str | None = None
    empresa_profesion_cargo: str | None = None
    referido_por: str | None = None
    fuma: bool | None = None
    fuma_detalle: str | None = None
    medicamentos_actuales: bool | None = None
    medicamentos_actuales_detalle: str | None = None
    tratamiento_medico_actual: str | None = None
    fecha_registro: date | None = None
    fecha_primera_consulta_real: date | None = None
    historia_origen: str | None = None
    documento_historia_anterior: str | None = None
    foto: str | None = None
    seguro: str | None = None
    ultima_visita_odontologo: str | None = None

    @field_validator("seguro")
    @classmethod
    def _seguro_limpio(cls, v: str | None) -> str | None:
        return _limpiar_seguro(v)

    @field_validator("ultima_visita_odontologo")
    @classmethod
    def _ultima_visita_limpia(cls, v: str | None) -> str | None:
        return _limpiar_ultima_visita(v)

    @field_validator("cedula")
    @classmethod
    def _cedula_normalizada(cls, v: str | None) -> str | None:
        return _normalizar_cedula(v)

    @field_validator("nombre_completo", "movil", "referido_por")
    @classmethod
    def _sin_espacios_sobrantes(cls, v: str | None) -> str | None:
        # Un obligatorio en blanco queda como None y lo rechaza _validar.
        if v is None:
            return None
        v = v.strip()
        return v or None

    @model_validator(mode="after")
    def _validar(self) -> "PacienteUpdate":
        if not self.model_fields_set:
            raise ValueError("No hay ningun campo para corregir")
        vacios = sorted(
            c for c in CAMPOS_OBLIGATORIOS if c in self.model_fields_set and getattr(self, c) is None
        )
        if vacios:
            raise ValueError(f"No pueden quedar vacios: {', '.join(vacios)}")
        return self


class PacienteRead(AuditRead):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    numero_historia: str
    telefono_fijo: str | None
    movil: str
    nombre_completo: str
    cedula: str | None
    fecha_nacimiento: date | None
    direccion: str | None
    email: str | None
    empresa_profesion_cargo: str | None
    referido_por: str
    fuma: bool
    fuma_detalle: str | None
    medicamentos_actuales: bool
    medicamentos_actuales_detalle: str | None
    tratamiento_medico_actual: str | None
    fecha_registro: date
    fecha_primera_consulta_real: date | None
    historia_origen: str | None
    documento_historia_anterior: str | None
    foto: str | None
    seguro: str | None
    ultima_visita_odontologo: str | None
    paciente_desde: int


class NumeroHistoriaCorreccion(BaseModel):
    numero_nuevo: str
    confirmo: bool = False


class PacienteCambioRead(BaseModel):
    id: UUID
    fecha: datetime
    # Nombre de quien hizo el cambio (no su id).
    actor_nombre: str | None
    campo: str
    etiqueta: str
    valor_anterior: str | None
    valor_nuevo: str | None
