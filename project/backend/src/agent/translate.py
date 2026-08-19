"""Traducción: acción interna del agente -> paso del contrato (CONTRATO.md).

La capa visual NO determina el modelo interno. El agente razona con acciones
como REPAIR(PANEL_A) o RECHARGE(CHARGER_1); esta capa las convierte al conjunto
cerrado que acepta el banco de pruebas:

    MOVE | PICKUP | DROP | INTERACT{OPEN_DOOR, REPAIR, ACTIVATE, RECHARGE}

Es lo último del pipeline, y es la única parte del agente que conoce el formato
del frontend.
"""

from __future__ import annotations

from typing import Any

from .problem import (
    ACTIVATE,
    DROP,
    MOVE,
    OPEN_DOOR,
    PICKUP,
    RECHARGE,
    REPAIR,
    Action,
    Problem,
)
from .state import Item


def _item_ref(item: Item) -> str:
    """Llaves y herramientas por id; materiales por TIPO (contrato §3.2)."""
    return item.name


def to_contract(problem: Problem, plan: list[Action]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    s = problem.initial_state()

    for a in plan:
        cost = problem.step_cost(s, a)

        if a.kind == MOVE:
            steps.append({"op": "MOVE", "from": s.zone, "to": a.target, "cost": cost})
        elif a.kind == PICKUP:
            steps.append({"op": "PICKUP", "item": _item_ref(a.target), "cost": cost})
        elif a.kind == DROP:
            steps.append({"op": "DROP", "item": _item_ref(a.target), "cost": cost})
        elif a.kind == OPEN_DOOR:
            steps.append(
                {"op": "INTERACT", "target": a.target, "action": "OPEN_DOOR", "cost": cost}
            )
        elif a.kind == REPAIR:
            steps.append(
                {
                    "op": "INTERACT",
                    "target": a.target,
                    "action": "REPAIR",
                    "consumes": problem.panels[a.target]["requires"]["material"],
                    "cost": cost,
                }
            )
        elif a.kind == ACTIVATE:
            steps.append(
                {"op": "INTERACT", "target": a.target, "action": "ACTIVATE", "cost": cost}
            )
        elif a.kind == RECHARGE:
            steps.append(
                {"op": "INTERACT", "target": a.target, "action": "RECHARGE", "cost": cost}
            )
        else:  # pragma: no cover
            raise ValueError(f"acción interna sin traducción: {a}")

        s = problem.result(s, a)

    return steps
