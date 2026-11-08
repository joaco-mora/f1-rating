"""Ranking Glicko-2 de pilotos de F1: Modelo A (duelo contra el compañero de equipo).

Calcula tres ratings en paralelo, recorriendo las carreras en orden cronológico:
- carrera v0: solo duelos entre compañeros que terminaron (la regla original).
- carrera v1: clasificación de abandonos de los ADR-004 y ADR-005 (pesos y prorrateo).
- clasificación: clasificación real o parrilla como sustituto (ADR-006).

La v0 se mantiene para medir cuánto cambia el ranking con la v1.

Uso:
    python3 build_ranking.py --landing ~/landing --causas ~/causas_2023_2026.csv --top 25
"""

import argparse
import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from glicko2 import Game, Player, update

REFERENCE = Path(__file__).resolve().parent.parent / "reference"
PIERDE = {"derrota", "derrota_ponderada"}   # tratamientos en que el piloto pierde el duelo


def autos_compartidos(results: list[dict]) -> set[str]:
    """Números de auto que aparecen más de una vez: autos compartidos (común en los años 50).
    Provisional hasta el ADR-007: no se sabe cuánto manejó cada piloto, así que esos
    resultados no miden a ninguno y quedan fuera de los duelos."""
    numeros = Counter(r.get("number") for r in results if r.get("number"))
    return {n for n, veces in numeros.items() if veces > 1}


def sin_compartidos(results: list[dict]) -> list[dict]:
    compartidos = autos_compartidos(results)
    return [r for r in results if r.get("number") not in compartidos]


def es_indianapolis(race: dict) -> bool:
    """Las 500 Millas (1950-1960): otra competencia con otros pilotos; ADR pendiente."""
    return race.get("Circuit", {}).get("circuitId") == "indianapolis" and int(race["season"]) <= 1960


# --- Clasificación de resultados (ADR-004 y ADR-005) -------------------------

@dataclass(frozen=True)
class Clase:
    categoria: str
    tratamiento: str
    peso: float   # peso de la derrota, si el tratamiento es derrota o derrota_ponderada
    fuente: str   # revision | wikipedia | jolpica


