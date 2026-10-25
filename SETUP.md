# Setup del proyecto F1 Rating

Receta para reproducir el entorno desde cero. Marca cada casilla al terminar.
Tiempo estimado: 2 a 3 horas la primera vez.

**Dónde se trabaja (modelo híbrido):**

| Lugar | Para qué |
|---|---|
| Computador local (VS Code + Python + Git) | Editar código, correr pruebas, commit y push |
| **Cloud Shell** (navegador) | Todo lo de GCP: gcloud, deploys, permisos |
| GitHub | Puente entre ambos: fuente única de verdad del código |

Así no hace falta instalar gcloud ni Docker en el computador local: Cloud Shell trae
gcloud ya autenticado, y las imágenes las construye Cloud Build en la nube.

---

## Bloque 1: herramientas locales (~30 min)

- [ ] **Python 3.12 o superior**, desde python.org/downloads. Verifica con
      `python3 --version`.
      - En Mac, al terminar la instalación, abre la carpeta de Python en Aplicaciones
        y ejecuta **`Install Certificates.command`**. Sin eso, Python no puede
        conectarse por HTTPS y el ingestor falla con un error de certificado SSL.
- [ ] **Git.** Verifica con `git --version`.
      - Mac: `xcode-select --install` instala las Command Line Tools, que traen Git.
        En Mac Intel antiguos conviene evitar Homebrew: ya no publica paquetes
        precompilados para Intel y compila todo desde cero.
      - Windows: git-scm.com/downloads; en el instalador, elige VS Code como editor y
        `main` como nombre de la rama inicial.
- [ ] **Configura Git** (una sola vez por computador):
      ```bash
      git config --global user.name "Tu Nombre"
      git config --global user.email "ID+usuario@users.noreply.github.com"
      git config --global init.defaultBranch main
      ```
      *Por qué el correo noreply:* el repo es público y cada commit expone el correo
      del autor. GitHub entrega una dirección privada en Settings → Emails →
      "Keep my email addresses private".
- [ ] **Extensiones de VS Code:** Python (Microsoft) y Pylance. Opcional: GitLens.

---

## Bloque 2: repositorio en GitHub (~15 min)

- [ ] Crea una cuenta en github.com/signup **con correo y contraseña** (no con
      "Continue with Apple/Google": esas cuentas no tienen contraseña propia y
      complican activar la verificación en dos pasos).
- [ ] Activa la verificación en dos pasos (Settings → Password and authentication)
      y guarda los códigos de recuperación.
- [ ] Crea un repo `f1-rating`, público, **sin** README, .gitignore ni licencia.
- [ ] Dentro de la carpeta del proyecto:
      ```bash
      git init
      git add .
      git commit -m "Esqueleto inicial: ingestor y ADRs"
      git branch -M main
      git remote add origin https://github.com/TU_USUARIO/f1-rating.git
      git push -u origin main
      ```
      En la terminal de VS Code, el push abre el navegador para autenticarte.
      Si la terminal pide usuario y contraseña, la contraseña de GitHub no sirve:
      hace falta un *personal access token*.

---

## Bloque 3: prueba local (~15 min)

- [ ] Crea el entorno virtual e instala las dependencias de desarrollo:
      ```bash
      cd ingestor
      python3 -m venv .venv
      source .venv/bin/activate
      pip install requests pytest
      ```
      La librería de GCS solo se usa en la nube; localmente no hace falta.
- [ ] `pytest -q` en `ingestor/` y en `rating/` pasan todas las pruebas.
- [ ] `python main.py --seasons 2024 --dest ./landing` descarga 24 rondas.
- [ ] Una segunda ejecución dice `descargada: 0` y `ya_existia: 24`.

---

## Bloque 4: proyecto GCP y límites de gasto (~30 min)

Usa una **cuenta de Google personal**, nunca la del trabajo.

- [ ] Entra a console.cloud.google.com, crea o elige un proyecto y vincula una
      cuenta de facturación.
