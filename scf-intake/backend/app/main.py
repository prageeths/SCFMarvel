"""FastAPI application entrypoint (PRD §4, §9)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .api import router
from .config import settings

app = FastAPI(
    title="SCF Agentic Intake",
    version="1.0.0",
    description=(
        "Agentic Intake Request Application for the Supply Chain Finance platform. "
        "Three orchestrated agents validate, score, and document intake requests. "
        "LLM access is behind a swappable adapter and optional; the service runs "
        "deterministically with no API key."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.on_event("startup")
def _startup() -> None:
    db.init_db()
    _seed_examples()


@app.get("/")
def root() -> dict:
    return {
        "app": settings.app_name,
        "llm_enabled": settings.llm_enabled,
        "docs": "/docs",
        "health": "/api/health",
    }


def _seed_examples() -> None:
    """Populate a few processed example requests on first run (synthetic only)."""
    if db.count() > 0:
        return
    from .examples import build_examples

    db.save_many(build_examples())
