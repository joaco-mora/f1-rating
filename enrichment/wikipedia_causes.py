"""Extractor de causas de abandono desde Wikipedia (ADR-005, experimento).

Para cada carrera ya descargada por el ingestor:
1. Toma el artículo de Wikipedia desde el campo `url` que entrega Jolpica.
2. Descarga su HTML con la API de MediaWiki (una llamada por carrera).
3. Ubica la tabla de clasificación de la CARRERA (no la de clasificación ni la del sprint).
4. Cruza cada fila con Jolpica por número de auto y guarda el texto de "Time/Retired".

No interpreta las causas: solo las extrae. La clasificación (por ejemplo,
"Power unit" -> mecanico) es un paso posterior, con su propia tabla de referencia.

Uso:
    python3 wikipedia_causes.py --landing ~/landing --seasons 2024 \
        --out ~/causas_2024.csv --cache ~/wiki_cache
"""

import argparse
import csv
import json
import re
import time
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup

API = "https://en.wikipedia.org/w/api.php"
# Wikimedia pide identificar al cliente con un User-Agent descriptivo y un contacto.
USER_AGENT = "f1-rating/0.1 (https://github.com/joaco-mora/f1-rating; proyecto educativo)"
PAUSA_SEGUNDOS = 1.0
OVERRIDES = Path(__file__).resolve().parent.parent / "reference" / "wikipedia_overrides.csv"
TITULOS_SECCION_CARRERA = {"race", "race classification"}


# --- Descarga ---------------------------------------------------------------

def page_title(url: str) -> str:
    """'https://en.wikipedia.org/wiki/2024_Australian_Grand_Prix' -> '2024_Australian_Grand_Prix'."""
    return unquote(urlparse(url).path.rsplit("/", 1)[-1])


def fetch_page(session: requests.Session, title: str, cache: Path | None) -> tuple[str, int]:
    """Devuelve (html, revid). Con caché, cada página se descarga una sola vez.

    El revid identifica la versión exacta del artículo: con él, cualquier dato
    extraído se puede rastrear hasta el texto que lo originó, aunque el artículo
    se edite después.
    """
    cached = cache / f"{title}.json" if cache else None
    if cached and cached.exists():
        data = json.loads(cached.read_text())
        return data["html"], data["revid"]

    params = {"action": "parse", "page": title, "prop": "text|revid", "redirects": 1,
              "format": "json", "formatversion": 2}
    resp = session.get(API, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise LookupError(f"{title}: {data['error'].get('info')}")
    html, revid = data["parse"]["text"], data["parse"]["revid"]

    if cached:
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps({"title": title, "revid": revid, "html": html}))
    time.sleep(PAUSA_SEGUNDOS)
    return html, revid


# --- Parsing ----------------------------------------------------------------

