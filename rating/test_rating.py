"""Pruebas del motor de rating. Correr con: python3 -m pytest -q"""

import json

import pytest

import build_ranking as br
from glicko2 import Game, Player, update


# --- Glicko-2 ---------------------------------------------------------------

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


def test_una_derrota_con_peso_menor_resta_menos():
    rival = Player(1500, 100)
    completa = update(Player(1500, 100), [Game(rival, 0.0, 1.0)])
    media = update(Player(1500, 100), [Game(rival, 0.0, 0.5)])
    assert completa.rating < media.rating < 1500


def test_partidas_con_peso_cero_no_cuentan():
    assert update(Player(1600, 80), [Game(Player(), 1.0, 0.0)]) == update(Player(1600, 80), [])


# --- Matriz de duelos (ADR-004) ---------------------------------------------

TERMINO = br.Clase("terminado", "duelo", 0, "jolpica")
ERROR = br.Clase("error_piloto", "derrota", 1.0, "jolpica")
COLISION = br.Clase("colision", "derrota_ponderada", 0.5, "jolpica")
MECANICO = br.Clase("mecanico", "excluir_penaliza_constructor", 0, "jolpica")


def r(driver, pos, laps, clase):
    return br.Resultado(driver, pos, laps, clase)


def test_ambos_terminan_gana_quien_llega_adelante():
    assert br.duelo(r("a", 5, 58, TERMINO), r("b", 2, 58, TERMINO), 58) == ("b", "a", 1.0)


def test_error_del_piloto_es_derrota_completa_y_colision_media():
    assert br.duelo(r("a", 3, 58, TERMINO), r("b", 18, 20, ERROR), 58) == ("a", "b", 1.0)
    assert br.duelo(r("a", 3, 58, TERMINO), r("b", 18, 20, COLISION), 58) == ("a", "b", 0.5)


def test_falla_mecanica_no_genera_duelo():
    assert br.duelo(r("a", 3, 58, TERMINO), r("b", 18, 20, MECANICO), 58) is None


def test_ambos_abandonan_prorrateo_por_vueltas():
    """A choca en la vuelta 5 y B en la 50, en una carrera de 57: gana B con 45/57."""
    g, p, peso = br.duelo(r("a", 19, 5, ERROR), r("b", 15, 50, ERROR), 57)
    assert (g, p) == ("b", "a")
    assert peso == pytest.approx(45 / 57)


def test_ambos_abandonan_sin_duelo_si_el_de_menos_vueltas_tuvo_falla_mecanica():
    """Australia 2024: Russell (error, vuelta 56) vs. Hamilton (motor, vuelta 15)."""
    assert br.duelo(r("russell", 17, 56, ERROR), r("hamilton", 19, 15, MECANICO), 58) is None


def test_resultado_en_cuarentena_no_genera_duelo():
    assert br.duelo(r("a", 1, 58, TERMINO), r("b", 2, 58, None), 58) is None


# --- Clasificador (ADR-005) -------------------------------------------------

@pytest.fixture
def referencia(tmp_path):
    ref = tmp_path / "reference"
    ref.mkdir()
    (ref / "status_categoria.csv").write_text(
        "status,coincidencia,status_normalizado,desde_temporada,hasta_temporada,categoria,tratamiento,peso_derrota,nota\n"
        "Finished,exacta,Finished,,,terminado,duelo,,\n"
        "Retired,exacta,Retired,,,no_atribuible,excluir,,\n"
        "Stalled,exacta,Stalled,,2013,error_piloto,derrota,1.0,\n"
        "Stalled,exacta,Stalled,2014,,mecanico,excluir_penaliza_constructor,,\n")
    (ref / "wikipedia_causa_categoria.csv").write_text(
        "causa,categoria,tratamiento,peso_derrota,revisar,nota\n"
        "collision,colision,derrota_ponderada,0.5,,\n"
        "collision damage,colision,derrota_ponderada,0.5,,\n"
        "undertray,mecanico,excluir_penaliza_constructor,,sí,\n")
    (ref / "abandonos_revisados.csv").write_text(
        "season,round,carrera,driver_id,causa_fuente,categoria,tratamiento,peso_derrota,evidencia,revisado_por\n"
        "2023,16,Japanese Grand Prix,albon,Undertray,victima,excluir,,onboard,Joaco Mora\n")
    causas = tmp_path / "causas.csv"
    causas.write_text(
        "season,round,number,driver_id,jolpica_status,jolpica_laps,wiki_driver,wiki_laps,wiki_time_retired,wiki_title,wiki_revid\n"
        "2023,16,23,albon,Retired,10,Alexander Albon,10,Undertray,T,1\n"
        "2023,16,77,bottas,Retired,10,Valtteri Bottas,10,Collision Damage,T,1\n"
        "2023,16,2,sargeant,Retired,10,Logan Sargeant,10,Warp drive,T,1\n"
        "2023,16,1,max_verstappen,Finished,53,Max Verstappen,53,1:30:58.421,T,1\n")
    return br.Clasificador(ref, causas)


def test_precedencia_revision_sobre_wikipedia(referencia):
    clase = referencia.clasificar(2023, 16, "albon", "Retired")
    assert (clase.categoria, clase.fuente) == ("victima", "revision")


