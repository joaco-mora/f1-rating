"""Pruebas del ingestor sin tocar la red.

Una sesión falsa imita a Jolpica: 3 rondas en el calendario, solo 2 con
resultados (la tercera "aún no se corre"). Correr con: pytest -q
"""

import json

import pytest

import jolpica_client
import main
from storage import LocalStorage


def race_payload(season, rnd, with_data=True):
    races = [{"season": str(season), "round": str(rnd), "Results": [{"position": "1"}]}]
    return {"MRData": {"RaceTable": {"Races": races if with_data else []}}}


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload, self.status_code, self.headers = payload, status, {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    """Calendario 2024 con 3 rondas; la ronda 3 todavía sin resultados."""

    def __init__(self):
        self.urls = []

    def get(self, url, params=None, timeout=None):
        self.urls.append(url)
        path = url.split("/f1/")[1]
        if path == "2024.json":
            races = [{"round": str(r)} for r in (1, 2, 3)]
            return FakeResponse({"MRData": {"RaceTable": {"Races": races}}})
        season, rnd = int(path.split("/")[0]), int(path.split("/")[1])
        return FakeResponse(race_payload(season, rnd, with_data=rnd < 3))


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(jolpica_client, "MIN_SECONDS_BETWEEN_CALLS", 0)


@pytest.fixture
def fake_api(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(main, "JolpicaClient", lambda: jolpica_client.JolpicaClient(session))
    return session


def test_descarga_rondas_disponibles(tmp_path, fake_api):
    summary = main.run([2024], "local", str(tmp_path))

    assert summary["descargada"] == 2
    assert summary["sin_datos"] == 1
    assert (tmp_path / "season=2024/round=01/results.json").exists()
    assert (tmp_path / "season=2024/round=02/qualifying.json").exists()
    assert not (tmp_path / "season=2024/round=03").exists()


def test_segunda_ejecucion_es_idempotente(tmp_path, fake_api):
    main.run([2024], "local", str(tmp_path))
    contenido_antes = (tmp_path / "season=2024/round=01/results.json").read_text()

    summary = main.run([2024], "local", str(tmp_path))

    assert summary["descargada"] == 0
    assert summary["ya_existia"] == 2
    assert (tmp_path / "season=2024/round=01/results.json").read_text() == contenido_antes


def test_presupuesto_agotado_termina_sin_error_y_retoma(tmp_path, fake_api, monkeypatch):
    # Presupuesto de 3 llamadas: calendario + resultados R1 + qualy R1.
    monkeypatch.setattr(jolpica_client, "MAX_CALLS_PER_RUN", 3)
    primera = main.run([2024], "local", str(tmp_path))
    assert primera["presupuesto_agotado"] is True
    assert primera["descargada"] == 1

    monkeypatch.setattr(jolpica_client, "MAX_CALLS_PER_RUN", 450)
    segunda = main.run([2024], "local", str(tmp_path))
    assert segunda["ya_existia"] == 1
    assert segunda["descargada"] == 1


def test_local_storage_no_sobrescribe(tmp_path):
    storage = LocalStorage(str(tmp_path))
    assert storage.write_json("a/b.json", {"v": 1}) is True
    assert storage.write_json("a/b.json", {"v": 2}) is False
    assert json.loads((tmp_path / "a/b.json").read_text()) == {"v": 1}


def test_rango_de_temporadas():
    assert main.parse_seasons("2022-2024") == [2022, 2023, 2024]
    assert main.parse_seasons("2024") == [2024]


def test_cuenta_rechazos_429_aparte():
    class SessionCon429:
        def __init__(self):
            self.n = 0

        def get(self, url, params=None, timeout=None):
            self.n += 1
            if self.n == 1:
                resp = FakeResponse({}, status=429)
                resp.headers = {"Retry-After": "0"}
                return resp
            return FakeResponse({"ok": True})

    client = jolpica_client.JolpicaClient(SessionCon429())
    assert client.get("2024.json") == {"ok": True}
    assert client.rejected == 1
    assert client.calls == 2
