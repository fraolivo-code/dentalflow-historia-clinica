# app/services/correlativos.py — Numeracion de historias, server-side.
#
# El numero no lo calcula el cliente (evita colisiones por condicion de
# carrera): usa la secuencia nativa de Postgres `paciente_numero_historia_seq`
# (migracion 0005), atomica por diseno. El punto de partida y el ancho se fijan
# desde la aplicacion (configuracion_consultorio.numero_ancho, setval).
#
# En SQLite (tests) no hay secuencias: se simula con un contador por motor.
# Los numeros se comparan como ENTEROS, no como texto, para que "0457" y
# "000457" (si cambia el ancho) cuenten como la misma historia.

import re
from weakref import WeakKeyDictionary

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configuracion_consultorio import ID_UNICO, ConfiguracionConsultorio
from app.models.paciente import Paciente

ANCHO_POR_DEFECTO = 4
MAX_DIGITOS = 18  # cabe en un bigint (setval) y de sobra en String(50)
TOPE_INTENTOS = 1000

_SOLO_DIGITOS = re.compile(r"[0-9]+")
_SECUENCIA = "paciente_numero_historia_seq"
_simuladas: "WeakKeyDictionary[object, int]" = WeakKeyDictionary()


class NumeroInvalido(ValueError):
    pass


class NumeracionAgotada(RuntimeError):
    pass


def _es_sqlite(session: AsyncSession) -> bool:
    return session.get_bind().dialect.name == "sqlite"


def _contador(session: AsyncSession) -> object:
    return session.get_bind()


async def ancho_configurado(session: AsyncSession) -> int:
    config = await session.get(ConfiguracionConsultorio, ID_UNICO)
    return config.numero_ancho if config is not None else ANCHO_POR_DEFECTO


def formatear(numero: int, ancho: int) -> str:
    return str(numero).zfill(ancho)


def normalizar_manual(texto: str, ancho: int) -> str:
    """Solo digitos (tras recortar); sin ceros de mas; ancho minimo `ancho`."""
    limpio = (texto or "").strip()
    if not _SOLO_DIGITOS.fullmatch(limpio):
        raise NumeroInvalido("El número de historia debe tener solo dígitos.")
    if len(limpio.lstrip("0")) > MAX_DIGITOS:
        raise NumeroInvalido(f"El número de historia no puede superar {MAX_DIGITOS} dígitos.")
    valor = int(limpio)
    if valor < 1:
        raise NumeroInvalido("El número de historia debe ser mayor que cero.")
    return formatear(valor, ancho)


async def numeros_en_uso(session: AsyncSession) -> set[int]:
    """Historias existentes que son solo digitos (otras, p. ej. 'H-1', se ignoran)."""
    filas = await session.execute(select(Paciente.numero_historia))
    return {
        int(n) for (n,) in filas if _SOLO_DIGITOS.fullmatch(n or "") and len(n) <= MAX_DIGITOS
    }


async def mayor_existente(session: AsyncSession) -> int:
    return max(await numeros_en_uso(session), default=0)


async def siguiente_sin_consumir(session: AsyncSession) -> int:
    """El proximo valor que daria la secuencia, sin consumirlo."""
    if _es_sqlite(session):
        return _simuladas.get(_contador(session), 1)
    fila = (await session.execute(text(f"SELECT last_value, is_called FROM {_SECUENCIA}"))).one()
    return fila.last_value + 1 if fila.is_called else fila.last_value


async def fijar_siguiente(session: AsyncSession, valor: int) -> None:
    """Hace que el proximo numero automatico sea exactamente `valor`."""
    if _es_sqlite(session):
        _simuladas[_contador(session)] = valor
        return
    await session.execute(text("SELECT setval(:seq, :v, false)"), {"seq": _SECUENCIA, "v": valor})


async def _consumir(session: AsyncSession) -> int:
    if _es_sqlite(session):
        valor = _simuladas.get(_contador(session), 1)
        _simuladas[_contador(session)] = valor + 1
        return valor
    return (await session.execute(text(f"SELECT nextval('{_SECUENCIA}')"))).scalar_one()


async def generar_numero_historia(session: AsyncSession) -> str:
    """Siguiente numero libre: salta los ya usados (historias viejas cargadas a mano)."""
    ancho = await ancho_configurado(session)
    usados = await numeros_en_uso(session)
    for _ in range(TOPE_INTENTOS):
        candidato = await _consumir(session)
        if candidato not in usados:
            return formatear(candidato, ancho)
    raise NumeracionAgotada(
        "No se encontró un número de historia libre; revise la numeración en Configuración."
    )
