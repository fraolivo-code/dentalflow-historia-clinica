from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.schemas.common import AuditRead


class PacienteCreate(BaseModel):
    # numero_historia y creado_por ya NO se aceptan del cliente (19/09/2026):
    # numero_historia se genera server-side (ver services/correlativos.py),
    # creado_por se deriva del usuario autenticado (JWT), nunca del body.
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
    se edita (lo genera el sistema). Los opcionales aceptan null (borran el
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

    @field_validator("nombre_completo", "movil", "referido_por", "cedula")
    @classmethod
    def _sin_espacios_sobrantes(cls, v: str | None) -> str | None:
        # Una cedula en blanco equivale a borrarla; un obligatorio en blanco
        # queda como "" y lo rechaza _validar.
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
