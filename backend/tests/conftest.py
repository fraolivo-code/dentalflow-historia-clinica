# Tests de la API (Etapa 6): sin red y sin Postgres. Las variables de entorno
# se fijan ANTES de importar la app (app.db y app.security las leen al importar).

import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ.setdefault("JWT_SECRET_KEY", "clave-solo-para-tests")

import sys  # noqa: E402
import types  # noqa: E402
import uuid  # noqa: E402
from datetime import date  # noqa: E402

# WeasyPrint necesita Pango/GTK del sistema (en Docker estan; en Windows suele
# faltar). Estos tests no generan PDFs: si no carga, se usa un sustituto vacio.
try:
    import weasyprint  # noqa: F401
except OSError:
    _stub = types.ModuleType("weasyprint")
    _stub.HTML = object
    _stub.CSS = object
    _stub.__path__ = []
    _fonts = types.ModuleType("weasyprint.text.fonts")
    _fonts.FontConfiguration = object
    sys.modules["weasyprint"] = _stub
    sys.modules["weasyprint.text"] = types.ModuleType("weasyprint.text")
    sys.modules["weasyprint.text.fonts"] = _fonts

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db import Base  # noqa: E402
from app.deps import get_session  # noqa: E402
from app.enums import RolUsuario  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ConsultaVinculacion, Paciente, Usuario  # noqa: E402
from app.services import vinculacion as servicio  # noqa: E402

CLAVE = "k" * 40


@pytest_asyncio.fixture
async def session_factory():
    # Solo las tablas que se usan: diente_anatomia usa ARRAY (solo Postgres).
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[Usuario.__table__, Paciente.__table__, ConsultaVinculacion.__table__],
        )
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(session_factory, monkeypatch):
    async def _get_session():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_session] = _get_session
    monkeypatch.setenv("VINCULACION_API_KEY", CLAVE)
    monkeypatch.setattr(servicio, "_ultima_purga", None)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def headers():
    return {"X-Api-Key": CLAVE}


@pytest_asyncio.fixture
async def crear_paciente(session_factory):
    usuario_id = uuid.uuid4()
    async with session_factory() as s:
        s.add(Usuario(id=usuario_id, nombre="dra", rol=RolUsuario.dra, password_hash="x"))
        await s.commit()

    async def _crear(nombre: str, movil: str) -> uuid.UUID:
        async with session_factory() as s:
            p = Paciente(
                numero_historia=f"H-{uuid.uuid4().hex[:8]}",
                movil=movil,
                nombre_completo=nombre,
                fecha_registro=date(2026, 10, 1),
                creado_por=usuario_id,
            )
            s.add(p)
            await s.commit()
            return p.id

    return _crear
