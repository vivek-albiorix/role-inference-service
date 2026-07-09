from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import history, inference, overrides, profiles, reprocess, roles, users
from app.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Role Inference Service",
    description="Maps messy SSO profiles to canonical Work Architecture roles.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


API_PREFIX = "/api"
app.include_router(profiles.router, prefix=API_PREFIX)
app.include_router(inference.router, prefix=API_PREFIX)
app.include_router(overrides.router, prefix=API_PREFIX)
app.include_router(history.router, prefix=API_PREFIX)
app.include_router(roles.router, prefix=API_PREFIX)
app.include_router(reprocess.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)

# Mounted last: only matches requests no API route above already claimed.
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
