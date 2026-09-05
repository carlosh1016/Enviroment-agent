from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.limiter import limiter
from app.logging_config import configure_logging, get_logger
from app.routers import auth, projects

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida de la aplicacion: registra el arranque y el apagado del servicio."""
    logger.info("Iniciando aplicacion")
    yield
    logger.info("Deteniendo aplicacion")


app = FastAPI(
    title="Plataforma de Analisis de Contaminacion de Suelos",
    description=(
        "API SaaS multi-tenant para estudios de contaminacion de suelos "
        "orientada al sector inmobiliario y de construccion en Colombia"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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


@app.get("/health")
async def health_check():
    """Endpoint de verificacion de salud del servicio, usado por orquestadores y balanceadores."""
    return {"success": True, "message": "Servicio operativo", "data": {"status": "ok"}}


app.include_router(auth.router)
app.include_router(projects.router)
