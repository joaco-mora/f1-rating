"""Dónde se guarda el JSON crudo.

Dos implementaciones con la misma interfaz:
- LocalStorage: carpeta en tu computador, para desarrollar y probar sin nube.
- GCSStorage: bucket de Cloud Storage, para producción.

El resto del código no sabe cuál está usando. Así pruebas todo localmente y
el día que despliegas solo cambias un parámetro.
"""

import json
from pathlib import Path
from typing import Protocol


def object_path(season: int, rnd: int, kind: str) -> str:
    """Ruta particionada estilo Hive: season=2024/round=05/results.json.

    El cero a la izquierda en la ronda hace que el orden alfabético
    coincida con el orden cronológico.
    """
    return f"season={season}/round={rnd:02d}/{kind}.json"


class Storage(Protocol):
    def exists(self, path: str) -> bool: ...
    def write_json(self, path: str, payload: dict) -> bool: ...


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root)

    def exists(self, path: str) -> bool:
        return (self.root / path).exists()

    def write_json(self, path: str, payload: dict) -> bool:
        """Escribe solo si no existe. Devuelve True si escribió."""
        target = self.root / path
        if target.exists():
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        return True


class GCSStorage:
    def __init__(self, bucket: str):
        from google.cloud import storage  # import diferido: no se necesita en local

        self.bucket = storage.Client().bucket(bucket)

    def exists(self, path: str) -> bool:
        return self.bucket.blob(path).exists()

    def write_json(self, path: str, payload: dict) -> bool:
        """Escribe solo si el objeto no existe, de forma atómica.

        if_generation_match=0 le dice a GCS: "crea este objeto solo si no existe".
        Si dos ejecuciones compiten, una gana y la otra recibe un error 412,
        que tratamos como "ya estaba". Esto hace al ingestor idempotente sin
        necesidad de una base de datos de estado.
        """
        from google.api_core.exceptions import PreconditionFailed

        blob = self.bucket.blob(path)
        try:
            blob.upload_from_string(
                json.dumps(payload, ensure_ascii=False),
                content_type="application/json",
                if_generation_match=0,
            )
            return True
        except PreconditionFailed:
            return False


def build_storage(backend: str, dest: str) -> Storage:
    if backend == "local":
        return LocalStorage(dest)
    if backend == "gcs":
        return GCSStorage(dest)
    raise ValueError(f"Backend desconocido: {backend}")
