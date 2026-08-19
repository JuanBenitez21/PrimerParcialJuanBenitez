"""Punto de entrada del agente: escenario -> respuesta del contrato.

Responsabilidades:
  1. construir el Problem a partir del escenario,
  2. correr UCS,
  3. traducir el plan al contrato,
  4. auditarlo contra el simulador ANTES de responder,
  5. memoizar por escenario.

La memoización es una decisión de ingeniería, no del modelo: UCS expande todos
los nodos con g < C*, lo cual es intrínseco a garantizar el óptimo. Cachear la
respuesta por escenario evita repetir ese trabajo en cada clic del frontend sin
tocar la formulación.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any

from agent.problem import Problem
from agent.search import uniform_cost_search
from agent.translate import to_contract
import simulator

_cache: dict[str, dict[str, Any]] = {}
_locks: dict[str, threading.Lock] = {}
_global_lock = threading.Lock()


def scenario_key(scenario: dict[str, Any]) -> str:
    """Hash del escenario, ignorando lo puramente visual (`layout`)."""
    core = {k: v for k, v in scenario.items() if k not in ("layout", "meta")}
    blob = json.dumps(core, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def _audit(scenario: dict[str, Any], steps: list[dict[str, Any]]) -> str | None:
    """Re-simula el plan. Devuelve None si es válido, o el motivo del fallo.

    El frontend no confía en el plan y lo re-ejecuta contra su propio simulador;
    nosotros hacemos lo mismo antes de responder, para no emitir nunca un plan
    que el banco de pruebas vaya a rechazar.
    """
    try:
        final = simulator.simulate(scenario, steps)
    except AssertionError as exc:
        return f"paso ilegal: {exc}"
    if not simulator.goal_satisfied(scenario, final):
        return "el plan no deja la misión en estado meta"
    total = sum(int(s["cost"]) for s in steps)
    if final["energy_spent"] != total:
        return f"costos inconsistentes: {final['energy_spent']} != {total}"
    return None


def solve(scenario: dict[str, Any]) -> dict[str, Any]:
    key = scenario_key(scenario)

    cached = _cache.get(key)
    if cached is not None:
        return cached

    with _global_lock:
        lock = _locks.setdefault(key, threading.Lock())

    with lock:
        cached = _cache.get(key)
        if cached is not None:
            return cached

        started = time.perf_counter()
        problem = Problem(scenario)
        result = uniform_cost_search(problem)
        elapsed = time.perf_counter() - started

        if not result.found:
            response = {
                "solution_found": False,
                "total_cost": 0,
                "steps": [],
                "message": f"FAILURE — {result.reason}. "
                f"Nodos expandidos: {result.expanded}. ({elapsed:.1f}s)",
            }
            _cache[key] = response
            return response

        steps = to_contract(problem, result.plan)
        problem_err = _audit(scenario, steps)
        if problem_err is not None:  # pragma: no cover - red de seguridad
            return {
                "solution_found": False,
                "total_cost": 0,
                "steps": [],
                "message": f"ERROR INTERNO — plan rechazado por la auditoría: {problem_err}",
            }

        response = {
            "solution_found": True,
            "total_cost": result.cost,
            "steps": steps,
            "message": (
                f"UCS — plan óptimo de costo {result.cost} en {len(steps)} pasos. "
                f"Expandidos {result.expanded} nodos, generados {result.generated} "
                f"({elapsed:.1f}s)."
            ),
        }
        _cache[key] = response
        return response


def warm_up(scenario: dict[str, Any]) -> None:
    """Precalcula un escenario en segundo plano, sin bloquear el arranque."""
    threading.Thread(target=solve, args=(scenario,), daemon=True).start()
