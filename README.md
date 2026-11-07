# F1 Rating

Autor: Joaco Mora · [github.com/joaco-mora](https://github.com/joaco-mora)

Rating histórico de pilotos de F1 con Glicko-2, sobre una arquitectura orientada a
eventos en Google Cloud. Proyecto personal de aprendizaje.

La pregunta de fondo: **¿cómo medir al piloto y no al auto?** El único enfrentamiento
con igualdad de máquina es contra el compañero de equipo, y de ahí parte el modelo.

## Documentación

| Documento | Tema |
|---|---|
| [ADR-001](docs/adr/ADR-001-modelo-rating.md) | Modelo de rating: Glicko-2, duelos, tratamiento de hiatos y edad |
| [ADR-003](docs/adr/ADR-003-arquitectura-gcp.md) | Arquitectura orientada a eventos en GCP |
| [ADR-004](docs/adr/ADR-004-clasificacion-abandonos.md) | Clasificación de abandonos y controles de calidad |
| [ADR-005](docs/adr/ADR-005-causas-de-abandono.md) | Causas de abandono desde Wikipedia |
| [SETUP.md](SETUP.md) | Puesta en marcha: computador local, GitHub y GCP |

Datos: [Jolpica-F1](https://github.com/jolpica/jolpica-f1), sucesor de la API de Ergast,
y [Wikipedia](https://en.wikipedia.org) para las causas de abandono.

## Estado

| Componente | Estado |
|---|---|
| Ingestor (Cloud Run Job + Cloud Scheduler) | ✅ En producción: busca resultados nuevos cada 6 h los domingos y lunes |
| Backfill 2000–2025 | ✅ 503 rondas |
| Backfill 1950–1999 | ⏳ En curso |
| Motor Glicko-2 + Modelo A v0 | ✅ Corre local sobre los JSON crudos |
| Clasificación de abandonos (ADR-004) | ✅ Tabla de referencia y controles de calidad |
| Causas de abandono desde Wikipedia (ADR-005) | ✅ 100% de los `Retired` 2023–2026 con causa |
| Integración de las causas en el rating | ⏳ Siguiente |
| Loader + QA (Eventarc → BigQuery) | ⏳ Pendiente |
| Rating engine orientado a eventos (Pub/Sub) | ⏳ Pendiente |
| Modelo B (parrilla ajustada por constructor) | ⏳ Pendiente |

## Estructura

```
f1-rating/
├── docs/adr/     Decisiones de arquitectura y de modelado
├── ingestor/     Descarga resultados desde Jolpica (Cloud Run Job)
├── rating/       Motor Glicko-2 y construcción del ranking
├── enrichment/   Enriquecimiento con otras fuentes (causas de abandono desde Wikipedia)
└── reference/    Tablas de referencia versionadas y controles de calidad
```

## Ingestor: correrlo en tu computador

```bash
cd ingestor
python3 -m venv .venv
source .venv/bin/activate
pip install requests pytest

pytest -q                                   # pruebas sin red, con una API falsa
python main.py --seasons 2024 --dest ./landing
```

Resultado esperado: una carpeta `landing/season=2024/round=NN/` por carrera, con
`qualifying.json` y `results.json`. Una segunda ejecución debe decir `descargada: 0`:
el ingestor es idempotente.

## Ranking: calcularlo

El motor lee la carpeta de datos crudos. Desde Cloud Shell, primero se sincroniza
el bucket:

```bash
mkdir -p ~/landing && gcloud storage rsync -r gs://$BUCKET ~/landing
cd rating
python3 -m pytest -q
python3 build_ranking.py --landing ~/landing --top 20
```

Opciones: `--min-duels` (mínimo de duelos para entrar al ranking, por defecto 30)
y `--csv` (guarda el ranking completo).

**Cómo leer la tabla:** se ordena por el **pico del rating conservador**
(rating − 2×RD): lo que valió el piloto en su mejor momento, con ~95% de confianza.
Así, un novato con pocas victorias no aparece arriba mientras su incertidumbre sea alta.

**Simplificaciones de la v0** respecto del ADR-001:
- Solo carrera; la clasificación queda para la v1.
- Un duelo cuenta solo si ambos compañeros terminaron. La clasificación de abandonos
  de los ADR-004 y ADR-005 todavía no está integrada al cálculo.

**Sesgos conocidos del Modelo A**, observados en el primer ranking:
- Ganarle a un compañero novato (rating inicial 1500) pesa más de lo que debería.
- Cada equipo es una "isla": dominar a un compañero que casi no se conecta con el
  resto de la parrilla infla el rating. El Modelo B existe para corregir esto.

## Calidad de datos y causas de abandono

```bash
# Controles del ADR-004: validez de la tabla, cobertura y deriva por temporada
python3 reference/check_status.py --landing ~/landing

# Causas de abandono desde Wikipedia (ADR-005)
pip install beautifulsoup4
python3 enrichment/wikipedia_causes.py --landing ~/landing --seasons 2023-2026 \
  --out ~/causas.csv --cache ~/wiki_cache
```

| Tabla de referencia | Contenido |
|---|---|
| `reference/status_categoria.csv` | Clasificación de cada status de Jolpica, con vigencia por temporada |
| `reference/wikipedia_causa_categoria.csv` | Regla general por causa de abandono de Wikipedia |
| `reference/abandonos_revisados.csv` | Revisiones caso a caso con evidencia; mandan sobre las reglas generales |
| `reference/wikipedia_overrides.csv` | Títulos de Wikipedia corregidos cuando la URL de Jolpica es incorrecta |

## Preguntas que queremos responder

- ¿Qué tan bien coincide el rating con los campeonatos del mundo, y dónde discrepa?
- ¿Cuáles fueron los puntos de inflexión de cada campeonato?
- ¿Qué pilotos protagonizan las mejores remontadas?
- ¿Cuándo trajo un equipo una mejora, y cómo se refleja en tiempos y rendimiento?
- ¿Qué pilotos aprovechan mejor las mejoras del auto, y qué tan sensibles son a los cambios?

## Roadmap

1. ~~Ingestor local~~ ✅
2. ~~Ingestor en Cloud Run + Scheduler~~ ✅
3. ~~Backfill 2000–2025~~ ✅
4. ~~Motor Glicko-2 y Modelo A v0~~ ✅
5. ~~Clasificación de abandonos y causas desde Wikipedia (ADR-004 y ADR-005)~~ ✅
6. Backfill 1950–1999
7. Integrar la clasificación de abandonos al rating y medir el ranking antes y después
8. Loader + QA con Eventarc: carga en BigQuery, cuarentena y controles automáticos
9. Rating engine con Pub/Sub
10. Modelo B y rating de clasificación
11. Datos de vueltas y sectores para las preguntas analíticas
12. Dashboard en Looker Studio

## Licencias

- Datos de resultados: [Jolpica-F1](https://github.com/jolpica/jolpica-f1).
- Las causas de abandono extraídas de Wikipedia se publican bajo
  [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), con atribución a
  Wikipedia como fuente (ADR-005).
