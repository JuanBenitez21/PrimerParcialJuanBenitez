"""Formulación del problema — los 5 componentes de AIMA cap. 3.

    <s0, Actions(s), Result(s,a), Is-Goal(s), g>

Todo se deriva de scenario.json en tiempo de ejecución. No hay ids, costos ni
cantidades de la instancia demo escritos en este archivo: el profesor puede
cambiar zonas, corredores, puertas, objetos, costos y meta sin tocar el agente.

design.md §Acciones, §Modelo de transición, §Prueba de meta, §Función de costo.
"""

from __future__ import annotations

from bisect import bisect_left, insort
from typing import Any, Iterator, NamedTuple

from .state import KEY, MAT, TOOL, Item, State, canon_ground, canon_payload

MOVE = "MOVE"
PICKUP = "PICKUP"
DROP = "DROP"
OPEN_DOOR = "OPEN_DOOR"
REPAIR = "REPAIR"
ACTIVATE = "ACTIVATE"
RECHARGE = "RECHARGE"



def _insert_sorted(payload: tuple[Item, ...], item: Item) -> tuple[Item, ...]:
    """Inserta manteniendo el orden canónico, sin re-ordenar todo."""
    out = list(payload)
    insort(out, item)
    return tuple(out)


class Action(NamedTuple):
    """Acción interna del agente. `target` es una zona, un item o un id."""

    kind: str
    target: Any

    def __repr__(self) -> str:  # pragma: no cover - solo depuración
        return f"{self.kind}({self.target})"


