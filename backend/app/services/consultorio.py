# app/services/consultorio.py — Datos del consultorio para el membrete de los
# impresos en blanco (formulario de ingreso y odontograma en blanco, 04/10/2026).
# Salen de la configuracion de la portada (nombre y frase), NO del profesional
# vinculado al usuario: asi los puede imprimir cualquier usuario autenticado.

import os

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configuracion_consultorio import ID_UNICO, ConfiguracionConsultorio


def nombre_por_defecto() -> str:
    return os.getenv("NOMBRE_PRODUCTO", "DentalFlow").strip() or "DentalFlow"


async def membrete_consultorio(session: AsyncSession) -> dict:
    """{"nombre", "detalle"}: nombre y frase configurados; sin ellos, NOMBRE_PRODUCTO."""
    config = await session.get(ConfiguracionConsultorio, ID_UNICO)
    return {
        "nombre": (config.nombre if config else None) or nombre_por_defecto(),
        "detalle": config.frase if config else None,
    }
