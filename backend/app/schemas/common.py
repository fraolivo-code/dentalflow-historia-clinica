# app/schemas/common.py — Campos de auditoria compartidos (seccion 0.1),
# expuestos en toda respuesta de una tabla clinica.

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

from app.enums import NUMEROS_DIENTE_VALIDOS


class AuditRead(BaseModel):
    creado_en: datetime
    creado_por: UUID
    actualizado_en: datetime | None = None
    actualizado_por: UUID | None = None


class NumeroDienteValidoMixin(BaseModel):
    """Valida numero_diente contra la notacion FDI antes de tocar la base."""

    # check_fields=False: numero_diente lo declara la subclase, no este mixin.
    @field_validator("numero_diente", check_fields=False)
    @classmethod
    def _validar_numero_diente(cls, v: int) -> int:
        if v not in NUMEROS_DIENTE_VALIDOS:
            raise ValueError(f"{v} no es un numero de diente valido (notacion FDI)")
        return v