def clean(text: str) -> str:
    """Quita notas al pie como [a] o [12] y normaliza los espacios."""
    text = re.sub(r"\[[^\]]*\]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _header(table) -> list[str]:
    first_row = table.find("tr")
    return [clean(c.get_text()).lower() for c in first_row.find_all(["th", "td"])] if first_row else []


def is_classification(table) -> bool:
    header = _header(table)
    return "laps" in header and any(h.startswith("time/retired") for h in header)


def find_race_table(html: str):
    """La primera tabla de clasificación que aparece después del título "Race".

    Se busca por sección y no solo por columnas, porque la tabla del sprint tiene
    exactamente las mismas columnas que la de la carrera.
    """
    soup = BeautifulSoup(html, "html.parser")
    # Las notas al pie vienen como superíndices (<sup>) y a veces sin corchetes:
    # "Laps<sup>a</sup>" se leería "Lapsa", y "Collision<sup>1</sup>", "Collision1".
    # Se eliminan del HTML antes de leer cualquier texto.
    for sup in soup.find_all("sup"):
        sup.decompose()
    for heading in soup.find_all(["h2", "h3", "h4"]):
        if clean(heading.get_text()).lower() in TITULOS_SECCION_CARRERA:
            table = heading.find_next("table")
            if table is not None and is_classification(table):
                return table
    return None


def _col(header: list[str], prefix: str) -> int:
    return next(i for i, h in enumerate(header) if h.startswith(prefix))


def parse_rows(table) -> list[dict]:
    header = _header(table)
    i_no, i_driver = _col(header, "no"), _col(header, "driver")
    i_laps, i_time = _col(header, "laps"), _col(header, "time/retired")

    rows = []
    for tr in table.find_all("tr")[1:]:
        cells = tr.find_all(["th", "td"])
        if len(cells) != len(header):
            continue  # filas de pie de tabla: vuelta rápida, fuentes, etc.
        number = clean(cells[i_no].get_text())
        if not number.isdigit():
            continue
        rows.append({
            "number": number,
            "driver": clean(cells[i_driver].get_text()),
            "laps": clean(cells[i_laps].get_text()),
            "time_retired": clean(cells[i_time].get_text()),
        })
    return rows


def has_cause(text: str) -> bool:
    """True si el texto describe una causa, y no un tiempo, una diferencia o un genérico."""
    if not text or re.match(r"^[+\d]", text):
        return False
    return text.lower() not in {"ret", "retired", "dnf", "dns"}


# --- Proceso principal ------------------------------------------------------

def parse_seasons(value: str) -> list[int]:
    if "-" in value:
        start, end = value.split("-")
        return list(range(int(start), int(end) + 1))
    return [int(value)]


def load_overrides(path: Path) -> dict[tuple[int, int], str]:
    """Títulos de Wikipedia corregidos a mano, para cuando la URL de Jolpica está mal."""
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return {(int(r["season"]), int(r["round"])): r["wiki_title"] for r in csv.DictReader(f)}


def run(landing: Path, seasons: list[int], out: Path, cache: Path | None,
        overrides_path: Path = OVERRIDES) -> Counter:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    overrides = load_overrides(overrides_path)
    stats = Counter()
    causes = Counter()

    def count_unprocessed(race: dict) -> None:
        """Los 'Retired' de una carrera fallida cuentan en el denominador: si no, la
        cobertura se ve mejor de lo que es (sesgo de supervivencia en la métrica)."""
        n = sum(1 for res in race["Results"] if res["status"] == "Retired")
        stats["retired"] += n
        stats["retired_sin_procesar"] += n

    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["season", "round", "number", "driver_id", "jolpica_status", "jolpica_laps",
                         "wiki_driver", "wiki_laps", "wiki_time_retired", "wiki_title", "wiki_revid"])

        for season in seasons:
            for path in sorted(landing.glob(f"season={season}/round=*/results.json")):
                races = json.loads(path.read_text())["MRData"]["RaceTable"]["Races"]
                if not races:
                    continue
                race = races[0]
                title = overrides.get((season, int(race["round"]))) or page_title(race["url"])
                stats["carreras"] += 1
                try:
                    html, revid = fetch_page(session, title, cache)
                except (requests.RequestException, LookupError) as exc:
                    print(f"  ⚠️ {season} R{race['round']}: no se pudo descargar ({exc})")
                    stats["carreras_sin_pagina"] += 1
                    count_unprocessed(race)
                    continue

                table = find_race_table(html)
                if table is None:
                    print(f"  ⚠️ {season} R{race['round']}: no se encontró la tabla de carrera en {title}")
                    stats["carreras_sin_tabla"] += 1
                    count_unprocessed(race)
                    continue
                wiki = {r["number"]: r for r in parse_rows(table)}

                for res in race["Results"]:
                    w = wiki.get(res["number"], {})
                    stats["resultados"] += 1
                    if not w:
                        stats["sin_cruce"] += 1
                    elif w["laps"] != res["laps"]:
                        # Convención conocida: Jolpica registra 0 vueltas a los descalificados y
                        # Wikipedia, las que realmente dieron. No es un error: se cuenta aparte.
                        if res["status"] == "Disqualified":
                            stats["vueltas_distintas_dsq"] += 1
                        else:
                            stats["vueltas_distintas"] += 1
                    if res["status"] == "Retired":
                        stats["retired"] += 1
                        if has_cause(w.get("time_retired", "")):
                            stats["retired_con_causa"] += 1
                            causes[w["time_retired"]] += 1
                    writer.writerow([season, race["round"], res["number"], res["Driver"]["driverId"],
                                     res["status"], res["laps"], w.get("driver", ""), w.get("laps", ""),
                                     w.get("time_retired", ""), title, revid])

    print(f"\nCarreras: {stats['carreras']} (sin página: {stats['carreras_sin_pagina']}, "
          f"sin tabla: {stats['carreras_sin_tabla']})")
    print(f"Resultados: {stats['resultados']} (sin cruce por número: {stats['sin_cruce']}, "
          f"vueltas distintas entre fuentes: {stats['vueltas_distintas']}, "
          f"más {stats['vueltas_distintas_dsq']} descalificados con 0 vueltas en Jolpica)")
    if stats["retired"]:
        share = stats["retired_con_causa"] / stats["retired"]
        print(f"'Retired' en Jolpica: {stats['retired']}; con causa en Wikipedia: "
              f"{stats['retired_con_causa']} ({share:.1%}); "
              f"en carreras no procesadas: {stats['retired_sin_procesar']}")
    print("\nCausas encontradas para los 'Retired' (Pareto):")
    for cause, n in causes.most_common():
        print(f"  {n:>4}  {cause}")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Causas de abandono desde Wikipedia (ADR-005)")
    parser.add_argument("--landing", required=True, help="Carpeta con season=*/round=*/results.json")
    parser.add_argument("--seasons", required=True, help="Año o rango, ej. 2024 o 2023-2026")
    parser.add_argument("--out", required=True, help="CSV de salida")
    parser.add_argument("--cache", help="Carpeta para guardar las páginas descargadas")
    args = parser.parse_args()
    run(Path(args.landing).expanduser(), parse_seasons(args.seasons), Path(args.out).expanduser(),
        Path(args.cache).expanduser() if args.cache else None)


if __name__ == "__main__":
    main()
