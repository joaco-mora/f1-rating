# Setup del proyecto F1 Rating

Checklist para dejar todo listo. Marca cada casilla al terminar.
Tiempo estimado: 1,5 a 2 horas la primera vez.

---

## Bloque 1: herramientas locales (~30 min)

- [ ] **Python 3.12 o superior.** En una terminal: `python --version`
      (en Mac puede ser `python3 --version`). Si falta o es menor: python.org/downloads.
- [ ] **Git.** `git --version`. Si falta: git-scm.com/downloads.
- [ ] **Configura tu identidad en Git** (una sola vez por computador):
      ```bash
      git config --global user.name "Tu Nombre"
      git config --global user.email "tu-correo@ejemplo.com"
      ```
- [ ] **Google Cloud CLI (gcloud).** Instálalo desde cloud.google.com/sdk/docs/install.
      Verifica con `gcloud --version`.
- [ ] **Extensiones de VS Code:** Python (Microsoft) y Pylance. Opcional: GitLens.

---

## Bloque 2: repositorio en GitHub (~15 min)

- [ ] En github.com crea un repo nuevo llamado `f1-rating`, público, **sin** README
      (ya tienes uno).
- [ ] Descomprime `f1-rating.zip`, abre una terminal dentro de la carpeta `f1-rating` y:
      ```bash
      git init
      git add .
      git commit -m "Esqueleto inicial: ingestor y ADRs"
      git branch -M main
      git remote add origin https://github.com/TU_USUARIO/f1-rating.git
      git push -u origin main
      ```
- [ ] Abre la carpeta en VS Code: `code .`

---

## Bloque 3: prueba local (~15 min)

Sigue la sección "Ingestor: correrlo en tu computador" del README.

- [ ] `pytest -q` muestra 5 pruebas pasadas.
- [ ] `python main.py --seasons 2024` descarga 24 rondas en `landing/`.
- [ ] Una segunda ejecución dice `descargada: 0`.
- [ ] **Revisión de código:** lee `main.py` de arriba abajo y anota en un papel
      cualquier línea que no entiendas. Esas dudas son la agenda de nuestra próxima sesión.

---

## Bloque 4: proyecto GCP y límites de gasto (~30 min)

- [ ] Inicia sesión en la CLI: `gcloud auth login`
- [ ] Crea el proyecto (el ID debe ser único en todo GCP; agrega un sufijo):
      ```bash
      gcloud projects create f1-rating-TUSUFIJO --name="F1 Rating"
      gcloud config set project f1-rating-TUSUFIJO
      ```
- [ ] **Vincula una cuenta de facturación** al proyecto en la consola web
      (Billing → Link a billing account). Sin facturación no se pueden habilitar
      la mayoría de los servicios, aunque el uso quede dentro de la capa gratuita.
- [ ] **Presupuesto con alertas:** consola → Billing → Budgets & alerts → Create budget.
      Alcance: solo este proyecto. Monto: USD 5. Alertas al 50%, 90% y 100%.

> ⚠️ **Importante:** un presupuesto en GCP **avisa, no corta**. Si algo se descontrola,
> te llega un correo pero el gasto sigue. Para un tope real hay dos capas extra:
>
> - **Cuota de BigQuery:** consola → IAM & Admin → Quotas, busca
>   "Query usage per day" y fija un límite bajo (por ejemplo, 100 GiB/día).
>   Esa sí es un corte duro: las consultas fallan al llegar al límite.
> - **Corte automático de facturación:** el presupuesto publica en Pub/Sub y una
>   función desactiva la facturación del proyecto. Lo armaremos más adelante como
>   ejercicio: es tu primer sistema orientado a eventos real, y uno muy útil.

- [ ] Habilita las APIs que vamos a usar:
      ```bash
      gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
        artifactregistry.googleapis.com storage.googleapis.com \
        cloudscheduler.googleapis.com eventarc.googleapis.com \
        pubsub.googleapis.com bigquery.googleapis.com
      ```

---

## Bloque 5: primer despliegue del ingestor (~20 min)

Región: `us-central1`. Tiene todos los servicios que usaremos y suele ser la más
barata; la latencia no importa para un proceso batch.

- [ ] Crea el bucket de aterrizaje (nombre único global):
      ```bash
      gcloud storage buckets create gs://f1-rating-landing-TUSUFIJO \
        --location=us-central1 --uniform-bucket-level-access
      ```
- [ ] Crea una service account solo para el ingestor, con permisos mínimos sobre ese bucket:
      ```bash
      gcloud iam service-accounts create f1-ingestor --display-name="F1 ingestor"

      SA=f1-ingestor@f1-rating-TUSUFIJO.iam.gserviceaccount.com

      gcloud storage buckets add-iam-policy-binding gs://f1-rating-landing-TUSUFIJO \
        --member=serviceAccount:$SA --role=roles/storage.objectCreator
      gcloud storage buckets add-iam-policy-binding gs://f1-rating-landing-TUSUFIJO \
        --member=serviceAccount:$SA --role=roles/storage.objectViewer
      ```
      *Por qué dos roles:* `objectCreator` permite crear pero no leer; el ingestor
      necesita `objectViewer` para revisar si una ronda ya existe. Ninguno permite borrar.
- [ ] Da permiso de construcción a la cuenta que usa Cloud Build:
      ```bash
      PROJECT_NUMBER=$(gcloud projects describe f1-rating-TUSUFIJO --format="value(projectNumber)")
      gcloud projects add-iam-policy-binding f1-rating-TUSUFIJO \
        --member=serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com \
        --role=roles/run.builder
      ```
      *Por qué:* Cloud Build construye la imagen con la cuenta por defecto de Compute Engine,
      que en proyectos nuevos ya no recibe el rol Editor. Sin `roles/run.builder`, el deploy
      falla con `403 ... storage.objects.get`. El permiso tarda ~2 minutos en propagarse.
- [ ] Despliega el job desde la carpeta `ingestor` (Cloud Build construye la imagen con el Dockerfile):
      ```bash
      cd ingestor
      gcloud run jobs deploy f1-ingestor --source . --region=us-central1 \
        --service-account=$SA \
        --args=--seasons,2026,--backend,gcs,--dest,f1-rating-landing-TUSUFIJO \
        --task-timeout=30m --max-retries=1
      ```
- [ ] Ejecútalo y mira los logs:
      ```bash
      gcloud run jobs execute f1-ingestor --region=us-central1 --wait
      gcloud storage ls -r gs://f1-rating-landing-TUSUFIJO
      ```

🏁 **Prueba de fuego del fin de semana:** después de la carrera, cuando Jolpica publique
los resultados, vuelve a ejecutar el job. Solo debería descargar la ronda nueva.

---

## Si algo falla
Copia el error completo y tráelo a la conversación. Los errores de permisos (403)
son normales la primera vez: son parte del aprendizaje de IAM.
