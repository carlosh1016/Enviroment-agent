# Ecolex backend

## Dependencias de sistema

- **poppler-utils**: requerido por `pdf2image` para convertir paginas de PDFs escaneados a
  imagen dentro del pipeline de ingesta (`app/services/ingestion_service.py`). Ya viene
  instalado en la imagen Docker (ver `Dockerfile`). Si corres el backend fuera de Docker
  (Ubuntu/Debian):

  ```
  sudo apt-get install poppler-utils
  ```
