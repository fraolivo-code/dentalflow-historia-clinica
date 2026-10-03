# app/services/movil.py — Normalizacion del telefono movil (Etapa 6, A.1).
# Modulo aparte y sin dependencias de modelos: lo usan el modelo Paciente, la
# migracion 0016 y el servicio de vinculacion sin crear importaciones circulares.

import re


def normalizar_movil(texto: str | None) -> str | None:
    """Telefono venezolano -> '58' + 10 digitos, o None si no encaja (no cruza)."""
    if not texto:
        return None
    digitos = re.sub(r"\D", "", texto)
    if len(digitos) == 11 and digitos.startswith("0"):
        return "58" + digitos[1:]
    if len(digitos) == 10:
        return "58" + digitos
    if len(digitos) == 12 and digitos.startswith("58"):
        return digitos
    return None
