"""FastAPI backend — agente de búsqueda (UCS) para Emergency Control."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import solver

SCENARIO_PATH = Path(__file__).resolve().parents[2] / "scenarios" / "scenario.json"


def _load_default_scenario() -> dict[str, Any]:
    with SCENARIO_PATH.open(encoding="utf-8") as f:
        return json.load(f)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Precalienta el escenario por defecto en segundo plano: cuando el profesor
    # pulse EXECUTE PLAN la respuesta ya está en caché.
    try:
        solver.warm_up(_load_default_scenario())
    except Exception:  # pragma: no cover
        pass
    yield


app = FastAPI(title="Emergency Control API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/scenario")
def get_scenario() -> dict[str, Any]:
    return _load_default_scenario()


@app.post("/api/solve")
def solve(scenario: dict[str, Any]) -> dict[str, Any]:
    """Resuelve la misión con Uniform-Cost Search.

    Devuelve el plan de MENOR COSTO traducido al contrato de CONTRATO.md, o
    solution_found=false si la misión no tiene solución.
    """
    data = scenario if scenario else _load_default_scenario()
    return solver.solve(data)