def _leer(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _parece_causa(texto: str) -> bool:
    """True si el texto de Wikipedia describe una causa, y no un tiempo o un genérico."""
    if not texto or texto[0] in "+0123456789":
        return False
    return texto.lower() not in {"ret", "retired", "dnf", "dns"}


class Clasificador:
    """Aplica las tablas de referencia con la precedencia del ADR-005:
    revisión caso a caso > regla de Wikipedia > tabla de status de Jolpica.
    Lo que no tiene regla va a cuarentena: se excluye y se cuenta."""

    def __init__(self, reference: Path = REFERENCE, causas_wiki: Path | None = None):
        self.status = _leer(reference / "status_categoria.csv")
        self.reglas_wiki = {r["causa"]: r for r in _leer(reference / "wikipedia_causa_categoria.csv")}
        self.revisados = {(int(r["season"]), int(r["round"]), r["driver_id"]): r
                          for r in _leer(reference / "abandonos_revisados.csv")}
        self.wiki = {}
        if causas_wiki:
            for r in _leer(causas_wiki):
                self.wiki[(int(r["season"]), int(r["round"]), r["driver_id"])] = r["wiki_time_retired"]
        self.cuarentena = Counter()
        self.por_fuente = Counter()

    @staticmethod
    def _clase(row: dict, fuente: str) -> Clase:
        return Clase(row["categoria"], row["tratamiento"], float(row["peso_derrota"] or 0), fuente)

    def clasificar(self, season: int, rnd: int, driver_id: str, status: str) -> Clase | None:
        clave = (season, rnd, driver_id)
        clase = None
        if clave in self.revisados:
            clase = self._clase(self.revisados[clave], "revision")
        elif _parece_causa(causa := self.wiki.get(clave, "")):
            regla = self.reglas_wiki.get(causa.lower())
            if regla is None:
                self.cuarentena[f"wikipedia: {causa}"] += 1
                return None
            clase = self._clase(regla, "wikipedia")
        else:
            for row in self.status:
                desde = int(row["desde_temporada"] or 0)
                hasta = int(row["hasta_temporada"] or 9999)
                if not desde <= season <= hasta:
                    continue
                if (row["coincidencia"] == "exacta" and row["status"] == status) or \
                   (row["coincidencia"] == "prefijo" and status.startswith(row["status"])):
                    clase = self._clase(row, "jolpica")
                    break
            if clase is None:
                self.cuarentena[f"jolpica: {status}"] += 1
                return None
        if clase.tratamiento != "duelo":
            self.por_fuente[clase.fuente] += 1   # solo interesa contar los abandonos
        return clase


# --- Duelos -----------------------------------------------------------------

@dataclass
class Resultado:
    driver: str
    pos: int
    laps: int
    clase: Clase | None


def duelo(a: Resultado, b: Resultado, vueltas_carrera: int) -> tuple[str, str, float] | None:
    """Matriz de duelo del ADR-004. Devuelve (ganador, perdedor, peso) o None."""
    if a.clase is None or b.clase is None:
        return None
    a_term, b_term = a.clase.tratamiento == "duelo", b.clase.tratamiento == "duelo"
    if a_term and b_term:
        return (a.driver, b.driver, 1.0) if a.pos < b.pos else (b.driver, a.driver, 1.0)
    if a_term and b.clase.tratamiento in PIERDE:
        return a.driver, b.driver, b.clase.peso
    if b_term and a.clase.tratamiento in PIERDE:
        return b.driver, a.driver, a.clase.peso
    if not a_term and not b_term and vueltas_carrera and a.laps != b.laps:
        # Ambos abandonaron: prorrateo por vueltas, solo si quien dio menos vueltas
        # abandonó por una causa atribuible al piloto.
        gana, pierde = (a, b) if a.laps > b.laps else (b, a)
        if pierde.clase.tratamiento in PIERDE:
            peso = pierde.clase.peso * (gana.laps - pierde.laps) / vueltas_carrera
            return gana.driver, pierde.driver, peso
    return None


def termino(status: str) -> bool:
    """Regla de la v0: vio la bandera a cuadros (aunque sea con vueltas de atraso)."""
    return status == "Finished" or status.startswith("+") or status == "Lapped"


def duelos_v0(results: list[dict]) -> list[tuple[str, str, float]]:
    por_equipo = defaultdict(list)
    for r in sin_compartidos(results):
        if termino(r["status"]):
            por_equipo[r["Constructor"]["constructorId"]].append(r)
    out = []
    for equipo in por_equipo.values():
        for a, b in combinations(equipo, 2):
            if a["Driver"]["driverId"] == b["Driver"]["driverId"]:
                continue
            g, p = (a, b) if int(a["position"]) < int(b["position"]) else (b, a)
            out.append((g["Driver"]["driverId"], p["Driver"]["driverId"], 1.0))
    return out


def duelos_v1(race: dict, clasificador: Clasificador) -> list[tuple[str, str, float]]:
    season, rnd = int(race["season"]), int(race["round"])
    results = race["Results"]
    ganador = next((r for r in results if r["position"] == "1"), None)
    vueltas_carrera = int(ganador["laps"]) if ganador else 0
    por_equipo = defaultdict(list)
    for r in sin_compartidos(results):
        d = r["Driver"]["driverId"]
        clase = clasificador.clasificar(season, rnd, d, r["status"])
        por_equipo[r["Constructor"]["constructorId"]].append(
            Resultado(d, int(r["position"]), int(r["laps"]), clase))
    out = []
    for equipo in por_equipo.values():
        for a, b in combinations(equipo, 2):
            if a.driver == b.driver:
                continue   # un piloto que figura dos veces (manejó dos autos) no compite consigo mismo
            d = duelo(a, b, vueltas_carrera)
            if d and d[2] > 0:
                out.append(d)
    return out


def duelos_clasificacion(race: dict, qualifying: list[dict] | None,
                         fuentes: Counter) -> list[tuple[str, str, float]]:
    """ADR-006: clasificación real si existe; si no, la parrilla (sin largadas desde pits)."""
    equipos = defaultdict(list)
    for r in sin_compartidos(race["Results"]):
        equipos[r["Constructor"]["constructorId"]].append(r["Driver"]["driverId"])
    if qualifying:
        orden = {q["Driver"]["driverId"]: int(q["position"]) for q in qualifying}
        fuente = "clasificacion"
    else:
        orden = {r["Driver"]["driverId"]: int(r["grid"]) for r in race["Results"] if int(r["grid"]) > 0}
        fuente = "parrilla"
    out = []
    for pilotos in equipos.values():
        for a, b in combinations(pilotos, 2):
            if a != b and a in orden and b in orden:
                out.append((a, b, 1.0) if orden[a] < orden[b] else (b, a, 1.0))
                fuentes[fuente] += 1
    return out


# --- Motor ------------------------------------------------------------------

@dataclass
class Stats:
    name: str
    first_season: int
    last_season: int = 0
    duels: int = 0
    wins: int = 0
    peak: float = float("-inf")
    peak_label: str = ""


class Pista:
    """Un rating independiente: sus propios jugadores y estadísticas."""

    def __init__(self, min_duels: int):
        self.min_duels = min_duels
        self.players: dict[str, Player] = {}
        self.stats: dict[str, Stats] = {}

    def registrar(self, driver_id: str, name: str, season: int) -> None:
        if driver_id not in self.players:
            self.players[driver_id] = Player()
            self.stats[driver_id] = Stats(name, season)
        self.stats[driver_id].last_season = season

    def periodo(self, duelos: list[tuple[str, str, float]], label: str) -> None:
        """Una carrera es un período de rating. Todos se comparan contra el estado de sus
        rivales ANTES de la carrera; quien no tuvo duelos solo gana incertidumbre."""
        games = defaultdict(list)
        for g, p, peso in duelos:
            games[g].append(Game(self.players[p], 1.0, peso))
            games[p].append(Game(self.players[g], 0.0, peso))
            self.stats[g].duels += 1
            self.stats[p].duels += 1
            self.stats[g].wins += 1
        self.players = {pid: update(pl, games.get(pid, [])) for pid, pl in self.players.items()}
        for pid in games:
            s = self.stats[pid]
            if s.duels >= self.min_duels and self.players[pid].conservative > s.peak:
                s.peak, s.peak_label = self.players[pid].conservative, label

    def ranking(self) -> list[str]:
        elegibles = [pid for pid, s in self.stats.items() if s.duels >= self.min_duels]
        return sorted(elegibles, key=lambda pid: self.stats[pid].peak, reverse=True)


def load_races(landing: Path):
    """Entrega (race, qualifying) en orden cronológico; qualifying puede ser None."""
    for path in sorted(landing.glob("season=*/round=*/results.json")):
        races = json.loads(path.read_text())["MRData"]["RaceTable"]["Races"]
        if not races:
            continue
        qualifying = None
        q_path = path.with_name("qualifying.json")
        if q_path.exists():
            q_races = json.loads(q_path.read_text())["MRData"]["RaceTable"]["Races"]
            if q_races:
                qualifying = q_races[0]["QualifyingResults"]
        yield races[0], qualifying


def build(landing: Path, min_duels: int, clasificador: Clasificador | None = None) -> dict:
    clasificador = clasificador or Clasificador()
    pistas = {"v0": Pista(min_duels), "v1": Pista(min_duels), "clasificacion": Pista(min_duels)}
    resumen = Counter()
    fuentes_clasif = Counter()

    for race, qualifying in load_races(landing):
        season, rnd = int(race["season"]), int(race["round"])
        if es_indianapolis(race):
            resumen["indianapolis_excluidas"] += 1
            continue
        resumen["carreras"] += 1
        resumen["resultados_en_autos_compartidos"] += len(race["Results"]) - len(sin_compartidos(race["Results"]))
        for r in race["Results"]:
            d = r["Driver"]
            for pista in pistas.values():
                pista.registrar(d["driverId"], f'{d["givenName"]} {d["familyName"]}', season)
        label = f"{season} R{rnd:02d}"
        pistas["v0"].periodo(duelos_v0(race["Results"]), label)
        pistas["v1"].periodo(duelos_v1(race, clasificador), label)
        pistas["clasificacion"].periodo(duelos_clasificacion(race, qualifying, fuentes_clasif), label)

    return {"pistas": pistas, "resumen": resumen, "fuentes_clasificacion": fuentes_clasif,
            "abandonos_por_fuente": clasificador.por_fuente, "cuarentena": clasificador.cuarentena}


# --- Salida -----------------------------------------------------------------

def _fila(i: int, pista: Pista, pid: str) -> str:
    s = pista.stats[pid]
    years = f"{s.first_season}-{s.last_season}"
    return (f"{i:>3}  {s.name:<24}{years:<11}{s.duels:>7}{100 * s.wins / s.duels:>7.0f}%"
            f"{s.peak:>12.0f}  {s.peak_label:<9}")


def _cambio(pid: str, pos_v0: dict, i: int) -> str:
    if pid not in pos_v0:
        return "nuevo"
    delta = pos_v0[pid] - i
    return "=" if delta == 0 else f"{delta:+d}"


def imprimir(out: dict, top: int) -> None:
    pistas, r = out["pistas"], out["resumen"]
    print(f"\nCarreras: {r['carreras']} (más {r['indianapolis_excluidas']} de Indianápolis 1950-1960, excluidas)")
    print(f"Resultados en autos compartidos, fuera de los duelos: {r['resultados_en_autos_compartidos']}")
    print(f"Abandonos clasificados por fuente: {dict(out['abandonos_por_fuente'])}")
    cuarentena = out["cuarentena"]
    print(f"Cuarentena: {sum(cuarentena.values())} resultados"
          + (f" | más frecuentes: {cuarentena.most_common(5)}" if cuarentena else ""))
    print(f"Duelos de clasificación por fuente: {dict(out['fuentes_clasificacion'])}")

    encabezado = f"\n{'#':>3}  {'Piloto':<24}{'Años':<11}{'Duelos':>7}{'% gan.':>8}{'Pico cons.':>12}  {'Cuándo':<9}"
    v0, v1 = pistas["v0"].ranking(), pistas["v1"].ranking()
    pos_v0 = {pid: i for i, pid in enumerate(v0, 1)}
    print("\n=== CARRERA (v1: con clasificación de abandonos) ===" + encabezado + f"{'vs v0':>7}")
    for i, pid in enumerate(v1[:top], 1):
        print(_fila(i, pistas["v1"], pid) + f"{_cambio(pid, pos_v0, i):>7}")

    print("\n=== CLASIFICACIÓN (real o parrilla) ===" + encabezado)
    for i, pid in enumerate(pistas["clasificacion"].ranking()[:top], 1):
        print(_fila(i, pistas["clasificacion"], pid))


def guardar_csv(out: dict, carpeta: Path) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    for nombre, pista in out["pistas"].items():
        with (carpeta / f"ranking_{nombre}.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["rank", "driver_id", "name", "first_season", "last_season", "duels", "wins",
                        "peak_conservative", "peak_when", "rating", "rd", "vol"])
            for i, pid in enumerate(pista.ranking(), 1):
                s, p = pista.stats[pid], pista.players[pid]
                w.writerow([i, pid, s.name, s.first_season, s.last_season, s.duels, s.wins,
                            round(s.peak, 1), s.peak_label, round(p.rating, 1), round(p.rd, 1),
                            round(p.vol, 4)])
    print(f"\nRankings completos guardados en {carpeta}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ranking Glicko-2 de pilotos de F1 (Modelo A)")
    parser.add_argument("--landing", required=True, help="Carpeta con season=*/round=*/results.json")
    parser.add_argument("--causas", help="CSV de causas de abandono de Wikipedia (ADR-005)")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--min-duels", type=int, default=30,
                        help="Duelos mínimos para entrar al ranking (filtra muestras chicas)")
    parser.add_argument("--csv-dir", help="Opcional: carpeta para guardar los rankings completos")
    args = parser.parse_args()

    causas = Path(args.causas).expanduser() if args.causas else None
    if causas is None:
        print("Aviso: sin --causas, los abandonos 'Retired' desde 2023 quedan como no atribuibles.")
    out = build(Path(args.landing).expanduser(), args.min_duels, Clasificador(REFERENCE, causas))
    imprimir(out, args.top)
    if args.csv_dir:
        guardar_csv(out, Path(args.csv_dir).expanduser())


if __name__ == "__main__":
    main()
