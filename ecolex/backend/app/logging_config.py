import logging
import sys

from decouple import config

LOG_LEVEL = config("LOG_LEVEL", default="INFO")

_SENSITIVE_KEYS = (
    "password",
    "hashed_password",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "secret",
)


class SensitiveDataFilter(logging.Filter):
    """Filtro que evita que contrasenas, tokens o secretos lleguen a los logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage().lower()
        for key in _SENSITIVE_KEYS:
            if key in message:
                record.msg = "[REDACTED] mensaje de log omitido por contener datos sensibles"
                record.args = ()
                break
        return True


def configure_logging() -> None:
    """Configura logging estructurado (formato JSON consistente) para toda la aplicacion."""
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt='{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
        '"logger": "%(name)s", "message": "%(message)s"}'
    )
    handler.setFormatter(formatter)
    handler.addFilter(SensitiveDataFilter())

    root_logger = logging.getLogger()
    root_logger.setLevel(LOG_LEVEL)
    root_logger.handlers = [handler]


def get_logger(name: str) -> logging.Logger:
    """Retorna un logger nombrado, usado de forma consistente en todos los modulos de la aplicacion."""
    return logging.getLogger(name)
