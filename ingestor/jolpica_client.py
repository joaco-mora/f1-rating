"""Cliente mínimo para la API de Jolpica-F1 (compatible con Ergast).

Responsabilidad única: hablar con la API respetando sus límites.
No sabe nada de archivos ni de GCS; eso vive en storage.py.
"""

import logging
import time

import requests

BASE_URL = "https://api.jolpi.ca/ergast/f1"

# Límites publicados por Jolpica: 4 requests/segundo y 500/hora.
# Dejamos margen para no rozar el límite.
MIN_SECONDS_BETWEEN_CALLS = 0.3   # ~3,3 req/s
MAX_CALLS_PER_RUN = 450           # bajo las 500/hora

log = logging.getLogger(__name__)


class RateLimitBudgetExceeded(Exception):
    """Se agotó el presupuesto de llamadas de esta ejecución."""


class JolpicaClient:
    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self._last_call = 0.0
        self.calls = 0

    def _throttle(self) -> None:
        """Espera lo necesario para respetar el ritmo máximo."""
        if self.calls >= MAX_CALLS_PER_RUN:
            raise RateLimitBudgetExceeded(
                f"Se alcanzaron {MAX_CALLS_PER_RUN} llamadas; reanudar en la próxima ejecución."
            )
        wait = MIN_SECONDS_BETWEEN_CALLS - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)

    def get(self, path: str, retries: int = 4) -> dict:
        """GET con throttling y reintentos con backoff exponencial."""
        url = f"{BASE_URL}/{path}"
        for attempt in range(retries):
            self._throttle()
            self._last_call = time.monotonic()
            self.calls += 1
            resp = self.session.get(url, params={"limit": 100}, timeout=30)

            if resp.status_code == 200:
                return resp.json()

            # 429 = nos pasamos del límite; 5xx = falla del servidor. Ambos se reintentan.
            if resp.status_code == 429 or resp.status_code >= 500:
                backoff = int(resp.headers.get("Retry-After", 2 ** (attempt + 1)))
                log.warning("HTTP %s en %s; reintento en %ss", resp.status_code, path, backoff)
                time.sleep(backoff)
                continue

            # 4xx distinto de 429: error nuestro (URL mala). Reintentar no sirve.
            resp.raise_for_status()

        raise RuntimeError(f"Sin éxito tras {retries} intentos: {path}")

    # --- Endpoints que usamos ---

    def season_rounds(self, season: int) -> list[int]:
        """Rondas del calendario de una temporada."""
        data = self.get(f"{season}.json")
        return [int(r["round"]) for r in data["MRData"]["RaceTable"]["Races"]]

    def race_results(self, season: int, rnd: int) -> dict:
        return self.get(f"{season}/{rnd}/results.json")

    def qualifying(self, season: int, rnd: int) -> dict:
        return self.get(f"{season}/{rnd}/qualifying.json")


def has_data(payload: dict) -> bool:
    """Jolpica responde 200 con lista vacía si la carrera aún no tiene resultados."""
    return bool(payload["MRData"]["RaceTable"]["Races"])
