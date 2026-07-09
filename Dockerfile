FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# scripts/seed.py runs the Alembic migration (via init_db()) and is idempotent,
# so it's safe to run on every container start -- fresh installs get schema +
# sample data, existing ones just skip everything that's already there.
CMD ["sh", "-c", "python scripts/seed.py && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
