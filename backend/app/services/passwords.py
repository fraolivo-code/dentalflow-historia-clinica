# app/services/passwords.py — Reglas de contrasena y normalizacion de nombre y
# correo, en un solo lugar (especificacion usuarios-contrasenas, A.2).
# Aplican a crear, cambiar y restablecer.

import secrets

LARGO_MINIMO = 10
BYTES_MAXIMOS = 72  # limite de bcrypt: lo que pase de 72 bytes se ignora en silencio

# Sin caracteres ambiguos (0/O, 1/l/I): la temporal se lee y se dicta a mano.
_ALFABETO_TEMPORAL = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
LARGO_TEMPORAL = 14


def normalizar_nombre(nombre: str) -> str:
    return nombre.strip().lower()


def normalizar_email(email: str | None) -> str | None:
    if email is None:
        return None
    limpio = email.strip().lower()
    return limpio or None


def validar_password(
    clave: str, nombre: str | None = None, email: str | None = None
) -> str | None:
    """Devuelve el mensaje de error en espanol, o None si la clave cumple."""
    if len(clave) < LARGO_MINIMO:
        return f"La contraseña debe tener al menos {LARGO_MINIMO} caracteres."
    if len(clave.encode("utf-8")) > BYTES_MAXIMOS:
        return f"La contraseña es demasiado larga (máximo {BYTES_MAXIMOS} bytes)."
    comparable = clave.strip().lower()
    if nombre and comparable == normalizar_nombre(nombre):
        return "La contraseña no puede ser igual al nombre de usuario."
    if email and comparable == normalizar_email(email):
        return "La contraseña no puede ser igual al correo."
    return None


def generar_temporal() -> str:
    """Contrasena temporal aleatoria que cumple las reglas de validar_password."""
    return "".join(secrets.choice(_ALFABETO_TEMPORAL) for _ in range(LARGO_TEMPORAL))
