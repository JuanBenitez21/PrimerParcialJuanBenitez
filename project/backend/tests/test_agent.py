"""Entregable 3 — Validación del agente.

Los cinco casos exigidos por el enunciado, más una regresión que comprueba que
el plan del agente es legal, alcanza la meta y es más barato que el plan demo.

Ejecutar:  python tests/test_agent.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent.problem import (  # noqa: E402
    ACTIVATE,
    DROP,
    MOVE,
    OPEN_DOOR,
    PICKUP,
    Action,
    Problem,
)
from agent.search import breadth_first_search, uniform_cost_search  # noqa: E402
from agent.state import KEY, MAT, Item  # noqa: E402
from agent.translate import to_contract  # noqa: E402
from demo_plan import build_demo_plan  # noqa: E402
from simulator import goal_satisfied, simulate  # noqa: E402

SCENARIO = ROOT.parent / "scenarios" / "scenario.json"


def load() -> dict[str, Any]:
    with SCENARIO.open(encoding="utf-8") as f:
        return json.load(f)


def apply_all(problem: Problem, actions: list[Action]):
    s = problem.initial_state()
    for a in actions:
        s = problem.result(s, a)
    return s


# ---------------------------------------------------------------------------
# Escenario mínimo sintético: sirve para aislar propiedades sin depender de la
# instancia demo. Mismas reglas del contrato, otros valores.
# ---------------------------------------------------------------------------


def mini_scenario(direct_cost: int) -> dict[str, Any]:
    """Z1 --direct_cost--> Z2, o Z1 -1-> Z3 -1-> Z2. La estación está en Z2."""
    return {
        "meta": {"id": "mini", "title": "mini", "description": ""},
        "robot": {"start": "Z1", "battery_max": 100, "battery_start": 100,
                  "cargo_capacity": 3},
        "zones": [
            {"id": "Z1", "name": "A", "recharge": False},
            {"id": "Z2", "name": "B", "recharge": False},
            {"id": "Z3", "name": "C", "recharge": False},
        ],
        "corridors": [
            {"from": "Z1", "to": "Z2", "cost": direct_cost, "door": None},
            {"from": "Z2", "to": "Z1", "cost": direct_cost, "door": None},
            {"from": "Z1", "to": "Z3", "cost": 1, "door": None},
            {"from": "Z3", "to": "Z1", "cost": 1, "door": None},
            {"from": "Z3", "to": "Z2", "cost": 1, "door": None},
            {"from": "Z2", "to": "Z3", "cost": 1, "door": None},
        ],
        "doors": [], "keys": [], "tools": [], "materials": [], "panels": [],
        "stations": [{"id": "S1", "kind": "generator", "zone": "Z2",
                      "state": "OFFLINE", "requires": {}}],
        "chargers": [],
        "goal": {"stations_online": ["S1"]},
        "action_costs": {"pickup": 1, "drop": 1, "interact": 2, "recharge": 3},
    }


# ---------------------------------------------------------------------------
# Caso 1 — Estados equivalentes
# ---------------------------------------------------------------------------


def test_caso_1_estados_equivalentes() -> None:
    """Dos historias distintas hacia la misma situación física dan el mismo estado."""
    p = Problem(load())

    prefijo = [
        Action(PICKUP, Item(KEY, "KEY1")),
        Action(OPEN_DOOR, "DOOR1"),
        Action(MOVE, "Z2"),
    ]
    # Mismo mundo, distinto orden de recogida.
    a = apply_all(p, prefijo + [Action(PICKUP, Item(MAT, "FUSE")),
                                Action(PICKUP, Item(MAT, "CHIP"))])
    b = apply_all(p, prefijo + [Action(PICKUP, Item(MAT, "CHIP")),
                                Action(PICKUP, Item(MAT, "FUSE"))])

    assert a == b, "el orden de recogida no es información física"
    assert hash(a) == hash(b), "__hash__ debe coincidir con la equivalencia"

    # La llave usada muere al abrir la puerta: dónde quede en el suelo ya no
    # distingue estados, así que soltarla en Z1 o en Z2 da el mismo mundo.
    en_z1 = apply_all(p, [
        Action(PICKUP, Item(KEY, "KEY1")), Action(OPEN_DOOR, "DOOR1"),
        Action(DROP, Item(KEY, "KEY1")), Action(MOVE, "Z2"),
    ])
    en_z2 = apply_all(p, [
        Action(PICKUP, Item(KEY, "KEY1")), Action(OPEN_DOOR, "DOOR1"),
        Action(MOVE, "Z2"), Action(DROP, Item(KEY, "KEY1")),
    ])
    assert en_z1.world == en_z2.world, "objetos muertos colapsan a GONE"
    print("  caso 1 OK — estados equivalentes se unifican")


# ---------------------------------------------------------------------------
# Caso 2 — Información relevante
# ---------------------------------------------------------------------------


def test_caso_2_informacion_relevante() -> None:
    """Lo que puede cambiar las acciones futuras mantiene los estados separados."""
    p = Problem(load())
    s0 = p.initial_state()

    # (a) La batería es parte del estado: cambia Applicable.
    poca = s0._replace(battery=2)
    assert poca != s0
    assert len(list(p.actions(poca))) < len(list(p.actions(s0))), \
        "con menos batería debe haber menos acciones legales"

    # (b) Una puerta abierta habilita un corredor: no puede colapsarse.
    cerrada = s0
    abierta = s0._replace(doors_open=frozenset({"DOOR1"}))
    assert cerrada != abierta
    destinos_cerrada = {a.target for a in p.actions(cerrada) if a.kind == MOVE}
    destinos_abierta = {a.target for a in p.actions(abierta) if a.kind == MOVE}
    assert destinos_abierta > destinos_cerrada, "DOOR1 abre una ruta nueva"

    # (c) Un objeto vivo en el payload sí distingue: ocupa capacidad.
    con_carga = s0._replace(payload=(Item(KEY, "KEY1"),))
    assert con_carga != s0
    print("  caso 2 OK — batería, puertas y carga distinguen estados")


# ---------------------------------------------------------------------------
# Caso 3 — Menos acciones no es menor costo
# ---------------------------------------------------------------------------


def test_caso_3_costos_diferentes() -> None:
    """BFS minimiza pasos; UCS minimiza costo. Con costos heterogéneos difieren."""
    p = Problem(mini_scenario(direct_cost=20))

    bfs = breadth_first_search(p)
    ucs = uniform_cost_search(p)

    assert bfs.found and ucs.found
    assert len(bfs.plan) < len(ucs.plan), "BFS debe dar el plan con menos acciones"
    assert ucs.cost < bfs.cost, "UCS debe dar el plan más barato"
    assert (len(bfs.plan), bfs.cost) == (2, 22)
    assert (len(ucs.plan), ucs.cost) == (3, 4)
    print(f"  caso 3 OK — BFS: {len(bfs.plan)} pasos / costo {bfs.cost} | "
          f"UCS: {len(ucs.plan)} pasos / costo {ucs.cost}")


# ---------------------------------------------------------------------------
# Caso 4 — Sin solución
# ---------------------------------------------------------------------------


def test_caso_4_sin_solucion() -> None:
    """El agente termina y retorna FAILURE; no queda atrapado explorando."""
    # (a) Batería insuficiente para completar cualquier misión.
    sin_energia = copy.deepcopy(load())
    sin_energia["robot"]["battery_start"] = 2
    r = uniform_cost_search(Problem(sin_energia))
    assert not r.found and r.plan == [] and r.cost == 0
    assert r.reason == "espacio agotado sin meta"

    # (b) Falta un recurso: sin material no hay panel reparado y sin panel no
    #     hay estación en línea. La meta es inalcanzable aunque el mapa lo sea.
    sin_material = copy.deepcopy(mini_scenario(direct_cost=5))
    sin_material["panels"] = [{
        "id": "P1", "zone": "Z2", "damage": "ELECTRICAL",
        "requires": {"tool": "T1", "material": "FUSE"}, "state": "DAMAGED",
    }]
    sin_material["tools"] = [{"id": "T1", "repairs": "ELECTRICAL",
                              "zone": "Z1", "weight": 1}]
    sin_material["stations"][0]["requires"] = {"panels_ok": ["P1"]}
    r2 = uniform_cost_search(Problem(sin_material))
    assert not r2.found and r2.plan == []
    print("  caso 4 OK — FAILURE por batería y por recurso faltante, sin colgarse")


# ---------------------------------------------------------------------------
# Caso 5 — Rutas alternativas
# ---------------------------------------------------------------------------


def test_caso_5_rutas_alternativas() -> None:
    """El mismo mundo se alcanza por dos rutas; se conserva la que exige g."""
    caro = uniform_cost_search(Problem(mini_scenario(direct_cost=20)))
    barato = uniform_cost_search(Problem(mini_scenario(direct_cost=1)))

    ruta_caro = [a.target for a in caro.plan if a.kind == MOVE]
    ruta_barato = [a.target for a in barato.plan if a.kind == MOVE]

    assert ruta_caro == ["Z3", "Z2"], "con el directo caro debe rodear"
    assert ruta_barato == ["Z2"], "con el directo barato debe ir directo"
    assert caro.cost == 4 and barato.cost == 3

    # En la instancia real Z5 también admite dos rutas (Z4->Z5 con DOOR3, y
    # Z2->Z5 por 12). El plan óptimo debe usar la que minimiza el costo total.
    p = Problem(load())
    r = uniform_cost_search(p)
    movimientos = [(a.kind, a.target) for a in r.plan if a.kind == MOVE]
    assert ("MOVE", "Z5") in movimientos
    print(f"  caso 5 OK — ruta cara: {ruta_caro} | ruta barata: {ruta_barato}")


# ---------------------------------------------------------------------------
# Regresión — el plan es legal, cumple la meta y mejora al demo
# ---------------------------------------------------------------------------


def test_plan_legal_y_optimo() -> None:
    sc = load()
    p = Problem(sc)
    r = uniform_cost_search(p)
    assert r.found

    steps = to_contract(p, r.plan)
    final = simulate(sc, steps)  # lanza AssertionError si algún paso es ilegal
    assert goal_satisfied(sc, final), final["stations"]
    assert final["energy_spent"] == r.cost == sum(s["cost"] for s in steps)

    demo = build_demo_plan(sc)
    assert r.cost < demo["total_cost"], "UCS debe mejorar el plan artesanal"

    assert {s["op"] for s in steps} <= {"MOVE", "PICKUP", "DROP", "INTERACT"}
    for s in steps:
        if s["op"] == "INTERACT":
            assert s["action"] in {"OPEN_DOOR", "REPAIR", "ACTIVATE", "RECHARGE"}
    print(f"  regresión OK — UCS {r.cost} vs demo {demo['total_cost']}, "
          f"{len(steps)} pasos legales")


def test_costos_oficiales() -> None:
    """Cada paso emitido lleva el costo oficial del escenario."""
    sc = load()
    p = Problem(sc)
    steps = to_contract(p, uniform_cost_search(p).plan)
    ac = sc["action_costs"]
    corr = {(c["from"], c["to"]): c["cost"] for c in sc["corridors"]}
    zona = sc["robot"]["start"]
    for s in steps:
        if s["op"] == "MOVE":
            assert s["cost"] == corr[(zona, s["to"])]
            zona = s["to"]
        elif s["op"] == "PICKUP":
            assert s["cost"] == ac["pickup"]
        elif s["op"] == "DROP":
            assert s["cost"] == ac["drop"]
        else:
            esperado = ac["recharge"] if s["action"] == "RECHARGE" else ac["interact"]
            assert s["cost"] == esperado
    print("  costos oficiales OK")


if __name__ == "__main__":
    print("Validación del agente (Entregable 3)")
    test_caso_1_estados_equivalentes()
    test_caso_2_informacion_relevante()
    test_caso_3_costos_diferentes()
    test_caso_4_sin_solucion()
    test_caso_5_rutas_alternativas()
    test_plan_legal_y_optimo()
    test_costos_oficiales()
    print("Todos los casos pasan.")
