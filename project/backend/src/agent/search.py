"""Estrategias de búsqueda — Graph Search sobre estados canónicos.

design.md §Estrategia de búsqueda.

UCS es la estrategia del agente. BFS está aquí solo como contraste para el
Caso 3 de la validación (menos acciones != menor costo); no se usa en producción.
"""

from __future__ import annotations

import heapq
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .problem import Action, Problem
from .state import State


@dataclass
class Node:
    """Plan parcial en construcción.

    design.md §Qué pertenece al historial: g, parent y action describen CÓMO se
    llegó, no DÓNDE se está. Por eso viven aquí y no en State: si estuvieran en
    el estado, CLOSED no reconocería la misma situación física alcanzada por dos
    rutas y Graph Search degeneraría en Tree Search.
    """

    state: State
    parent: "Node | None" = None
    action: Action | None = None
    path_cost: int = 0
    depth: int = 0

    def plan(self) -> list[Action]:
        """Reconstruye la secuencia de acciones subiendo por los punteros parent."""
        node, acts = self, []
        while node.parent is not None:
            acts.append(node.action)
            node = node.parent
        acts.reverse()
        return acts


@dataclass
class SearchResult:
    found: bool
    plan: list[Action] = field(default_factory=list)
    cost: int = 0
    expanded: int = 0
    generated: int = 0
    reason: str = ""


def uniform_cost_search(problem: Problem, max_expansions: int = 2_000_000) -> SearchResult:
    """Uniform-Cost Search sobre grafos, con dominancia de batería en CLOSED.

    Garantías (design.md):
      - Completitud: espacio finito y todos los costos >= 1 > 0. Si OPEN se
        vacía sin meta, retorna FAILURE en vez de colgarse.
      - Optimalidad: la prueba de meta se hace AL EXTRAER, no al generar. Como
        se extrae siempre el nodo de menor g, al extraerlo se garantiza que no
        existe camino más barato hacia él.
    """
    start = problem.initial_state()
    root = Node(start)

    counter = 0
    frontier: list[tuple[int, int, Node]] = [(0, counter, root)]

    # Parent discarding generalizado. Para cada mundo guardamos la frontera de
    # Pareto de los pares (g, batería) ya alcanzados: un par nuevo solo entra a
    # OPEN si no está dominado por ninguno anterior. Es el mismo lema de
    # monotonía del recurso aplicado en la generación y no solo en la extracción.
    seen: dict[tuple, list[tuple[int, int]]] = {start.world: [(0, start.battery)]}

    # CLOSED indexado por el MUNDO (estado sin batería) -> mejor batería vista.
    closed: dict[tuple, int] = {}

    expanded = 0
    generated = 1

    while frontier:
        g, _, node = heapq.heappop(frontier)
        s = node.state

        if problem.is_goal(s):
            return SearchResult(True, node.plan(), g, expanded, generated)

        # --- Dominancia (design.md, lema de monotonía del recurso) ---
        # Más batería nunca es peor: Applicable(w, b) ⊆ Applicable(w, b') si b<=b'.
        # Un nodo que llega al mismo mundo costando más o igual y con menos o
        # igual batería no puede mejorar ningún plan futuro.
        seen_battery = closed.get(s.world)
        if seen_battery is not None and s.battery <= seen_battery:
            continue
        closed[s.world] = s.battery

        expanded += 1
        if expanded > max_expansions:
            return SearchResult(
                False, [], 0, expanded, generated, "límite de expansiones alcanzado"
            )

        for a in problem.actions(s):
            child_state = problem.result(s, a)
            child_g = g + problem.step_cost(s, a)
            child_b = child_state.battery
            world = child_state.world

            done = closed.get(world)
            if done is not None and child_b <= done:
                continue  # ese mundo ya se expandió más barato y con más carga

            pareto = seen.setdefault(world, [])
            if any(og <= child_g and ob >= child_b for og, ob in pareto):
                continue  # dominado: ni más barato ni con más autonomía
            pareto[:] = [
                (og, ob) for og, ob in pareto if not (child_g <= og and child_b >= ob)
            ]
            pareto.append((child_g, child_b))

            counter += 1
            generated += 1
            heapq.heappush(
                frontier,
                (
                    child_g,
                    counter,
                    Node(child_state, node, a, child_g, node.depth + 1),
                ),
            )

    return SearchResult(False, [], 0, expanded, generated, "espacio agotado sin meta")


def breadth_first_search(problem: Problem, max_expansions: int = 400_000) -> SearchResult:
    """BFS — solo para el Caso 3 de la validación.

    Minimiza el NÚMERO de acciones, no el costo. Con costos heterogéneos (aquí
    los corredores van de 3 a 12) el plan que devuelve puede ser más corto y más
    caro que el de UCS. Ese es exactamente el punto que demuestra el Caso 3.
    """
    start = problem.initial_state()
    root = Node(start)
    if problem.is_goal(start):
        return SearchResult(True, [], 0, 0, 1)

    frontier: deque[Node] = deque([root])
    reached: set[tuple] = {(start.world, start.battery)}
    expanded = 0
    generated = 1

    while frontier:
        node = frontier.popleft()
        expanded += 1
        if expanded > max_expansions:
            return SearchResult(
                False, [], 0, expanded, generated, "límite de expansiones alcanzado"
            )

        for a in problem.actions(node.state):
            child_state = problem.result(node.state, a)
            child_key = (child_state.world, child_state.battery)
            if child_key in reached:
                continue
            child = Node(
                child_state,
                node,
                a,
                node.path_cost + problem.step_cost(node.state, a),
                node.depth + 1,
            )
            generated += 1
            if problem.is_goal(child_state):
                return SearchResult(
                    True, child.plan(), child.path_cost, expanded, generated
                )
            reached.add(child_key)
            frontier.append(child)

    return SearchResult(False, [], 0, expanded, generated, "espacio agotado sin meta")


def plan_cost(problem: Problem, plan: list[Action]) -> int:
    """Recalcula el costo de un plan re-simulándolo. Auditoría independiente."""
    s = problem.initial_state()
    total = 0
    for a in plan:
        total += problem.step_cost(s, a)
        s = problem.result(s, a)
    return total
