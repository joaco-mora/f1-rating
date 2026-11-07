"""Pruebas del extractor sin tocar la red. Correr con: python3 -m pytest -q

El HTML de ejemplo imita la estructura de un artículo de GP con sprint:
la tabla del sprint tiene las mismas columnas que la de la carrera, y el
extractor tiene que elegir la correcta.
"""

import json

import wikipedia_causes as wc

TABLA = """
<table class="wikitable">
<tr><th>Pos.</th><th>No.</th><th>Driver</th><th>Constructor</th><th>Laps<sup>a</sup></th>
    <th>Time/Retired</th><th>Grid</th><th>Points</th></tr>
{filas}
<tr><th colspan="8">Fastest lap: Charles Leclerc</th></tr>
</table>
"""

HTML = f"""
<div class="mw-heading mw-heading3"><h3 id="Sprint">Sprint</h3></div>
{TABLA.format(filas='<tr><td>1</td><td>1</td><td>Max Verstappen</td><td>Red Bull</td><td>19</td><td>30:00.000</td><td>1</td><td>8</td></tr>')}
<div class="mw-heading mw-heading3"><h3 id="Race">Race</h3></div>
{TABLA.format(filas='''
<tr><td>1</td><td>55</td><td>Carlos Sainz Jr.</td><td>Ferrari</td><td>58</td><td>1:20:26.843</td><td>2</td><td>25</td></tr>
<tr><td>17<sup>[d]</sup></td><td>63</td><td>George Russell</td><td>Mercedes</td><td>56</td><td>Accident</td><td>7</td><td></td></tr>
<tr><td>Ret</td><td>44</td><td>Lewis Hamilton</td><td>Mercedes</td><td>15</td><td>Power unit<sup>[e]</sup></td><td>11</td><td></td></tr>
<tr><td>Ret</td><td>1</td><td>Max Verstappen</td><td>Red Bull</td><td>3</td><td>Brakes<sup>1</sup></td><td>1</td><td></td></tr>
''')}
"""


def test_elige_la_tabla_de_la_carrera_y_no_la_del_sprint():
    rows = wc.parse_rows(wc.find_race_table(HTML))
    assert [r["number"] for r in rows] == ["55", "63", "44", "1"]


def test_limpia_notas_al_pie_y_omite_filas_de_pie_de_tabla():
    rows = {r["number"]: r for r in wc.parse_rows(wc.find_race_table(HTML))}
    assert rows["44"]["time_retired"] == "Power unit"
    assert rows["63"] == {"number": "63", "driver": "George Russell", "laps": "56",
                          "time_retired": "Accident"}


def test_sin_seccion_race_devuelve_none():
    assert wc.find_race_table("<h3>Qualifying</h3><table><tr><th>Q1</th></tr></table>") is None


def test_distingue_causas_de_tiempos_y_genericos():
    assert wc.has_cause("Brakes")
    assert wc.has_cause("Power unit")
    assert not wc.has_cause("1:20:26.843")
    assert not wc.has_cause("+2.366")
    assert not wc.has_cause("+1 lap")
    assert not wc.has_cause("Retired")
    assert not wc.has_cause("")


def test_titulo_desde_la_url_de_jolpica():
    assert wc.page_title("https://en.wikipedia.org/wiki/2024_S%C3%A3o_Paulo_Grand_Prix") \
        == "2024_São_Paulo_Grand_Prix"


def test_proceso_completo_con_cache(tmp_path):
    """Con la página en caché, el proceso corre completo sin red."""
    landing = tmp_path / "landing" / "season=2024" / "round=03"
    landing.mkdir(parents=True)
    results = [
        {"number": "55", "status": "Finished", "laps": "58", "Driver": {"driverId": "sainz"}},
        {"number": "63", "status": "Retired", "laps": "56", "Driver": {"driverId": "russell"}},
        {"number": "44", "status": "Retired", "laps": "15", "Driver": {"driverId": "hamilton"}},
        {"number": "1", "status": "Retired", "laps": "3", "Driver": {"driverId": "max_verstappen"}},
    ]
    race = {"season": "2024", "round": "3", "url": "https://en.wikipedia.org/wiki/2024_Australian_Grand_Prix",
            "Results": results}
    (landing / "results.json").write_text(json.dumps({"MRData": {"RaceTable": {"Races": [race]}}}))
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "2024_Australian_Grand_Prix.json").write_text(json.dumps({"html": HTML, "revid": 123}))

    out = tmp_path / "causas.csv"
    stats = wc.run(tmp_path / "landing", [2024], out, cache)

    assert stats["retired"] == 3
    assert stats["retired_con_causa"] == 3
    assert stats["sin_cruce"] == 0
    assert stats["vueltas_distintas"] == 0
    assert "Power unit" in out.read_text()


