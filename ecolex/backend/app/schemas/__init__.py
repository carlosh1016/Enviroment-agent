from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Envoltorio estandar de respuesta usado por todos los endpoints de la API."""

    success: bool
    message: str
    data: T | None = None


def success_response(data: Any = None, message: str = "OK") -> dict:
    """Construye el envoltorio de respuesta estandar {success, message, data}."""
    return {"success": True, "message": message, "data": data}