- [ ] Abre **Cloud Shell** (ícono `>_` arriba a la derecha) y guarda las variables
      del proyecto en `~/.bashrc`, para que sobrevivan entre sesiones:
      ```bash
      echo 'export PROJECT_ID=TU_PROYECTO' >> ~/.bashrc
      echo 'export REGION=us-central1' >> ~/.bashrc
      echo 'export BUCKET=${PROJECT_ID}-landing' >> ~/.bashrc
      echo 'export SA_INGESTOR=f1-ingestor@${PROJECT_ID}.iam.gserviceaccount.com' >> ~/.bashrc
      echo 'export SA_SCHEDULER=f1-scheduler@${PROJECT_ID}.iam.gserviceaccount.com' >> ~/.bashrc
      source ~/.bashrc
      ```
      Ojo: `>>` agrega al final del archivo; un solo `>` lo reemplazaría completo.
- [ ] **Presupuesto con alertas:** consola → Budgets & alerts → Create budget.
      Alcance: solo este proyecto. Monto: USD 5 (o su equivalente en la moneda de la
      cuenta). Alertas al 50%, 90% y 100%.
- [ ] **Cuota diaria de BigQuery (límite duro):** consola → Quotas & System Limits →
      "Query usage per day" (la del proyecto, no la "per user") → Edit.
      Valor: **0,01 TiB** (~10 GiB). El valor por defecto es 200 TiB diarios.

> ⚠️ Un presupuesto **avisa, no corta**. La cuota de BigQuery sí corta. El corte
> automático de facturación (presupuesto → Pub/Sub → función que desactiva la
> facturación) queda como ejercicio futuro.

- [ ] Habilita las APIs:
      ```bash
      gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
        artifactregistry.googleapis.com storage.googleapis.com \
        cloudscheduler.googleapis.com eventarc.googleapis.com \
        pubsub.googleapis.com bigquery.googleapis.com
      ```

---

## Bloque 5: primer despliegue del ingestor (~30 min)

Región `us-central1`: tiene todos los servicios y suele ser la más barata; la
latencia no importa para procesos batch. Todo esto se corre en Cloud Shell.

- [ ] Trae el código: `git clone https://github.com/TU_USUARIO/f1-rating.git`
- [ ] Crea el bucket de aterrizaje. Usar el ID del proyecto como prefijo garantiza
      un nombre único en todo GCP:
      ```bash
      gcloud storage buckets create gs://$BUCKET --location=$REGION \
        --uniform-bucket-level-access
      ```
- [ ] Crea la service account del ingestor, con permisos **solo sobre ese bucket**:
      ```bash
      gcloud iam service-accounts create f1-ingestor --display-name="F1 ingestor"

      gcloud storage buckets add-iam-policy-binding gs://$BUCKET \
        --member=serviceAccount:$SA_INGESTOR --role=roles/storage.objectCreator
      gcloud storage buckets add-iam-policy-binding gs://$BUCKET \
        --member=serviceAccount:$SA_INGESTOR --role=roles/storage.objectViewer
      ```
      *Por qué dos roles:* `objectCreator` permite crear pero no leer; el ingestor
      necesita `objectViewer` para revisar si una ronda ya existe. Ninguno permite borrar.
      Si un comando responde "does not exist", la cuenta recién creada aún no se
      propaga: espera unos segundos y repítelo.
- [ ] Da permiso de construcción a la cuenta que usa Cloud Build:
      ```bash
      PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")
      gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member=serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com \
        --role=roles/run.builder
      ```
      *Por qué:* Cloud Build construye la imagen con la cuenta por defecto de Compute Engine,
      que en proyectos nuevos ya no recibe el rol Editor. Sin `roles/run.builder`, el deploy
      falla con `403 ... storage.objects.get`. El permiso tarda ~2 minutos en propagarse.
- [ ] Despliega el job (Cloud Build construye la imagen con el Dockerfile):
      ```bash
      cd ~/f1-rating/ingestor
      gcloud run jobs deploy f1-ingestor --source . --region=$REGION \
        --service-account=$SA_INGESTOR \
        --args=--seasons,2026,--backend,gcs,--dest,$BUCKET \
        --task-timeout=30m --max-retries=1
      ```
