# Stage 1: build the Vue 3 admin app into static assets.
FROM node:22-slim AS frontend-build

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# Stage 2: the actual runtime image -- just Python + the backend + the
# frontend's static build output. No Node in the final image.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=frontend-build /frontend/dist ./frontend/dist

EXPOSE 8000

# $PORT is set by PaaS platforms (Render, etc.) to a dynamically-assigned
# port; defaults to 8000 for docker-compose / plain `docker run`, which
# never set it.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request as u; u.urlopen('http://localhost:' + os.environ.get('PORT', '8000') + '/health')" || exit 1

# scripts/seed.py runs the Alembic migration (via init_db()) and is idempotent,
# so it's safe to run on every container start -- fresh installs get schema +
# sample data, existing ones just skip everything that's already there.
CMD ["sh", "-c", "python scripts/seed.py && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
