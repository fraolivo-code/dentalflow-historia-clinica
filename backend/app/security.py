# app/security.py — Hash de contrasenas (bcrypt) y JWT (Etapa 3, login).
#
# JWT_EXPIRA_HORAS = 8: una jornada laboral (confirmado con la Dra.).

import os
from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
import jwt

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
JWT_ALGORITHM = "HS256"
JWT_EXPIRA_HORAS = 8

if not JWT_SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY no esta configurada (falta en .env / variables de entorno)."
    )


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def crear_access_token(usuario_id: UUID, rol: str) -> str:
    ahora = datetime.now(timezone.utc)
    payload = {
        "sub": str(usuario_id),
        "rol": rol,
        "iat": ahora,
        "exp": ahora + timedelta(hours=JWT_EXPIRA_HORAS),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decodificar_access_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
