# F1 Rating

Rating histórico de pilotos de F1 con Glicko-2, sobre una arquitectura orientada a
eventos en Google Cloud. Proyecto personal de aprendizaje.

La pregunta de fondo: **¿cómo medir al piloto y no al auto?** El único enfrentamiento
con igualdad de máquina es contra el compañero de equipo, y de ahí parte el modelo.

- Decisiones de modelado: [ADR-001](docs/adr/ADR-001-modelo-rating.md)
- Arquitectura en GCP: [ADR-003](docs/adr/ADR-003-arquitectura-gcp.md)
- Puesta en marcha (local, GitHub y GCP): [SETUP.md](SETUP.md)
- Datos: [Jolpica-F1](https://github.com/jolpica/jolpica-f1), sucesor de la API de Ergast.

## Estado

| Componente | Estado |
|---|---|
| Ingestor (Cloud Run Job + Cloud Scheduler) | ✅ En producción: busca resultados nuevos cada 6 h los domingos y lunes |
| Backfill histórico 2000–2025 | ⏳ 497 de ~503 rondas; faltan las últimas de 2025 |
| Motor Glicko-2 + Modelo A v0 | ✅ Corre local sobre los JSON crudos |
| Loader + QA (Eventarc → BigQuery) | ⏳ Siguiente |
| Rating engine orientado a eventos (Pub/Sub) | ⏳ Pendiente |
| Modelo B (parrilla ajustada por constructor) | ⏳ Pendiente |

## Estructura

```
f1-rating/
├── docs/adr/     Decisiones de arquitectura
├── ingestor/     Descarga resultados desde Jolpica (Cloud Run Job)
└── rating/       Motor Glicko-2 y construcción del ranking
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
- Un duelo cuenta solo si ambos compañeros terminaron. Todos los abandonos se
  excluyen; la atribución mecánico/error/colisión llega con el loader.

**Sesgos conocidos del Modelo A**, observados en el primer ranking:
- Ganarle a un compañero novato (rating inicial 1500) pesa más de lo que debería.
- Cada equipo es una "isla": dominar a un compañero que casi no se conecta con el
  resto de la parrilla infla el rating. El Modelo B existe para corregir esto.

## Roadmap

1. ~~Ingestor local~~ ✅
2. ~~Ingestor en Cloud Run + Scheduler~~ ✅
3. Backfill 2000–2025 
4. ~~Motor Glicko-2 y Modelo A v0~~ ✅
5. Loader + QA con Eventarc: carga en BigQuery, clasificación de abandonos y
   control de completitud (rondas por temporada vs. calendario)
6. Rating engine con Pub/Sub
7. Modelo B y rating de clasificación
8. Dashboard en Looker Studio
