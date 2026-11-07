"""Cliente mínimo para la API de Jolpica-F1 (compatible con Ergast).

Responsabilidad única: hablar con la API respetando sus límites.
No sabe nada de archivos ni de GCS; eso vive en storage.py.
"""

import logging
import os
import time

import requests

BASE_URL = "https://api.jolpi.ca/ergast/f1"

# Límites publicados por Jolpica: 4 requests/segundo y 500/hora.
#
# Pausa mínima entre llamadas, configurable sin tocar el código (JOLPICA_MIN_INTERVAL).
# MIN_SECONDS_BETWEEN_CALLS es la pausa inicial y mínima, y la real se adapta, para evitar rechazos por 429
MIN_SECONDS_BETWEEN_CALLS = float(os.environ.get("JOLPICA_MIN_INTERVAL", "1.0"))
MAX_CALLS_PER_RUN = 450           # bajo las 500/hora
MAX_INTERVAL = 10.0        # tope de la pausa: nunca esperar más de 10 s entre llamadas
RECOVERY_STEP = 0.25       # cuánto se acorta la pausa después de una racha de éxitos
SUCCESSES_TO_RECOVER = 10  # largo de la racha de éxitos necesaria para acelerar

log = logging.getLogger(__name__)


class RateLimitBudgetExceeded(Exception):
    """Se agotó el presupuesto de llamadas de esta ejecución."""


class JolpicaClient:
    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self._last_call = 0.0
        self.calls = 0
        self.rejected = 0   # respuestas 429: se reportan aparte para diagnosticar
        self.interval = MIN_SECONDS_BETWEEN_CALLS   # pausa actual: se adapta al servidor
        self._streak = 0                            # éxitos seguidos desde el último 429

    def _throttle(self) -> None:
        """Espera lo necesario para respetar el ritmo máximo."""
        if self.calls >= MAX_CALLS_PER_RUN:
            raise RateLimitBudgetExceeded(
                f"Se alcanzaron {MAX_CALLS_PER_RUN} llamadas; reanudar en la próxima ejecución."
            )
        wait = self.interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)

    def _on_success(self) -> None:
        """Después de una racha de éxitos, acorta la pausa un poco (aumento aditivo del ritmo)."""
        self._streak += 1
        if self._streak >= SUCCESSES_TO_RECOVER:
            self.interval = max(MIN_SECONDS_BETWEEN_CALLS, self.interval - RECOVERY_STEP)
            self._streak = 0

    def _on_rejected(self) -> None:
        """Ante un 429, duplica la pausa (disminución multiplicativa del ritmo)."""
        self._streak = 0
        self.interval = min(MAX_INTERVAL, max(self.interval * 2, 1.0))

    def get(self, path: str, retries: int = 4) -> dict:
        """GET con pausa adaptativa ante 429 y reintentos ante errores del servidor."""
        url = f"{BASE_URL}/{path}"
        for attempt in range(retries):
            self._throttle()
            self._last_call = time.monotonic()
            self.calls += 1
            resp = self.session.get(url, params={"limit": 100}, timeout=30)

            if resp.status_code == 200:
                self._on_success()
                return resp.json()

            if resp.status_code == 429:
                self.rejected += 1
                self._on_rejected()
                # Si el servidor dice cuánto esperar, se le hace caso; si no, la pausa
                # ya duplicada (que aplica _throttle antes del reintento) hace el trabajo.
                retry_after = int(resp.headers.get("Retry-After", 0))
                log.warning("HTTP 429 en %s; pausa ahora %.2fs", path, self.interval)
                time.sleep(retry_after)
                continue

            if resp.status_code >= 500:
                backoff = 2 ** (attempt + 1)
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
