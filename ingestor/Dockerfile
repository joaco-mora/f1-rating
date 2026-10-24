# Imagen del ingestor para Cloud Run Jobs.
FROM python:3.12-slim

WORKDIR /app

# Dependencias primero: si solo cambia el código, Docker reutiliza esta capa.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY jolpica_client.py storage.py main.py ./

# Los argumentos (--seasons, --backend, --dest) se pasan al ejecutar el job.
ENTRYPOINT ["python", "main.py"]
