"""Modelo A, versión 0: Glicko-2 por duelo contra el compañero de equipo.

Lee los results.json del ingestor (carpeta local), recorre las carreras en
orden cronológico y calcula el rating de cada piloto.

Simplificaciones de esta v0 respecto del ADR-001 (se resuelven en la v1):
- Solo carrera; la clasificación queda para después.
- Un duelo cuenta solo si AMBOS pilotos terminaron la carrera. Todos los
  abandonos se excluyen; la atribución mecánico/error/colisión viene después.

Uso:
    python build_ranking.py --landing ~/landing --top 20
"""

import argparse
import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from glicko2 import Game, Player, update


def finished(status: str) -> bool:
    """True si el piloto vio la bandera a cuadros (aunque sea con vueltas de atraso)."""
    return status == "Finished" or status.startswith("+") or status == "Lapped"


@dataclass
class DriverStats:
    name: str
    duels: int = 0
    wins: int = 0
    peak: float = float("-inf")      # mejor rating conservador alcanzado
    peak_label: str = ""             # temporada y ronda del pico
    first_season: int = 0
    last_season: int = 0


def load_races(landing: Path):
    """Entrega (temporada, ronda, lista de resultados) en orden cronológico."""
    # El cero a la izquierda en round=NN hace que el orden alfabético sea cronológico.
    for path in sorted(landing.glob("season=*/round=*/results.json")):
        races = json.loads(path.read_text())["MRData"]["RaceTable"]["Races"]
        if races:
            race = races[0]
            yield int(race["season"]), int(race["round"]), race["Results"]


def teammate_duels(results: list[dict]) -> list[tuple[str, str]]:
    """Duelos (ganador, perdedor) entre compañeros que terminaron la carrera."""
    by_team = defaultdict(list)
    for r in results:
        if finished(r["status"]):
            by_team[r["Constructor"]["constructorId"]].append(r)

    duels = []
    for team in by_team.values():
        for a, b in combinations(team, 2):
            winner, loser = (a, b) if int(a["position"]) < int(b["position"]) else (b, a)
            duels.append((winner["Driver"]["driverId"], loser["Driver"]["driverId"]))
    return duels


def build(landing: Path, min_duels: int):
    players: dict[str, Player] = {}
    stats: dict[str, DriverStats] = {}

    for season, rnd, results in load_races(landing):
        # Registra pilotos nuevos con el rating inicial (1500, RD 350).
        for r in results:
            d = r["Driver"]
            if d["driverId"] not in players:
                players[d["driverId"]] = Player()
                stats[d["driverId"]] = DriverStats(
                    f'{d["givenName"]} {d["familyName"]}', first_season=season
                )
            stats[d["driverId"]].last_season = season

        # Cada carrera es un período de rating. Todos se comparan contra el
        # estado de sus rivales ANTES de la carrera, por eso se arma la lista
        # de partidas completa antes de actualizar a nadie.
        games: dict[str, list[Game]] = defaultdict(list)
        for winner, loser in teammate_duels(results):
            games[winner].append(Game(players[loser], 1.0))
            games[loser].append(Game(players[winner], 0.0))
            stats[winner].wins += 1
            stats[winner].duels += 1
            stats[loser].duels += 1

        # Se actualiza a TODOS los pilotos conocidos: quien no corrió, o no
        # tuvo duelo válido, solo aumenta su incertidumbre.
        players = {pid: update(p, games.get(pid, [])) for pid, p in players.items()}

        for pid in games:
            s = stats[pid]
            if s.duels >= min_duels and players[pid].conservative > s.peak:
                s.peak = players[pid].conservative
                s.peak_label = f"{season} R{rnd:02d}"

    return players, stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Ranking Glicko-2 de pilotos de F1 (Modelo A, v0)")
    parser.add_argument("--landing", required=True, help="Carpeta con season=*/round=*/results.json")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--min-duels", type=int, default=30,
                        help="Duelos mínimos para entrar al ranking (filtra muestras chicas)")
    parser.add_argument("--csv", help="Opcional: ruta para guardar el ranking completo")
    args = parser.parse_args()

    players, stats = build(Path(args.landing).expanduser(), args.min_duels)
    ranked = sorted(
        (pid for pid in stats if stats[pid].duels >= args.min_duels),
        key=lambda pid: stats[pid].peak,
        reverse=True,
    )

    print(f"\n{'#':>3}  {'Piloto':<24}{'Años':<11}{'Duelos':>7}{'% gan.':>8}"
          f"{'Pico cons.':>12}  {'Cuándo':<9}{'Rating hoy':>11}{'RD':>6}")
    for i, pid in enumerate(ranked[: args.top], 1):
        s, p = stats[pid], players[pid]
        years = f"{s.first_season}-{s.last_season}"
        print(f"{i:>3}  {s.name:<24}{years:<11}{s.duels:>7}{100 * s.wins / s.duels:>7.0f}%"
              f"{s.peak:>12.0f}  {s.peak_label:<9}{p.rating:>11.0f}{p.rd:>6.0f}")

    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["rank", "driver_id", "name", "first_season", "last_season", "duels",
                        "wins", "peak_conservative", "peak_when", "rating", "rd", "vol"])
            for i, pid in enumerate(ranked, 1):
                s, p = stats[pid], players[pid]
                w.writerow([i, pid, s.name, s.first_season, s.last_season, s.duels, s.wins,
                            round(s.peak, 1), s.peak_label, round(p.rating, 1),
                            round(p.rd, 1), round(p.vol, 4)])
        print(f"\nRanking completo guardado en {args.csv}")


if __name__ == "__main__":
    main()