def test_wikipedia_sin_distinguir_mayusculas(referencia):
    clase = referencia.clasificar(2023, 16, "bottas", "Retired")
    assert (clase.categoria, clase.fuente, clase.peso) == ("colision", "wikipedia", 0.5)


def test_causa_sin_regla_va_a_cuarentena(referencia):
    assert referencia.clasificar(2023, 16, "sargeant", "Retired") is None
    assert referencia.cuarentena["wikipedia: Warp drive"] == 1


def test_un_tiempo_de_wikipedia_no_es_causa(referencia):
    clase = referencia.clasificar(2023, 16, "max_verstappen", "Finished")
    assert (clase.categoria, clase.fuente) == ("terminado", "jolpica")


def test_vigencia_por_temporada(referencia):
    assert referencia.clasificar(2010, 5, "x", "Stalled").categoria == "error_piloto"
    assert referencia.clasificar(2020, 5, "x", "Stalled").categoria == "mecanico"


def test_status_desconocido_va_a_cuarentena(referencia):
    assert referencia.clasificar(2010, 5, "x", "Abducted") is None


# --- Clasificación (ADR-006) ------------------------------------------------

def resultado(driver, team, pos, grid, status="Finished", laps=58):
    return {"Driver": {"driverId": driver, "givenName": driver.title(), "familyName": "X"},
            "Constructor": {"constructorId": team}, "position": str(pos), "grid": str(grid),
            "status": status, "laps": str(laps)}


def test_clasificacion_real_manda_sobre_la_parrilla():
    """Pole con sanción: clasificó primero, largó undécimo."""
    race = {"Results": [resultado("a", "t", 1, 11), resultado("b", "t", 2, 2)]}
    qualifying = [{"Driver": {"driverId": "a"}, "position": "1"},
                  {"Driver": {"driverId": "b"}, "position": "2"}]
    fuentes = br.Counter()
    assert br.duelos_clasificacion(race, qualifying, fuentes) == [("a", "b", 1.0)]
    assert fuentes == {"clasificacion": 1}


def test_parrilla_como_sustituto_y_sin_largadas_desde_pits():
    race = {"Results": [resultado("a", "t", 1, 3), resultado("b", "t", 2, 1), resultado("c", "t", 3, 0)]}
    fuentes = br.Counter()
    assert br.duelos_clasificacion(race, None, fuentes) == [("b", "a", 1.0)]
    assert fuentes == {"parrilla": 1}


# --- Proceso completo -------------------------------------------------------

def escribir(tmp_path, season, rnd, results, circuit="monza"):
    path = tmp_path / f"season={season}/round={rnd:02d}/results.json"
    path.parent.mkdir(parents=True)
    race = {"season": str(season), "round": str(rnd), "Circuit": {"circuitId": circuit}, "Results": results}
    path.write_text(json.dumps({"MRData": {"RaceTable": {"Races": [race]}}}))


def test_quien_le_gana_siempre_al_companero_sube(tmp_path):
    for rnd in range(1, 11):
        escribir(tmp_path, 2024, rnd, [resultado("ver", "redbull", 1, 1), resultado("per", "redbull", 4, 2)])
    out = br.build(tmp_path, min_duels=1)
    for nombre in ("v0", "v1", "clasificacion"):
        pista = out["pistas"][nombre]
        assert pista.players["ver"].rating > 1500 > pista.players["per"].rating
        assert pista.stats["ver"].wins == 10


def test_la_v1_penaliza_el_error_que_la_v0_ignora(tmp_path):
    for rnd in range(1, 6):
        escribir(tmp_path, 2010, rnd, [resultado("a", "t", 5, 1),
                                       resultado("b", "t", 20, 2, status="Accident", laps=3)])
    out = br.build(tmp_path, min_duels=1)
    assert out["pistas"]["v0"].stats["a"].duels == 0
    assert out["pistas"]["v1"].stats["a"].wins == 5


def test_indianapolis_1950_1960_queda_excluida(tmp_path):
    escribir(tmp_path, 1955, 2, [resultado("a", "t", 1, 1), resultado("b", "t", 2, 2)], circuit="indianapolis")
    out = br.build(tmp_path, min_duels=1)
    assert out["resumen"]["indianapolis_excluidas"] == 1
    assert out["resumen"]["carreras"] == 0


def test_autos_compartidos_y_piloto_repetido_no_generan_duelos(tmp_path):
    """Bélgica 1953: Fangio figura dos veces (manejó dos autos) y compartió el auto 6 con otro piloto."""
    results = [
        dict(resultado("fangio", "maserati", 1, 1), number="4"),
        dict(resultado("gonzalez", "maserati", 2, 2), number="6"),
        dict(resultado("fangio", "maserati", 3, 3), number="6"),
        dict(resultado("marimon", "maserati", 4, 4), number="8"),
    ]
    escribir(tmp_path, 1953, 4, results)
    out = br.build(tmp_path, min_duels=1)
    # El auto 6 queda fuera: solo hay un duelo válido, Fangio (auto 4) contra Marimón (auto 8).
    assert out["resumen"]["resultados_en_autos_compartidos"] == 2
    for nombre in ("v0", "v1", "clasificacion"):
        stats = out["pistas"][nombre].stats
        assert stats["fangio"].duels == 1
        assert stats["gonzalez"].duels == 0
