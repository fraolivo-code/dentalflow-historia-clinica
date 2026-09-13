# app/db.py — Conexion a la base de datos
#
# Postgres en Railway (mismo proveedor que fase1-whatsapp-bot). A diferencia de
# Fase 1, este modulo no soporta SQLite como fallback local: la Fase 2 nace
# directamente sobre Postgres, sin el problema del disco efimero.

import os

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")

# Railway entrega la URL con el esquema "postgresql://" (o "postgres://").
# SQLAlchemy en modo asincrono necesita el driver explicito en la URL.
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass
