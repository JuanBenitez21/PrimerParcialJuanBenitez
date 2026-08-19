# Emergency Control — Agente de planificación (UCS)

Primer Parcial · Fundamentos de Inteligencia Artificial · Universidad de La Sabana · 2026-2

El backend expone `POST /api/solve`, que recibe un escenario y devuelve el **plan de menor costo**
para dejar todas las estaciones de la misión en línea, traducido al contrato de `CONTRATO.md`.

El diseño del agente (estado, acciones, transición, meta, costo, estrategia y podas) está en
[`design.md`](design.md). Este README solo explica cómo ejecutarlo.

---

## 1. Instalación

Requiere Python 3.11+ y Node 18+.

### Backend

```bash
cd project/backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
# source .venv/bin/activate
pip install -r requirements.txt
```

### Frontend

```bash
cd project/frontend
npm install
```

---

## 2. Ejecución

Dos terminales.

**Terminal 1 — backend**

```bash
cd project/backend
uvicorn main:app --app-dir src --port 8000
```

Comprobar: <http://127.0.0.1:8000/api/health> → `{"status":"ok"}`

**Terminal 2 — frontend**

```bash
cd project/frontend
npm run dev
```

Abrir <http://localhost:5173> y pulsar **EXECUTE PLAN**.

> **Nota sobre el primer arranque.** Al iniciar, el backend precalcula en segundo plano el plan del
> escenario por defecto (~30 s en un portátil normal). Si pulsas EXECUTE PLAN de inmediato, la
> primera respuesta puede tardar ese tiempo; a partir de ahí es instantánea. El motivo está
> explicado en `design.md` §Estrategia de búsqueda: UCS debe expandir todos los nodos con
> `g < C*` para garantizar el óptimo, y se prefirió un agente exacto y memoizado antes que uno
> rápido que perdiera la optimalidad.

---

## 3. Probar una misión

**Desde la interfaz.** Pulsar EXECUTE PLAN. El robot recorre el plan casilla a casilla; el log de la
derecha muestra cada paso con su costo y la batería restante.

**Desde la consola**, con el backend levantado:

```bash
curl -X POST http://127.0.0.1:8000/api/solve \
     -H "Content-Type: application/json" \
     -d @../scenarios/scenario.json
```

**Con otro escenario.** `POST /api/solve` acepta cualquier escenario con las mismas reglas: basta
enviar otro JSON en el cuerpo. El agente no tiene ids, costos ni cantidades codificados; todo se lee
del escenario recibido.

---

## 4. Interpretar el resultado

```json
{
  "solution_found": true,
  "total_cost": 88,
  "steps": [ { "op": "MOVE", "from": "Z1", "to": "Z2", "cost": 4 } ],
  "message": "UCS — plan óptimo de costo 88 en 33 pasos. Expandidos 553840 nodos..."
}
```

- `solution_found` — `false` con `steps: []` es el caso **FAILURE**: la misión no tiene solución
  bajo ese escenario. El agente termina; no se queda explorando.
- `total_cost` — suma de los costos oficiales del escenario. Es el valor que el agente **minimiza**;
  no es el número de pasos.
- `steps` — solo las cuatro operaciones del contrato. Las acciones internas del agente
  (`OPEN_DOOR`, `REPAIR`, `ACTIVATE`, `RECHARGE`) viajan dentro de `INTERACT` en el campo `action`.
- `message` — traza de la búsqueda: costo, longitud, nodos expandidos y generados, tiempo.

En la interfaz: el HUD muestra zona, batería, carga, progreso de la misión y costo acumulado. Si el
simulador rechazara un paso, el log lo indicaría con el motivo exacto y detendría la ejecución.

Sobre el escenario demo el agente encuentra **costo 88 en 33 pasos**, frente a los **99** del plan
artesanal de referencia (`demo_plan.py`).

---

## 5. Pruebas

```bash
cd project/backend
python tests/test_agent.py     # los 5 casos del Entregable 3 + regresión (~2 min)
python tests/test_demo_plan.py # comprobación del plan de referencia
```

`test_agent.py` cubre: estados equivalentes, información relevante, menos acciones ≠ menor costo
(BFS vs UCS), FAILURE sin colgarse, rutas alternativas, legalidad del plan contra el simulador y
correspondencia de cada `cost` con los costos oficiales del escenario.

---

## 6. Estructura

```text
project/
├── backend/
│   ├── src/
│   │   ├── agent/
│   │   │   ├── state.py       # estado canónico, hashable
│   │   │   ├── problem.py     # los 5 componentes AIMA + Applicable con podas
│   │   │   ├── search.py      # UCS con dominancia de batería (y BFS de contraste)
│   │   │   └── translate.py   # acción interna -> contrato visual
│   │   ├── solver.py          # orquestación, memoización y auditoría del plan
│   │   ├── simulator.py       # simulador de referencia (auditoría)
│   │   ├── demo_plan.py       # plan artesanal de referencia
│   │   └── main.py            # FastAPI: /api/solve
│   └── tests/
├── frontend/                  # React + R3F (sin cambios)
├── scenarios/scenario.json    # fuente de verdad
├── design.md                  # diseño del agente
└── README.md
```

El modelo interno de IA y la representación visual están separados: `agent/` no conoce el formato
del frontend, y `translate.py` es la única capa que lo traduce.
