from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.common import AuditRead


class PacienteCreate(BaseModel):
    # numero_historia y creado_por ya NO se aceptan del cliente (19/09/2026):
    # numero_historia se genera server-side (ver services/correlativos.py),
    # creado_por se deriva del usuario autenticado (JWT), nunca del body.
    telefono_fijo: str | None = None
    movil: str
    nombre_completo: str
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


class PacienteRead(AuditRead):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    numero_historia: str
    telefono_fijo: str | None
    movil: str
    nombre_completo: str
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
