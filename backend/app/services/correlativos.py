# app/services/correlativos.py — Generacion de correlativos server-side.
#
# numero_historia no depende de que el cliente lo calcule (evita colisiones
# por condicion de carrera): usa la secuencia nativa de Postgres
# `paciente_numero_historia_seq` (migracion 0005), atomica por diseno.

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def generar_numero_historia(session: AsyncSession) -> str:
    resultado = await session.execute(text("SELECT nextval('paciente_numero_historia_seq')"))
    siguiente = resultado.scalar_one()
    return str(siguiente).zfill(4)
