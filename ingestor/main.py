"""Ingestor: descarga de Jolpica las rondas que aún no están en el storage.

Uso local:
    python main.py --seasons 2024 --backend local --dest ./landing

Uso en la nube (Cloud Run Job):
    python main.py --seasons 2026 --backend gcs --dest mi-bucket-landing

Diseño:
- El storage es la única fuente de verdad del estado: si el archivo existe,
  la ronda ya se descargó. No hay tabla de control aparte.
- Escribe qualifying.json primero y results.json al final. Más adelante,
  Eventarc se dispara con results.json; cuando eso pase, la qualy ya estará.
- Si se acaba el presupuesto de llamadas, termina sin error: la próxima
  ejecución sigue donde quedó, porque salta lo que ya existe.
"""

import argparse
import logging
import sys

from jolpica_client import JolpicaClient, RateLimitBudgetExceeded, has_data
from storage import build_storage, object_path

log = logging.getLogger("ingestor")


def parse_seasons(value: str) -> list[int]:
    """Acepta '2024' o un rango '2000-2024'."""
    if "-" in value:
        start, end = value.split("-")
        return list(range(int(start), int(end) + 1))
    return [int(value)]


def ingest_round(client, storage, season: int, rnd: int) -> str:
    """Descarga una ronda. Devuelve el resultado para el resumen final."""
    results_path = object_path(season, rnd, "results")
    if storage.exists(results_path):
        return "ya_existia"

    results = client.race_results(season, rnd)
    if not has_data(results):
        # La carrera aún no se corre o Jolpica no publica resultados todavía.
        return "sin_datos"

    qualifying = client.qualifying(season, rnd)
    if has_data(qualifying):
        storage.write_json(object_path(season, rnd, "qualifying"), qualifying)
    else:
        log.warning("%s R%02d sin clasificación publicada", season, rnd)

    # results.json va al final: su llegada indica que la ronda está completa.
    storage.write_json(results_path, results)
    return "descargada"


def run(seasons: list[int], backend: str, dest: str) -> dict:
    client = JolpicaClient()
    storage = build_storage(backend, dest)
    summary = {"descargada": 0, "ya_existia": 0, "sin_datos": 0}

    try:
        for season in seasons:
            for rnd in client.season_rounds(season):
                outcome = ingest_round(client, storage, season, rnd)
                summary[outcome] += 1
                if outcome == "descargada":
                    log.info("%s R%02d descargada", season, rnd)
                elif outcome == "sin_datos":
                    # Las rondas siguientes de esta temporada tampoco tendrán datos.
                    break
    except RateLimitBudgetExceeded as exc:
        log.warning("%s", exc)
        summary["presupuesto_agotado"] = True

    summary["llamadas_api"] = client.calls
    summary["rechazos_429"] = client.rejected
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingestor de resultados de F1 desde Jolpica")
    parser.add_argument("--seasons", required=True, help="Año o rango, ej. 2024 o 2000-2024")
    parser.add_argument("--backend", choices=["local", "gcs"], default="local")
    parser.add_argument("--dest", default="./landing", help="Carpeta local o nombre del bucket")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    summary = run(parse_seasons(args.seasons), args.backend, args.dest)
    log.info("Resumen: %s", summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
