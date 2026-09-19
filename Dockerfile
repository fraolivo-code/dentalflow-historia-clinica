# Historia Clinica Digital — Fase 2. Imagen de la API (FastAPI + Alembic).
FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# Railway inyecta PORT en runtime; alembic upgrade head corre en cada deploy
# para que la base quede al dia con las migraciones antes de levantar la API.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