def test_notas_al_pie_sin_corchetes_no_ensucian_encabezados_ni_causas():
    """Italia 2023: el encabezado 'Laps<sup>a</sup>' se leía 'Lapsa' y la tabla no se reconocía."""
    rows = {r["number"]: r for r in wc.parse_rows(wc.find_race_table(HTML))}
    assert rows["1"]["time_retired"] == "Brakes"


def _carrera(tmp_path, url, results):
    landing = tmp_path / "landing" / "season=2026" / "round=07"
    landing.mkdir(parents=True)
    race = {"season": "2026", "round": "7", "url": url, "Results": results}
    (landing / "results.json").write_text(json.dumps({"MRData": {"RaceTable": {"Races": [race]}}}))
    return tmp_path / "landing"


def test_override_corrige_el_titulo_de_jolpica(tmp_path):
    results = [{"number": "44", "status": "Retired", "laps": "15", "Driver": {"driverId": "hamilton"}}]
    landing = _carrera(tmp_path, "https://en.wikipedia.org/wiki/2026_Barcelona-Catalunya", results)
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "Titulo_Correcto.json").write_text(json.dumps({"html": HTML, "revid": 1}))
    overrides = tmp_path / "overrides.csv"
    overrides.write_text("season,round,wiki_title,nota\n2026,7,Titulo_Correcto,URL mala en Jolpica\n")

    stats = wc.run(landing, [2026], tmp_path / "out.csv", cache, overrides)
    assert stats["carreras_sin_pagina"] == 0
    assert stats["retired_con_causa"] == 1


def test_retired_de_carreras_fallidas_cuentan_en_el_denominador(tmp_path):
    results = [{"number": "44", "status": "Retired", "laps": "15", "Driver": {"driverId": "hamilton"}},
               {"number": "1", "status": "Retired", "laps": "3", "Driver": {"driverId": "max_verstappen"}}]
    landing = _carrera(tmp_path, "https://en.wikipedia.org/wiki/Sin_Tabla", results)
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "Sin_Tabla.json").write_text(json.dumps({"html": "<h2>Race</h2><p>Sin tabla</p>", "revid": 1}))

    stats = wc.run(landing, [2026], tmp_path / "out.csv", cache, tmp_path / "no_existe.csv")
    assert stats["retired"] == 2
    assert stats["retired_sin_procesar"] == 2
    assert stats["retired_con_causa"] == 0


def test_descalificados_con_0_vueltas_no_cuentan_como_inconsistencia(tmp_path):
    """Jolpica pone 0 vueltas a un descalificado; Wikipedia, las que dio (Hülkenberg, Brasil 2024)."""
    results = [{"number": "44", "status": "Disqualified", "laps": "0", "Driver": {"driverId": "hamilton"}},
               {"number": "1", "status": "Finished", "laps": "2", "Driver": {"driverId": "max_verstappen"}}]
    landing = _carrera(tmp_path, "https://en.wikipedia.org/wiki/Con_DSQ", results)
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "Con_DSQ.json").write_text(json.dumps({"html": HTML, "revid": 1}))

    stats = wc.run(landing, [2026], tmp_path / "out.csv", cache, tmp_path / "no_existe.csv")
    assert stats["vueltas_distintas_dsq"] == 1
    assert stats["vueltas_distintas"] == 1   # Verstappen: 2 en Jolpica vs. 3 en el HTML de ejemplo
