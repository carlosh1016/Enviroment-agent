from contextlib import asynccontextmanager
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.database import engine
from app.limiter import limiter
from app.logging_config import configure_logging, get_logger
from app.routers import auth, conversations, documents, reports, stats, users
from app.services.minambiente_sync_service import run_sync_job

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida de la aplicacion: habilita pgvector, registra el arranque/apagado del
    servicio y (si esta activado) programa la sincronizacion periodica de normativa."""
    logger.info("Iniciando aplicacion")
    if engine.dialect.name == "postgresql":
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    scheduler = None
    if settings.ENABLE_NORM_SYNC_SCHEDULER:
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            run_sync_job,
            "interval",
            hours=settings.NORM_SYNC_INTERVAL_HOURS,
            id="sync_minambiente_corpus",
            # Corre una vez al arrancar en vez de esperar el primer intervalo completo: si el
            # proceso se reinicia seguido (deploys), evita quedarse sin sincronizar por dias.
            next_run_time=datetime.now(),
        )
        scheduler.start()
        logger.info(
            "Scheduler de sincronizacion de normativa activado (cada %d horas)",
            settings.NORM_SYNC_INTERVAL_HOURS,
        )

    yield

    if scheduler is not None:
        scheduler.shutdown(wait=False)
    logger.info("Deteniendo aplicacion")


app = FastAPI(
    title="Ecolex API",
    description=(
        "API SaaS multi-tenant con agente conversacional RAG para consulta de "
        "normativa ambiental colombiana"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exception_handler(request: Request, exc: RateLimitExceeded):
    """Devuelve el 429 de slowapi con el envoltorio de respuesta estandar."""
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"success": False, "message": "Demasiados intentos. Espera 1 minuto e intenta de nuevo.", "data": None},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Convierte cualquier HTTPException en el envoltorio de respuesta estandar, sin exponer detalles internos."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "message": exc.detail, "data": None},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Convierte errores de validacion de Pydantic en el envoltorio de respuesta estandar."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"success": False, "message": "Error de validacion en la solicitud", "data": exc.errors()},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Ultima red de seguridad: cualquier excepcion no controlada responde con el envoltorio estandar."""
    logger.error("Excepcion no controlada: %s", type(exc).__name__)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"success": False, "message": "Error interno del servidor", "data": None},
    )


@app.get("/health")
async def health_check():
    """Endpoint de verificacion de salud del servicio, usado por orquestadores y balanceadores."""
    return {"success": True, "message": "Servicio operativo", "data": {"status": "ok"}}


app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(conversations.router)
app.include_router(reports.router)
app.include_router(stats.router)
app.include_router(users.router)
