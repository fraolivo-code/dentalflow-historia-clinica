# app/services/vinculacion.py — Etapa 6: vinculacion Alma <-> historia clinica
# (solo lectura). Todo el cruce (telefonos y nombres) se hace aqui, en Python,
# para que el comportamiento sea identico en Postgres y en SQLite de tests.
# Especificacion: especificacion-tecnica-vinculacion-alma-fase2.md, parte A.

import re
import unicodedata
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consulta_vinculacion import ConsultaVinculacion
from app.models.paciente import Paciente
from app.services.movil import normalizar_movil

DIAS_RETENCION_CONSULTAS = 90
INTERVALO_PURGA = timedelta(hours=24)

# Momento (UTC) de la ultima purga lanzada por este proceso (mismo patron que
# Alma: vive en memoria, tras un redespliegue vuelve a purgar al primer uso).
_ultima_purga: datetime | None = None

# Palabras que se ignoran al principio de lo que escribe la persona
# ("soy Maria", "es para mi hijo Pedro"). Lista fija, ya normalizada.
PALABRAS_PREVIAS = frozenset(
    {
        "hola", "buenas", "buenos", "buen", "dia", "dias", "tarde", "tardes", "noche", "noches",
        "soy", "yo", "me", "llamo", "llama", "mi", "nombre", "es", "son", "se", "el", "la",
        "lo", "los", "las", "un", "una", "para", "por", "con", "de", "del", "a", "al",
        "hijo", "hija", "esposo", "esposa", "mama", "papa", "madre", "padre", "hermano",
        "hermana", "sobrino", "sobrina", "nieto", "nieta", "abuelo", "abuela", "tio", "tia",
        "paciente", "senor", "senora", "sr", "sra", "gusto", "quien", "habla", "cita",
        "seria", "esta", "estoy", "llamando", "escribiendo",
    }
)


def palabras_normalizadas(texto: str | None) -> list[str]:
    """Minusculas, sin tildes, sin signos, espacios simples -> lista de palabras."""
    if not texto:
        return []
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto.lower()) if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-z0-9\s]", " ", sin_tildes).split()


def extraer_nombre_y_apellido(texto: str | None) -> tuple[str | None, str | None]:
    """
    Quita las frases previas fijas y toma la primera palabra como nombre y,
    si hay mas, la siguiente como posible apellido.
    """
    palabras = palabras_normalizadas(texto)
    while palabras and palabras[0] in PALABRAS_PREVIAS:
        palabras.pop(0)
    if not palabras:
        return None, None
    return palabras[0], palabras[1] if len(palabras) > 1 else None


def evaluar_coincidencia(nombres_registrados: list[str], texto: str) -> dict:
    """
    Regla conservadora (ante la duda, no coincide). `nombres_registrados` son los
    nombre_completo de los pacientes con ese movil. Devuelve el dict de /verificar.

    El primer nombre es la primera palabra del registro. nombre_completo es un
    solo texto, asi que el "primer apellido" no se puede ubicar con certeza: el
    apellido dicho coincide si esta entre las demas palabras del registro.
    """
    nombre, apellido = extraer_nombre_y_apellido(texto)
    if nombre is None:
        return {"coincide": False}

    coinciden: list[str] = []
    for registrado in nombres_registrados:
        palabras = palabras_normalizadas(registrado)
        if not palabras or palabras[0] != nombre:
            continue
        if apellido is not None and apellido not in palabras[1:]:
            continue
        coinciden.append(registrado)

    if len(coinciden) == 1:
        return {"coincide": True, "nombre_saludo": coinciden[0].split()[0]}
    if len(coinciden) > 1 and apellido is None:
        return {"coincide": False, "pedir_apellido": True}
    return {"coincide": False}


async def pacientes_con_movil(session: AsyncSession, telefono: str | None) -> list[str]:
    """nombre_completo de los pacientes cuyo movil normalizado coincide con `telefono`."""
    movil = normalizar_movil(telefono)
    if movil is None:
        return []
    resultado = await session.execute(
        select(Paciente.nombre_completo).where(Paciente.movil_normalizado == movil)
    )
    return list(resultado.scalars().all())


async def registrar_consulta(
    session: AsyncSession, endpoint: str, telefono: str | None, resultado: str
) -> None:
    """Guarda la consulta (sin el nombre escrito por la persona) y purga si toca."""
    session.add(
        ConsultaVinculacion(
            endpoint=endpoint, movil_normalizado=normalizar_movil(telefono), resultado=resultado
        )
    )
    await session.commit()
    await purgar_si_corresponde(session)


async def purgar_consultas_antiguas(session: AsyncSession, ahora: datetime | None = None) -> int:
    referencia = ahora or datetime.now(timezone.utc)
    if referencia.tzinfo is None:
        referencia = referencia.replace(tzinfo=timezone.utc)
    limite = referencia - timedelta(days=DIAS_RETENCION_CONSULTAS)
    resultado = await session.execute(
        delete(ConsultaVinculacion).where(ConsultaVinculacion.fecha < limite)
    )
    await session.commit()
    return max(resultado.rowcount or 0, 0)


async def purgar_si_corresponde(
    session: AsyncSession, ahora: datetime | None = None
) -> int | None:
    """Purga como maximo una vez cada 24 h. Nunca levanta excepciones."""
    global _ultima_purga
    try:
        referencia = ahora or datetime.now(timezone.utc)
        if _ultima_purga is not None and referencia - _ultima_purga < INTERVALO_PURGA:
            return None
        _ultima_purga = referencia  # antes de purgar: un fallo no se reintenta en cada consulta
        return await purgar_consultas_antiguas(session, referencia)
    except Exception:  # noqa: BLE001
        return None
