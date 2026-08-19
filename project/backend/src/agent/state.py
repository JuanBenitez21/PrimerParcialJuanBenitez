"""Estado físico del mundo — forma canónica, hashable e inmutable.

design.md §Estado. La tupla es:

    s = <zone, battery, payload, ground, doors, panels, stations>

Todo lo que no cambia durante la búsqueda (grafo, costos, capacidad, qué llave
abre qué puerta) NO vive aquí: vive en Problem, que lo lee del escenario.
"""

from __future__ import annotations

from typing import Iterable, NamedTuple

# --- Identificación de objetos -------------------------------------------------
# Llaves y herramientas se identifican por id; los materiales por TIPO (§2.2 del
# enunciado): dos FUSE son intercambiables y darles ids artificiales duplicaría
# el espacio de estados sin añadir ninguna distinción física.

KEY = "KEY"
TOOL = "TOOL"
MAT = "MAT"


class Item(NamedTuple):
    """Un objeto transportable. (KEY|TOOL, id) o (MAT, tipo)."""

    kind: str
    name: str

    def __repr__(self) -> str:  # pragma: no cover - solo depuración
        return f"{self.kind}:{self.name}"


class State(NamedTuple):
    """Configuración física del mundo.

    Es un NamedTuple: inmutable, con __eq__ y __hash__ estructurales gratis.
    Eso es justo lo que CLOSED necesita para decidir en O(1) si dos objetos
    distintos en memoria representan la misma situación física.

    Invariante de canonicalización (garantizado por Problem.result):
      - payload y ground están ordenados;
      - los materiales se agregan por (tipo, zona) con un contador;
      - los objetos irrelevantes que están en el suelo no aparecen en ground
        (colapsados a GONE): su posición ya no distingue estados.
    """

    zone: str
    battery: int
    payload: tuple[Item, ...]
    ground: tuple[tuple[Item, str, int], ...]
    doors_open: frozenset[str]
    panels_ok: frozenset[str]
    stations_online: frozenset[str]

    @property
    def world(self) -> tuple:
        """Proyección sin batería — la clave de CLOSED.

        design.md §Batería como recurso: la batería ES parte del estado (cambia
        Applicable), pero NO es parte de la clave con la que indexamos CLOSED.
        Separar ambas cosas es lo que permite aplicar dominancia sin mutilar el
        modelo.
        """
        return (
            self.zone,
            self.payload,
            self.ground,
            self.doors_open,
            self.panels_ok,
            self.stations_online,
        )


# --- Constructores canónicos ---------------------------------------------------


def canon_payload(items: Iterable[Item]) -> tuple[Item, ...]:
    """Multiconjunto de objetos cargados -> tupla ordenada.

    El ORDEN en que se recogieron los objetos no es información física: dos
    robots con {KEY1, FUSE} y {FUSE, KEY1} están en la misma situación. Ordenar
    antes de hashear es lo que hace que == coincida con la equivalencia real.
    """
    return tuple(sorted(items))


def canon_ground(entries: Iterable[tuple[Item, str, int]]) -> tuple[tuple[Item, str, int], ...]:
    """Objetos en el suelo -> tupla ordenada de (item, zona, cantidad).

    Llaves y herramientas siempre con cantidad 1. Los materiales se agregan por
    (tipo, zona): tres FUSE en Z2 son una sola entrada con count=3, no tres
    entradas distinguibles.
    """
    acc: dict[tuple[Item, str], int] = {}
    for item, zone, count in entries:
        if count <= 0:
            continue
        acc[(item, zone)] = acc.get((item, zone), 0) + count
    return tuple(sorted((item, zone, n) for (item, zone), n in acc.items()))
