"""Pruebas del motor de rating. Correr con: python3 -m pytest -q"""

import json

import pytest

import build_ranking
from glicko2 import Game, Player, update


def test_ejemplo_oficial_del_paper_de_glickman():
    """El ejemplo resuelto del paper: si coincide, la implementación es correcta."""
    player = Player(1500, 200, 0.06)
    games = [
        Game(Player(1400, 30), 1.0),
        Game(Player(1550, 100), 0.0),
        Game(Player(1700, 300), 0.0),
    ]
    new = update(player, games)
    assert new.rating == pytest.approx(1464.06, abs=0.01)
    assert new.rd == pytest.approx(151.52, abs=0.01)
    assert new.vol == pytest.approx(0.05999, abs=0.00001)


def test_hiato_aumenta_incertidumbre_sin_cambiar_rating():
    player = Player(1800, 50, 0.06)
    after = update(player, [])
    assert after.rating == 1800
    assert after.rd > 50


def test_rd_tiene_tope_en_350():
    assert update(Player(1500, 349.9, 0.06), []).rd == 350


def race(season, rnd, entries):
    """entries: (driverId, constructorId, position, status)."""
    results = [
        {"Driver": {"driverId": d, "givenName": d.title(), "familyName": "X"},
         "Constructor": {"constructorId": c}, "position": str(p), "status": s}
        for d, c, p, s in entries
    ]
    return {"MRData": {"RaceTable": {"Races": [
        {"season": str(season), "round": str(rnd), "Results": results}]}}}


def write(tmp_path, season, rnd, payload):
    path = tmp_path / f"season={season}/round={rnd:02d}/results.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload))


def test_duelos_solo_entre_companeros_que_terminaron():
    results = race(2024, 1, [
        ("ver", "redbull", 1, "Finished"),
        ("per", "redbull", 5, "+1 Lap"),
        ("ham", "mercedes", 2, "Finished"),
        ("rus", "mercedes", 18, "Engine"),
    ])["MRData"]["RaceTable"]["Races"][0]["Results"]
    assert build_ranking.teammate_duels(results) == [("ver", "per")]


def test_quien_le_gana_siempre_al_companero_sube(tmp_path):
    for rnd in range(1, 11):
        write(tmp_path, 2024, rnd, race(2024, rnd, [
            ("ver", "redbull", 1, "Finished"),
            ("per", "redbull", 4, "Finished"),
        ]))
    players, stats = build_ranking.build(tmp_path, min_duels=1)
    assert players["ver"].rating > 1500 > players["per"].rating
    assert stats["ver"].duels == stats["per"].duels == 10
    assert stats["ver"].wins == 10


def test_orden_cronologico_entre_temporadas(tmp_path):
    write(tmp_path, 2023, 22, race(2023, 22, [("a", "t", 1, "Finished"), ("b", "t", 2, "Finished")]))
    write(tmp_path, 2024, 1, race(2024, 1, [("a", "t", 2, "Finished"), ("b", "t", 1, "Finished")]))
    order = [(s, r) for s, r, _ in build_ranking.load_races(tmp_path)]
    assert order == [(2023, 22), (2024, 1)]
