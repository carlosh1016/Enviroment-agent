from datetime import date

from pydantic import BaseModel


class ReportRequest(BaseModel):
    """Rango de fechas opcional para el informe. Si no se especifican, se usan las fechas del
    primer y ultimo mensaje de la conversacion."""

    date_from: date | None = None
    date_to: date | None = None