- [ ] Verifica la configuración desplegada (service account y argumentos), ejecútalo
      y revisa el bucket:
      ```bash
      gcloud run jobs describe f1-ingestor --region=$REGION
      gcloud run jobs execute f1-ingestor --region=$REGION --wait
      gcloud storage ls -r gs://$BUCKET | head -20
      ```

---

## Bloque 6: ingesta automática y backfill (~30 min)

- [ ] Crea la identidad del scheduler y dale permiso **solo para ejecutar** el job:
      ```bash
      gcloud iam service-accounts create f1-scheduler --display-name="F1 scheduler"
      gcloud run jobs add-iam-policy-binding f1-ingestor --region=$REGION \
        --member=serviceAccount:$SA_SCHEDULER --role=roles/run.invoker
      ```
      *Por qué otra cuenta:* separación de funciones. El scheduler puede iniciar el
      job, pero no tocar el bucket; el ingestor puede escribir en el bucket, pero no
      iniciar nada.
- [ ] Programa la ingesta cada 6 horas los domingos y lunes (hora de Chile):
      ```bash
      gcloud scheduler jobs create http f1-ingestor-schedule \
        --location=$REGION \
        --schedule="0 */6 * * 0,1" \
        --time-zone="America/Santiago" \
        --uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/f1-ingestor:run" \
        --http-method=POST \
        --oauth-service-account-email=$SA_SCHEDULER
      ```
      `--oauth-...` porque se llama a una API de Google; para llamar a un servicio
      Cloud Run propio se usaría `--oidc-...`.
- [ ] Prueba sin esperar al domingo: `gcloud scheduler jobs run f1-ingestor-schedule
      --location=$REGION`. En `gcloud run jobs executions list --job=f1-ingestor
      --region=$REGION`, la ejecución nueva debe decir `RUN BY: f1-scheduler@...`.
- [ ] **Backfill histórico** con un job dedicado que reutiliza la misma imagen
      (sin reconstruir):
      ```bash
      IMAGE=$(gcloud run jobs describe f1-ingestor --region=$REGION \
        --format="value(spec.template.spec.template.spec.containers[0].image)")
      gcloud run jobs create f1-backfill --image=$IMAGE --region=$REGION \
        --service-account=$SA_INGESTOR \
        --args=--seasons,2000-2025,--backend,gcs,--dest,$BUCKET \
        --task-timeout=30m --max-retries=1
      gcloud run jobs add-iam-policy-binding f1-backfill --region=$REGION \
        --member=serviceAccount:$SA_SCHEDULER --role=roles/run.invoker
      ```
      *Por qué un job aparte:* cambiar argumentos al ejecutar requiere el permiso
      `run.jobs.runWithOverrides`, más amplio que `run.invoker`. Un job con
      argumentos fijos mantiene el mínimo privilegio.
- [ ] El backfill necesita ~1.000 llamadas y cada ejecución tiene un tope de 450.
      Programa ejecuciones con una hora de separación (en este ejemplo, el 24 de
      octubre a las 20:30, 21:30, 22:30 y 23:30):
      ```bash
      gcloud scheduler jobs create http f1-backfill-hoy \
        --location=$REGION --schedule="30 20-23 24 10 *" \
        --time-zone="America/Santiago" \
        --uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/f1-backfill:run" \
        --http-method=POST --oauth-service-account-email=$SA_SCHEDULER
      ```
      ⚠️ Al terminar, **bórralo**: ese cron volvería a dispararse el año siguiente.
      `gcloud scheduler jobs delete f1-backfill-hoy --location=$REGION`
- [ ] Verifica la completitud contando rondas por temporada y comparándolas con el
      calendario oficial:
      ```bash
      mkdir -p ~/landing && gcloud storage rsync -r gs://$BUCKET ~/landing
      for s in ~/landing/season=*; do echo "$(basename $s): $(ls $s | wc -l) rondas"; done
      ```

---

## Si algo falla
Copia el error completo. Un 403 casi siempre responde tres preguntas: **quién**
(qué cuenta), **qué** (qué permiso) y **sobre qué** (qué recurso). Con esas tres,
se sabe qué rol falta y a qué nivel asignarlo.
