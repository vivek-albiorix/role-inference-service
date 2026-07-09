from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db import init_db

app = FastAPI(
    title="Role Inference Service",
    description="Maps messy SSO profiles to canonical Work Architecture roles.",
    version="0.1.0",
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
