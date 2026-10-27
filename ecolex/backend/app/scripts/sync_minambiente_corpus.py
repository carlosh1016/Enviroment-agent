"""Sincroniza el corpus normativo compartido (tenant _base) contra el listado publico de
normativa de Minambiente. Agrega SOLO normas nuevas (nunca reemplaza/borra una ya ingestada);
ver app/services/minambiente_sync_service.py para el alcance completo y las decisiones de diseno.

Uso (dentro del contenedor del backend, donde esta instalado el paquete `app`):
    docker compose exec backend python -m app.scripts.sync_minambiente_corpus
    docker compose exec backend python -m app.scripts.sync_minambiente_corpus --max-new-per-category 3

--max-new-per-category N: limita cuantas normas NUEVAS se ingestan por categoria en esta
corrida (recomendado para la primera corrida real contra una fuente nunca sincronizada antes:
sin tope, TODA la pagina 1 de cada categoria cuenta como "nueva" -- puede ser un centenar de
PDFs, cada uno con costo real de OpenRouter). Sin este flag, no hay tope.

Este script SI accede a la base de datos directamente (a diferencia de
ecolex/scripts/ingest_base_corpus.py, que pasa por los endpoints HTTP): necesita su propia
tabla de estado (external_norms) para no re-descargar/re-ingestar lo mismo en cada corrida,
algo que no tiene sentido modelar como una llamada HTTP sin estado.
"""

import argparse
import asyncio
import sys

from app.logging_config import configure_logging
from app.services.minambiente_sync_service import run_sync_job

configure_logging()


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-new-per-category",
        type=int,
        default=None,
        help="Tope de normas nuevas a ingestar por categoria en esta corrida (sin tope por defecto)",
    )
    args = parser.parse_args()

    all_stats = await run_sync_job(max_new_per_category=args.max_new_per_category)
    total_failed = sum(s.failed for s in all_stats)
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
