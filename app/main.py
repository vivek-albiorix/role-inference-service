from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
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
# Serves the built Vue admin app (frontend/, `npm run build` -> frontend/dist)
# -- run `npm run dev` in frontend/ separately for hot-reloading development.
#
# Guarded rather than mounted unconditionally: frontend/dist is a build
# artifact, not something checked into git, so a fresh clone (or `pytest`,
# which imports this module) shouldn't hard-crash just because no one has
# run `npm run build` yet. The API itself never depends on this.
_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="static")
else:

    @app.get("/", response_class=PlainTextResponse)
    def frontend_not_built() -> str:
        return (
            "Frontend not built yet. Run `npm install && npm run build` in frontend/, "
            "or `npm run dev` there for hot-reloading development. API docs: /docs"
        )
