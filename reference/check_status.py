"""Controles de calidad de la clasificación de abandonos (ADR-004, sección 7).

Prototipo de los controles que hará el loader. Corre sobre la carpeta de datos crudos:

    python3 check_status.py --landing ~/landing

1. Validez de la tabla: combinaciones permitidas y vigencias sin solapes.
2. Cobertura: cada status recibido tiene una fila vigente (si no, iría a cuarentena).
3. Deriva: proporción de abandonos no atribuibles por temporada.
"""

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

TABLE = Path(__file__).parent / "status_categoria.csv"

COMBINACIONES_VALIDAS = {
    ("terminado", "duelo", ""),
    ("error_piloto", "derrota", "1.0"),
    ("colision", "derrota_ponderada", "0.5"),
    ("no_reanudo", "derrota_ponderada", "0.5"),
    ("mecanico", "excluir_penaliza_constructor", ""),
    ("operacion_equipo", "excluir_penaliza_constructor", ""),
    ("no_compitio", "excluir_penaliza_constructor", ""),   # Did not start
    ("no_compitio", "excluir", ""),
    ("fortuito", "excluir", ""),
    ("victima", "excluir", ""),         # abandono por error de otro piloto (ADR-005)
    ("no_atribuible", "excluir", ""),
    ("sancion", "excluir", ""),
    ("sancion_tecnica", "excluir_penaliza_constructor", ""),  # auto fuera de reglamento (ADR-005)
    ("sancion_deportiva", "excluir", ""),                      # ADR-005
}
UMBRAL_NO_ATRIBUIBLE = 0.30   # ADR-004, pregunta abierta 3: sobre esto, el modelo pierde validez


def load_table(path: Path) -> list[dict]:
    return list(csv.DictReader(path.open(encoding="utf-8")))


def season_range(row: dict) -> tuple[int, int]:
    return int(row["desde_temporada"] or 0), int(row["hasta_temporada"] or 9999)


def validate_table(rows: list[dict]) -> list[str]:
    errors = []
    for r in rows:
        if (r["categoria"], r["tratamiento"], r["peso_derrota"]) not in COMBINACIONES_VALIDAS:
            errors.append(f"Combinación inválida en '{r['status']}'")
    by_status = defaultdict(list)
    for r in rows:
        by_status[(r["status"], r["coincidencia"])].append(season_range(r))
    for (status, _), ranges in by_status.items():
        ranges.sort()
        for (_, end), (start, _) in zip(ranges, ranges[1:]):
            if start <= end:
                errors.append(f"Vigencias solapadas en '{status}'")
    return errors


def classify(rows: list[dict], status: str, season: int) -> dict | None:
    """Devuelve la fila vigente para ese status y temporada, o None (cuarentena)."""
    for r in rows:
        desde, hasta = season_range(r)
        if not desde <= season <= hasta:
            continue
        if r["coincidencia"] == "exacta" and r["status"] == status:
            return r
        if r["coincidencia"] == "prefijo" and status.startswith(r["status"]):
            return r
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Controles de calidad de status (ADR-004)")
    parser.add_argument("--landing", required=True)
    args = parser.parse_args()

    rows = load_table(TABLE)
    errors = validate_table(rows)
    print(f"1. Validez de la tabla ({len(rows)} filas): {'OK' if not errors else errors}")

    cuarentena = Counter()
    abandonos = Counter()
    no_atribuibles = Counter()
    for path in sorted(Path(args.landing).expanduser().glob("season=*/round=*/results.json")):
        races = json.loads(path.read_text())["MRData"]["RaceTable"]["Races"]
        if not races:
            continue
        season = int(races[0]["season"])
        for res in races[0]["Results"]:
            row = classify(rows, res["status"], season)
            if row is None:
                cuarentena[(season, res["status"])] += 1
                continue
            if row["categoria"] in ("terminado", "no_compitio"):
                continue
            abandonos[season] += 1
            if row["categoria"] == "no_atribuible":
                no_atribuibles[season] += 1

    print(f"2. Cobertura: {'OK, nada en cuarentena' if not cuarentena else dict(cuarentena)}")

    print(f"3. Deriva: abandonos no atribuibles por temporada (umbral {UMBRAL_NO_ATRIBUIBLE:.0%})")
    print(f"   {'Temp.':<7}{'Aband.':>7}{'No atrib.':>11}{'%':>7}")
    for season in sorted(abandonos):
        share = no_atribuibles[season] / abandonos[season]
        flag = "  ⚠️ sobre el umbral" if share > UMBRAL_NO_ATRIBUIBLE else ""
        print(f"   {season:<7}{abandonos[season]:>7}{no_atribuibles[season]:>11}{share:>7.0%}{flag}")


if __name__ == "__main__":
    main()
