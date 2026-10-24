# F1 Rating

Rating histórico de pilotos de F1 con Glicko-2, sobre una arquitectura orientada a
eventos en Google Cloud. Proyecto personal de aprendizaje.

- Decisiones de modelado: [ADR-001](docs/adr/ADR-001-modelo-rating.md)
- Arquitectura en GCP: [ADR-003](docs/adr/ADR-003-arquitectura-gcp.md)
- Puesta en marcha (local, GitHub y GCP): [SETUP.md](SETUP.md)
- Datos: [Jolpica-F1](https://github.com/jolpica/jolpica-f1), sucesor de la API de Ergast.

## Estructura

```
f1-rating/
├── docs/adr/          Decisiones de arquitectura
└── ingestor/          Descarga resultados desde Jolpica (Cloud Run Job)
```

## Ingestor: correrlo en tu computador

```bash
cd ingestor
python -m venv .venv
source .venv/bin/activate        # en Windows: .venv\Scripts\activate
pip install -r requirements.txt

pytest -q                        # pruebas sin red, con una API falsa

python main.py --seasons 2024 --backend local --dest ./landing
```

Resultado esperado: una carpeta `landing/season=2024/round=NN/` por carrera, cada una
con `qualifying.json` y `results.json`. Si lo corres de nuevo, el resumen debe decir
`descargada: 0` y `ya_existia: 24`: el ingestor es idempotente.

Para el backfill del MVP (`--seasons 2000-2024`) se necesitan más llamadas que el
presupuesto por ejecución. Córrelo varias veces con al menos una hora entre una y
otra; cada ejecución sigue donde quedó la anterior.

## Próximos pasos
1. Ingestor en local ✅
2. Desplegar el ingestor como Cloud Run Job con destino en GCS
3. Loader + QA disparado por Eventarc
4. Rating engine con Pub/Sub