class Problem:
    """Instancia de búsqueda construida a partir de un escenario."""

    def __init__(self, scenario: dict[str, Any]) -> None:
        self.scenario = scenario

        robot = scenario["robot"]
        self.capacity: int = robot["cargo_capacity"]
        self.battery_max: int = robot["battery_max"]

        costs = scenario.get("action_costs", {})
        self.cost_pickup: int = costs.get("pickup", 1)
        self.cost_drop: int = costs.get("drop", 1)
        self.cost_interact: int = costs.get("interact", 2)
        self.cost_recharge: int = costs.get("recharge", 3)

        # --- Grafo de corredores: zona -> [(destino, costo, puerta|None)] ---
        self.adj: dict[str, list[tuple[str, int, str | None]]] = {}
        for z in scenario["zones"]:
            self.adj[z["id"]] = []
        for c in scenario["corridors"]:
            self.adj.setdefault(c["from"], []).append(
                (c["to"], int(c["cost"]), c.get("door"))
            )

        # --- Puertas y llaves ---
        self.doors: dict[str, dict[str, Any]] = {d["id"]: d for d in scenario["doors"]}
        self.door_of_key: dict[str, str] = {d["key"]: d["id"] for d in scenario["doors"]}

        # --- Paneles: qué herramienta y qué material exigen ---
        self.panels: dict[str, dict[str, Any]] = {p["id"]: p for p in scenario["panels"]}
        self.panels_by_zone: dict[str, list[str]] = {}
        for pid, p in self.panels.items():
            self.panels_by_zone.setdefault(p["zone"], []).append(pid)

        # --- Estaciones y sus dependencias ---
        self.stations: dict[str, dict[str, Any]] = {
            s["id"]: s for s in scenario["stations"]
        }
        self.stations_by_zone: dict[str, list[str]] = {}
        for sid, s in self.stations.items():
            self.stations_by_zone.setdefault(s["zone"], []).append(sid)

        # --- Cargadores: zona -> id. Se acepta también zones[].recharge ---
        self.charger_of_zone: dict[str, str] = {
            c["zone"]: c["id"] for c in scenario.get("chargers", [])
        }
        for z in scenario["zones"]:
            if z.get("recharge") and z["id"] not in self.charger_of_zone:
                self.charger_of_zone[z["id"]] = z["id"]

        # --- Pesos por objeto ---
        self.weight: dict[Item, int] = {}
        for k in scenario["keys"]:
            self.weight[Item(KEY, k["id"])] = int(k.get("weight", 1))
        for t in scenario["tools"]:
            self.weight[Item(TOOL, t["id"])] = int(t.get("weight", 1))
        for m in scenario["materials"]:
            self.weight[Item(MAT, m["type"])] = int(m.get("weight", 1))

        self.goal_stations: frozenset[str] = frozenset(
            scenario["goal"]["stations_online"]
        )

        self.min_cost = min(
            [self.cost_pickup, self.cost_drop, self.cost_interact, self.cost_recharge]
            + [int(c["cost"]) for c in scenario["corridors"]]
        )

        # Cachés. La relevancia solo depende de (doors_open, panels_ok), que son
        # monótonos y toman pocos valores distintos; recomputarla por estado es
        # el cuello de botella. No cambia la semántica, solo el tiempo.
        self._rel_cache: dict[tuple, dict[Item, bool]] = {}
        self._need_cache: dict[frozenset, dict[str, int]] = {}

    # ------------------------------------------------------------------
    # Estado inicial
    # ------------------------------------------------------------------

    def initial_state(self) -> State:
        sc = self.scenario
        ground = [(Item(KEY, k["id"]), k["zone"], 1) for k in sc["keys"]]
        ground += [(Item(TOOL, t["id"]), t["zone"], 1) for t in sc["tools"]]
        ground += [
            (Item(MAT, m["type"]), m["zone"], int(m["count"])) for m in sc["materials"]
        ]

        s = State(
            zone=sc["robot"]["start"],
            battery=int(sc["robot"]["battery_start"]),
            payload=(),
            ground=canon_ground(ground),
            doors_open=frozenset(
                d["id"] for d in sc["doors"] if d.get("state") == "OPEN"
            ),
            panels_ok=frozenset(
                p["id"] for p in sc["panels"] if p.get("state") == "OK"
            ),
            stations_online=frozenset(
                st["id"] for st in sc["stations"] if st.get("state") == "ONLINE"
            ),
        )
        return self._canonicalize(s)

    # ------------------------------------------------------------------
    # Relevancia (design.md §Relevancia)
    # ------------------------------------------------------------------

    def _relevance_table(self, s: State) -> dict[Item, bool]:
        """¿Qué objetos pueden todavía aparecer en alguna precondición?

        Los cambios del entorno son monótonos (una puerta abierta no se cierra,
        un panel reparado no se daña), así que la irrelevancia es permanente y
        la tabla solo depende de (doors_open, panels_ok).
        """
        sig = (s.doors_open, s.panels_ok)
        table = self._rel_cache.get(sig)
        if table is not None:
            return table

        needed = self._needed_table(s)
        table = {}
        for item in self.weight:
            if item.kind == KEY:
                door = self.door_of_key.get(item.name)
                table[item] = door is not None and door not in s.doors_open
            elif item.kind == TOOL:
                table[item] = any(
                    pid not in s.panels_ok and p["requires"]["tool"] == item.name
                    for pid, p in self.panels.items()
                )
            else:
                table[item] = needed.get(item.name, 0) > 0
        self._rel_cache[sig] = table
        return table

    def _needed_table(self, s: State) -> dict[str, int]:
        """Cuántas unidades de cada material siguen haciendo falta."""
        table = self._need_cache.get(s.panels_ok)
        if table is not None:
            return table
        table = {}
        for pid, p in self.panels.items():
            if pid in s.panels_ok:
                continue
            mat = p["requires"]["material"]
            table[mat] = table.get(mat, 0) + 1
        self._need_cache[s.panels_ok] = table
        return table

    def _is_relevant(self, item: Item, s: State) -> bool:
        return self._relevance_table(s).get(item, False)

    def _material_needed(self, mat_type: str, s: State) -> int:
        return self._needed_table(s).get(mat_type, 0)

    def _held(self, item: Item, s: State) -> int:
        return sum(1 for x in s.payload if x == item)

    def _payload_weight(self, s: State) -> int:
        return sum(self.weight.get(x, 1) for x in s.payload)

    def _canonicalize(self, s: State) -> State:
        """Colapsa a GONE los objetos irrelevantes que están en el suelo.

        Su posición ya no aparece en ninguna precondición alcanzable, así que
        dos estados que solo difieran en dónde quedó un objeto muerto tienen
        exactamente los mismos planes futuros con los mismos costos. Eliminar
        esa distinción es *sound* y borra del espacio todas las permutaciones
        de objetos muertos.
        """
        rel = self._relevance_table(s)
        ground = tuple(e for e in s.ground if rel.get(e[0], False))
        if ground == s.ground:
            return s
        return s._replace(ground=ground)

    # ------------------------------------------------------------------
    # Applicable  (design.md §Applicable interno vs legalidad del contrato)
    # ------------------------------------------------------------------

    def actions(self, s: State) -> Iterator[Action]:
        yield from self._move_actions(s)
        yield from self._pickup_actions(s)
        yield from self._drop_actions(s)
        yield from self._interact_actions(s)

    def _move_actions(self, s: State) -> Iterator[Action]:
        for to, cost, door in self.adj.get(s.zone, []):
            if door is not None and door not in s.doors_open:
                continue
            if s.battery < cost:
                continue
            yield Action(MOVE, to)

    def _pickup_actions(self, s: State) -> Iterator[Action]:
        """Poda 1: solo objetos relevantes, y solo las unidades que hacen falta."""
        if s.battery < self.cost_pickup:
            return
        free = self.capacity - self._payload_weight(s)
        seen: set[Item] = set()
        for item, zone, count in s.ground:
            if zone != s.zone or count <= 0 or item in seen:
                continue
            if self.weight.get(item, 1) > free:
                continue
            if not self._is_relevant(item, s):
                continue
            if item.kind == MAT and self._held(item, s) >= self._material_needed(
                item.name, s
            ):
                continue
            seen.add(item)
            yield Action(PICKUP, item)

    def _drop_actions(self, s: State) -> Iterator[Action]:
        """Podas 2 y 3: soltar solo para liberar capacidad; nunca materiales."""
        if s.battery < self.cost_drop or not s.payload:
            return

        full = self._payload_weight(s) >= self.capacity
        wants_here = full and self._has_relevant_pickup_here(s)

        seen: set[Item] = set()
        for item in s.payload:
            if item.kind == MAT or item in seen:
                continue  # poda 3
            seen.add(item)
            if not self._is_relevant(item, s):
                yield Action(DROP, item)  # objeto muerto: libera capacidad
            elif wants_here:
                yield Action(DROP, item)  # hay que hacer hueco aquí y ahora

    def _has_relevant_pickup_here(self, s: State) -> bool:
        for item, zone, count in s.ground:
            if zone != s.zone or count <= 0:
                continue
            if not self._is_relevant(item, s):
                continue
            if item.kind == MAT and self._held(item, s) >= self._material_needed(
                item.name, s
            ):
                continue
            return True
        return False

    def _interact_actions(self, s: State) -> Iterator[Action]:
        held = set(s.payload)

        if s.battery >= self.cost_interact:
            for did, d in self.doors.items():
                if did in s.doors_open or s.zone not in d["between"]:
                    continue
                if Item(KEY, d["key"]) in held:
                    yield Action(OPEN_DOOR, did)

            for pid in self.panels_by_zone.get(s.zone, []):
                if pid in s.panels_ok:
                    continue
                req = self.panels[pid]["requires"]
                if Item(TOOL, req["tool"]) in held and Item(MAT, req["material"]) in held:
                    yield Action(REPAIR, pid)

            for sid in self.stations_by_zone.get(s.zone, []):
                if sid in s.stations_online:
                    continue
                req = self.stations[sid].get("requires", {})
                if not all(p in s.panels_ok for p in req.get("panels_ok", [])):
                    continue
                if not all(x in s.stations_online for x in req.get("stations_online", [])):
                    continue
                yield Action(ACTIVATE, sid)

        # Poda 4: RECHARGE solo si hay cargador, falta carga y alcanza para pagarlo
        charger = self.charger_of_zone.get(s.zone)
        if (
            charger is not None
            and s.battery < self.battery_max
            and s.battery >= self.cost_recharge
        ):
            yield Action(RECHARGE, charger)

    # ------------------------------------------------------------------
    # Costo y transición
    # ------------------------------------------------------------------

    def step_cost(self, s: State, a: Action) -> int:
        if a.kind == MOVE:
            for to, cost, _ in self.adj[s.zone]:
                if to == a.target:
                    return cost
            raise ValueError(f"corredor inexistente {s.zone}->{a.target}")
        if a.kind == PICKUP:
            return self.cost_pickup
        if a.kind == DROP:
            return self.cost_drop
        if a.kind == RECHARGE:
            return self.cost_recharge
        return self.cost_interact

    def result(self, s: State, a: Action) -> State:
        """Determinista y parcial. Clona, aplica los efectos, canonicaliza."""
        cost = self.step_cost(s, a)
        battery = s.battery - cost
        if battery < 0:
            raise ValueError(f"batería insuficiente para {a}")

        if a.kind == MOVE:
            ns = s._replace(zone=a.target, battery=battery)

        elif a.kind == PICKUP:
            item: Item = a.target
            # ground ya está ordenado; quitar una unidad preserva el orden.
            ground = list(s.ground)
            for i, (it, z, n) in enumerate(ground):
                if it == item and z == s.zone:
                    if n > 1:
                        ground[i] = (it, z, n - 1)
                    else:
                        del ground[i]
                    break
            ns = s._replace(
                battery=battery,
                payload=_insert_sorted(s.payload, item),
                ground=tuple(ground),
            )

        elif a.kind == DROP:
            item = a.target
            payload = list(s.payload)
            payload.remove(item)
            ground = list(s.ground)
            entry = (item, s.zone)
            pos = bisect_left(ground, (item, s.zone, 0))
            if pos < len(ground) and ground[pos][:2] == entry:
                ground[pos] = (item, s.zone, ground[pos][2] + 1)
            else:
                ground.insert(pos, (item, s.zone, 1))
            ns = s._replace(
                battery=battery,
                payload=tuple(payload),
                ground=tuple(ground),
            )

        elif a.kind == OPEN_DOOR:
            ns = s._replace(battery=battery, doors_open=s.doors_open | {a.target})

        elif a.kind == REPAIR:
            mat = Item(MAT, self.panels[a.target]["requires"]["material"])
            payload = list(s.payload)
            payload.remove(mat)  # el material se consume; la herramienta no
            ns = s._replace(
                battery=battery,
                payload=canon_payload(payload),
                panels_ok=s.panels_ok | {a.target},
            )

        elif a.kind == ACTIVATE:
            ns = s._replace(
                battery=battery, stations_online=s.stations_online | {a.target}
            )

        elif a.kind == RECHARGE:
            ns = s._replace(battery=self.battery_max)

        else:  # pragma: no cover
            raise ValueError(f"acción desconocida {a}")

        # La relevancia solo depende de (doors_open, panels_ok). MOVE, PICKUP,
        # ACTIVATE y RECHARGE no los tocan, y PICKUP solo quita del suelo objetos
        # que ya eran relevantes: en esos casos canonicalizar es un no-op y nos
        # ahorramos recorrer el suelo en cada transición.
        if a.kind in (OPEN_DOOR, REPAIR, DROP):
            return self._canonicalize(ns)
        return ns

    # ------------------------------------------------------------------
    # Prueba de meta
    # ------------------------------------------------------------------

    def is_goal(self, s: State) -> bool:
        """Se verifica sobre el estado final del MUNDO, no sobre tareas hechas.

        Las puertas abiertas y los paneles reparados son medios, no meta.
        """
        return self.goal_stations <= s.stations_online
