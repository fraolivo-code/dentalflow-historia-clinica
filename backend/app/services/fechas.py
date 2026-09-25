# app/services/fechas.py — "Hoy" en Venezuela. El contenedor corre en UTC y
# Venezuela no tiene horario de verano desde 2016: UTC-4 fijo.

from datetime import date, datetime, timedelta, timezone

HORA_VENEZUELA = timezone(timedelta(hours=-4))


def hoy_venezuela() -> date:
    return datetime.now(HORA_VENEZUELA).date()
