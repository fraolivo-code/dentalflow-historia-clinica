# app/services/paciente_cambios.py — Que campos del paciente corrige cada rol y
# como se registra cada correccion (tabla paciente_cambio, sin retencion).

import uuid
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.common import ahora
from app.models.paciente import Paciente
from app.models.paciente_cambio import PacienteCambio

# Contacto: lo corrigen la asistente y el acceso total.
CAMPOS_CONTACTO = frozenset({"movil", "telefono_fijo", "email", "direccion"})

# Etiqueta legible de cada campo. Todo campo editable que NO este en
# CAMPOS_CONTACTO se trata como personal (solo acceso total), este o no aqui.
ETIQUETAS = {
    "numero_historia": "N.° de historia",
    "nombre_completo": "Nombre completo",
    "cedula": "Cédula",
    "fecha_nacimiento": "Fecha de nacimiento",
    "movil": "Teléfono móvil",
    "telefono_fijo": "Teléfono fijo",
    "email": "Correo electrónico",
    "direccion": "Dirección",
    "empresa_profesion_cargo": "Empresa / profesión / cargo",
    "referido_por": "Referido por",
    "fuma": "Fuma",
    "fuma_detalle": "Detalle de tabaquismo",
    "medicamentos_actuales": "Toma medicamentos",
    "medicamentos_actuales_detalle": "Detalle de medicamentos",
    "tratamiento_medico_actual": "Tratamiento médico actual",
    "fecha_registro": "Fecha de registro",
    "fecha_primera_consulta_real": "Paciente desde (primera consulta real)",
    "historia_origen": "Origen de la historia",
    "documento_historia_anterior": "Documento de historia anterior",
    "foto": "Foto",
    "seguro": "Seguro",
    "periodontograma_eliminado": "Periodontograma eliminado",
}


def etiqueta(campo: str) -> str:
    return ETIQUETAS.get(campo, campo)


def solo_contacto(campos) -> bool:
    return all(c in CAMPOS_CONTACTO for c in campos)


def a_texto(valor: Any) -> str | None:
    """Valor del campo como texto: fechas en ISO, booleanos como Si/No."""
    if valor is None:
        return None
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor)


def registrar(
    session: AsyncSession,
    paciente_id: uuid.UUID,
    actor_id: uuid.UUID,
    cambios: list[tuple[str, Any, Any]],
) -> None:
    """Agrega una fila por (campo, anterior, nuevo); la confirma quien llama."""
    momento = ahora()
    for campo, anterior, nuevo in cambios:
        session.add(
            PacienteCambio(
                paciente_id=paciente_id,
                fecha=momento,
                actor_id=actor_id,
                campo=campo,
                valor_anterior=a_texto(anterior),
                valor_nuevo=a_texto(nuevo),
            )
        )
