import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production-use")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:3000")
os.environ.setdefault("COOKIE_SECURE", "False")
os.environ.setdefault("GOOGLE_API_KEY", "test-google-api-key-not-for-production-use")

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app import database as app_database
from app.database import Base, get_db
from app.limiter import limiter
from app.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    """Sesion de base de datos de pruebas, usando SQLite en memoria en lugar de PostgreSQL."""
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db

# Codigo fuera del ciclo de requests (BackgroundTasks de ingestion_service) abre su propia sesion via
# app_database.AsyncSessionLocal en lugar de la dependencia get_db, asi que se sustituye directamente
# para que tambien use la base SQLite en memoria de las pruebas.
app_database.AsyncSessionLocal = TestSessionLocal


@pytest_asyncio.fixture(autouse=True)
async def prepare_database():
    """Crea el esquema antes de cada test y lo elimina despues, garantizando aislamiento entre tests."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(autouse=True)
def reset_rate_limiter():
    """Reinicia el almacenamiento del rate limiter antes de cada test para evitar fugas de estado entre tests."""
    limiter.reset()
    yield


@pytest_asyncio.fixture
async def client():
    """Cliente HTTP asincrono que ejecuta requests directamente contra la app FastAPI, sin red real."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
