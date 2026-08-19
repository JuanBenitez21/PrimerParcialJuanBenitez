# Diseño del agente

Este documento debe completarse **antes** de la implementación principal del agente.

Use sus propias palabras y notación. No reemplace este archivo por una transcripción
del enunciado. Las subsecciones existen para que no se le olvide una decisión;
usted decide el contenido.

El entorno, según las propiedades vistas en clase, es totalmente observable,
determinista, secuencial, estático, discreto y de agente único. Bajo esas
condiciones la solución es un **plan completo** y el marco correcto es la
búsqueda clásica. Justifique cada componente con ese marco (AIMA, cap. 3).

---

## Estado

### Definición formal

Escriba la tupla de estado. Cada componente debe ser una variable que el robot
necesita para saber qué podrá hacer después.

```text
s = ⟨zone, battery, payload, ground, doors, panels, stations⟩

```

| Componente | Representación canónica |
|---|---|
| `zone` | id de zona (string) |
| `battery` | entero en `[0, robot.battery_max]` |
| `payload` | multiconjunto de objetos → tupla ordenada de claves (`("KEY","KEY1")`, `("TOOL","MULTITOOL")`, `("MAT","FUSE")`) |
| `ground` | llaves y herramientas: `{id → zona}`; materiales: `{(tipo, zona) → conteo}`, todo ordenado |
| `doors` | `{id → CLOSED \| OPEN}` |
| `panels` | `{id → DAMAGED \| OK}` |
| `stations` | `{id → OFFLINE \| ONLINE}` |

La clase `State` implementa `__eq__` y `__hash__` sobre exactamente esa forma canónica. Es un
requisito de implementación, no un detalle: la lista CLOSED necesita decidir en `O(1)` si dos objetos
distintos en memoria representan la misma situación física.

### Por qué cada variable es necesaria

Criterio de clase (`Applicable`): una variable pertenece al estado **si y solo si**
dos configuraciones que difieran en ella pueden diferir en las acciones legales
futuras o en su resultado.

Pase ese filtro con cada variable. En particular:

- la **batería** forma parte de la situación física (§2.1 del enunciado);
- la **posición de los objetos** no se deduce del escenario inicial si el robot
  puede soltarlos (`DROP`);
- los cambios permanentes (puertas, paneles, estaciones) condicionan el futuro.

- **`zone`** — determina qué corredores, paneles, estaciones y objetos del suelo están al alcance.
  Aparece en la precondición de las seis acciones del mundo.
- **`battery`** — §2.1 del enunciado: es parte de la situación física. Pasa el filtro de forma
  directa: con carga 20 un `MOVE` de costo 8 es aplicable; con carga 5 no lo es. Dos mundos
  idénticos salvo por la batería tienen conjuntos `Applicable` distintos, luego la batería **es**
  estado. *(Ver «Batería como recurso» para la distinción entre estado y clave de CLOSED.)*
- **`payload`** — condiciona la capacidad restante (precondición de `PICKUP`) y la disponibilidad
  de llaves, herramientas y materiales (precondición de `OPEN_DOOR` y `REPAIR`).
- **`ground`** — no se deduce del escenario inicial, porque `PICKUP` y `DROP` la modifican. Es lo
  que determina qué se puede recoger en cada zona.
- **`doors`, `panels`, `stations`** — cambios permanentes del entorno. Una puerta `OPEN` habilita un
  corredor para siempre; un panel `OK` habilita la activación de su estación; una estación `ONLINE`
  satisface la dependencia de otras. Sin ellas el agente no sabría qué le falta.

### Qué información se deriva y NO se almacena

Peso de la carga, grafo de corredores, costos, capacidad, batería máxima, etc.
Si se puede calcular a partir del estado y de las constantes del escenario, no
es una variable de estado.

Constantes del escenario: grafo de corredores y sus costos, `action_costs`, `cargo_capacity`,
`battery_max`, qué llave abre qué puerta, qué herramienta y material exige cada panel, qué paneles y estaciones exige cada estación, ubicación de cargadores. Todo eso es inmutable durante la búsqueda y se consulta del escenario.
Tampoco se almacena el **peso actual de la carga**: es `sum(weight(x) for x in payload)`, derivable del estado y de los pesos declarados. Los materiales se manejan **por tipo**, sin identificadores individuales (§2.2): dos `FUSE` son intercambiables y distinguirlos duplicaría el espacio sin añadir ninguna distinción física.

### Qué pertenece al historial de búsqueda y no al estado físico

`g(n)`, el padre y la acción que trajo aquí describen *cómo llegó*, no *dónde
está*. Viven en el **Nodo**. Si se meten en el estado, CLOSED no puede reconocer
la misma situación física alcanzada por dos rutas.

Viven en el **Nodo**, no en el Estado: el costo acumulado `g(n)`, el puntero `parent`, la `action` que produjo el nodo y la profundidad. Describen *cómo se llegó*, no *dónde se está*.
**Si `g(n)` o la acción previa entraran en la tupla física, dos rutas distintas hacia el mismo mundo nunca colisionarían en CLOSED, el algoritmo degeneraría en Tree Search y el árbol se volvería infinito por los ciclos del mapa.** Es la distinción Estado vs. Nodo de AIMA: un mismo estado puede estar representado por muchos nodos, cada uno con una historia distinta.

### Cuándo dos configuraciones son el mismo estado

Materiales equivalentes por tipo (§2.2): no les ponga ids artificiales.
Estructuras canónicas (conjuntos, contadores) para que `==` y el hash coincidan
con la equivalencia física. Sin eso Graph Search explota.

Cuando coinciden componente a componente en la forma canónica: misma zona, misma batería, mismo
multiconjunto de payload, misma distribución del suelo, y mismos estados de puertas, paneles y
estaciones. En particular:
- el **orden** en que se recogieron los objetos es irrelevante — el payload se ordena antes de
  hashear;
- la **identidad** de los materiales es irrelevante — se cuentan por tipo;
- la **historia** es irrelevante — llegar a Z4 por Z1→Z4 o por Z1→Z2→Z3→Z4 produce el mismo estado
  si el resto de variables coincide.

### Relevancia: objetos que ya no cambian el futuro

Los cambios del entorno son **monótonos** (una puerta abierta no se cierra).
Pregúntese: una llave cuya puerta ya está abierta, o una herramienta cuyo panel
ya está reparado, ¿sigue distinguiendo estados si solo cambia *dónde* está en
el suelo? Si no habilita ninguna acción futura, incluirla multiplica el espacio
con permutaciones de objetos muertos. Justifique si las ignora y por qué eso
no pierde el óptimo.

Los cambios del entorno son **monótonos**: una puerta abierta no se cierra, un panel reparado no se
daña, una estación en línea no se apaga. Por tanto un objeto puede volverse permanentemente
irrelevante:

- una llave cuya puerta ya está `OPEN`;
- una herramienta cuyo panel asociado ya está `OK`;
- un material cuyo panel asociado ya está `OK`.

Aquí hay que separar dos casos, y la distinción importa:

**Objeto muerto en el suelo.** Su posición no aparece en ninguna precondición alcanzable. Colapso su
ubicación en un valor único (`GONE`) al canonicalizar, lo que elimina del espacio todas las
permutaciones de objetos muertos. Es *sound*: dos estados que solo difieren en dónde quedó un objeto
irrelevante tienen exactamente el mismo conjunto de planes futuros y los mismos costos, luego
identificarlos no puede descartar un plan óptimo.

**Objeto muerto en el payload.** **No se puede ignorar: sigue ocupando capacidad y por tanto sigue
apareciendo en la precondición de `PICKUP`.** Permanece en el estado. Lo que sí hago es habilitar su
`DROP` (ver abajo): es el único `DROP` que un plan de costo mínimo podría necesitar.

No fuerzo el `DROP` de objetos muertos. Soltar cuesta `action_costs.drop`, y un plan óptimo puede
preferir seguir cargando una llave usada antes que pagar por soltarla. Forzarlo rompería la
optimalidad.


---

## Acciones

Defina las acciones **internas** del agente (nombres libres). Para cada una:
precondiciones, efectos, costo. Toda acción del mundo exige además
`batería ≥ costo`.

Puede usar una tabla:

| Acción interna | Precondiciones | Efectos | Costo |
|---|---|---|---|
| `MOVE(to)` | existe corredor `zone → to`; si tiene puerta, está `OPEN` | `zone ← to` | `cost` del corredor |
| `PICKUP(x)` | `x` está en el suelo de `zone`; `peso(payload) + weight(x) ≤ cargo_capacity` | `x` pasa de `ground` a `payload` | `action_costs.pickup` |
| `DROP(x)` | `x ∈ payload` | `x` pasa de `payload` al suelo de `zone` | `action_costs.drop` |
| `OPEN_DOOR(d)` | `zone ∈ d.between`; `doors[d] = CLOSED`; `d.key ∈ payload` | `doors[d] ← OPEN` | `action_costs.interact` |
| `REPAIR(p)` | `zone = p.zone`; `panels[p] = DAMAGED`; `p.requires.tool ∈ payload`; `p.requires.material ∈ payload` | `panels[p] ← OK`; se consume el material (la herramienta no) | `action_costs.interact` |
| `ACTIVATE(st)` | `zone = st.zone`; `stations[st] = OFFLINE`; todo `p ∈ st.requires.panels_ok` está `OK`; toda `s ∈ st.requires.stations_online` está `ONLINE` | `stations[st] ← ONLINE` | `action_costs.interact` |
| `RECHARGE(c)` | `zone = c.zone` (o `zone.recharge`); `battery < battery_max`; `battery ≥ costo` | se paga el costo y **después** `battery ← battery_max` | `action_costs.recharge` |

Traducción al contrato: `MOVE`, `PICKUP` y `DROP` van tal cual; `OPEN_DOOR`, `REPAIR`, `ACTIVATE` y
`RECHARGE` se emiten como `INTERACT` con el campo `action` correspondiente (y `consumes` en
`REPAIR`). La capa visual no determina el modelo interno: es una traducción al final del pipeline.


### `Applicable` interno vs legalidad del contrato

El simulador dice cuándo un paso es **legal**. Su generador de sucesores dice
qué acciones son **relevantes para buscar**. No tienen que ser el mismo conjunto.

El contrato **permite** `DROP` en cualquier zona si el objeto está en la carga.
Si su agente genera ese `DROP` en cada estado con carga, el espacio deja de ser
«5 zonas y unas tareas» y pasa a ser «en cuál de las 5 zonas quedó cada objeto».
Eso no se arregla cambiando `cargo_capacity` ni apagando la batería: el escenario
es la fuente de verdad y el profesor probará otras instancias.

Usted puede (y se espera que) restrinja `DROP` —y cualquier otra acción— a los
casos que un plan **óptimo** podría necesitar. Justifique que ningún plan de
costo mínimo usa una acción que usted dejó de generar.

(completar: en particular, cuándo genera `DROP` y por qué)

El simulador decide qué es **legal**. Mi generador de sucesores decide qué es **relevante para buscar**. No son el mismo conjunto, y esa diferencia es una decisión de formulación, no un atajo sobre esta instancia.

**Poda 1 — `PICKUP` solo de objetos relevantes.** Genero `PICKUP(x)` únicamente si `x` puede aún aparecer en alguna precondición: llave de una puerta `CLOSED`, herramienta de un panel `DAMAGED`, o
material requerido por un panel `DAMAGED`. *Sound*: si `x` es irrelevante, todo plan `P` que lo recoja admite un plan gemelo `P'` idéntico sin ese `PICKUP` (y sin su eventual `DROP`), ejecutable
—porque solo se libera capacidad y batería— y de costo estrictamente menor. Luego ningún plan óptimo contiene ese `PICKUP`.

**Poda 2 — `DROP` restringido a dos casos.** El contrato permite soltar en cualquier zona; generarlo libremente convierte el problema en «en cuál de las 5 zonas quedó cada objeto». Genero `DROP(x)`
solo si:

1. `x` ya es irrelevante (su puerta está `OPEN` o su panel está `OK`) — soltarlo libera capacidad
   real; o
2. el payload está lleno y existe en la zona actual un objeto relevante que no cabe.

Cualquier otro `DROP` deja el mundo en una configuración desde la que el objeto sigue haciendo falta: para volver a usarlo hay que pagar un `PICKUP` adicional, luego el plan resultante es estrictamente más caro que el que no soltó. Ningún plan de costo mínimo lo contiene.

**Poda 3 — nunca `DROP` de materiales.** Un material se recoge para consumirse. Soltarlo paga
`pickup + drop` para volver a una configuración físicamente equivalente a no haberlo tocado, luego no aparece en ningún plan óptimo. *(Efecto colateral útil: el banco de pruebas indexa los materiales del suelo por tipo y no por par (tipo, zona), de modo que soltar un `FUSE` en una zona distinta a la del stack restante haría desaparecer ese stack. La poda evita esa divergencia entre mi modelo y el
simulador.)*

**Poda 4 — `RECHARGE` solo con `battery < battery_max`.** Ya es una regla del mundo, pero conviene
respetarla en `Applicable` para no generar sucesores que el simulador rechazaría.
Ninguna de estas podas toca el escenario. No subo `cargo_capacity`, no ignoro la batería y no recorto estaciones: el ajuste está en el generador de sucesores, que es donde la rúbrica lo pide.

---

## Modelo de transición

```text
s --a--> s'     definida solo si a ∈ Applicable(s)
```

`Result` es determinista y parcial. Qué puede cambiar: zona, carga/suelo,
batería, entorno persistente. Qué se preserva. Si canonicaliza el estado tras
una acción, dígalo aquí.

- `MOVE` cambia `zone` y `battery`;
- `PICKUP` / `DROP` cambian `payload`, `ground` y `battery`;
- `OPEN_DOOR`, `REPAIR`, `ACTIVATE` cambian la variable persistente correspondiente y `battery`
  (`REPAIR` cambia además `payload`, al consumir el material);
- `RECHARGE` cambia `battery` (paga el costo y luego sube a `battery_max`).

Todo lo demás se preserva. Tras cada transición el estado se **canonicaliza**: se ordena el payload, se ordenan las entradas del suelo y se colapsan a `GONE` los objetos irrelevantes que estén en el suelo. La canonicalización es idempotente, y es lo que garantiza que `__eq__` y `__hash__` coincidan con la equivalencia física.

---

## Prueba de meta

```text
Goal(s)  ⟺  ∀ id ∈ scenario.goal.stations_online :  s.stations[id] = ONLINE
```

La misión se verifica sobre el **estado final del mundo**, no sobre haber
ejecutado una lista de tareas. ¿Las puertas y los paneles son parte de la meta
o solo medios?

Se verifica sobre el **estado final del mundo**, no sobre haber ejecutado una lista de tareas. La meta se lee del escenario; el agente no asume cuáles ni cuántas estaciones son.

**Las puertas y los paneles no forman parte de la meta: son medios.** Esto tiene consecuencias reales en esta instancia. Z3 es alcanzable por Z1→Z4→Z3 (8+5=13) sin abrir ninguna puerta, y Z5 admite dos rutas (Z4→Z5 con `DOOR3`, o Z2→Z5 por 12 sin puerta). Un agente que asumiera «hay que abrir todas las puertas» o «hay que recoger todas las llaves» estaría resolviendo un problema distinto y más caro: es plausible que `DOOR2`/`KEY2` no aparezcan en el plan óptimo.
---

## Función de costo

```text
g(n) = Σ cost(aᵢ)   sobre las acciones del camino desde s₀ hasta n
```

Debe ser la suma de los **costos oficiales** del escenario (no el número de
pasos). Explique por qué minimizar pasos no es lo mismo que minimizar costo
en este mundo (hay corredores baratos y caros).

Con `cost` tomado de los costos oficiales: el `cost` del corredor para `MOVE`, y `action_costs.{pickup, drop, interact, recharge}` para el resto. Todos son enteros positivos, así que `g` es no decreciente y existe `ε = min(costos) > 0`. Minimizar `g` es la definición correcta de «mejor plan» aquí porque el costo modela consumo de energía, que es el recurso escaso del robot: la batería. Minimizar el **número de pasos** sería una métrica distinta y peor. Los corredores valen entre 3 y 12, así que un plan con menos acciones puede gastar más energía: `Z2→Z5` es una sola acción por 12, mientras que `Z2→Z1→Z4→Z5` son tres acciones por 4+8+3 = 15 (con las puertas ya abiertas), y una variación de los costos del escenario invierte la comparación. El Caso 3 de la validación lo demuestra empíricamente ejecutando BFS y UCS sobre la misma instancia: BFS devuelve un plan con menos acciones y mayor `total_cost`.

---

## Estrategia de búsqueda

Elija una estrategia **vista en clase** y justifíquela con las propiedades
reales del problema (costos heterogéneos, plan de menor costo, espacio finito).

Discuta:

- completitud
- optimalidad (¿la prueba de meta se hace al extraer o al generar?)
- costo de camino
- tiempo y espacio (el `b` peligroso no es el grado del mapa: es cuántos
  `DROP`/`PICKUP` genera por estado)
- cuándo se rompen las garantías (costos 0 o negativos, estados mal
  canonicalizados, OPEN que no se vacía)

Graph Search exige una lista CLOSED sobre estados **canónicos**. Explique cómo
evita reexplorar la misma situación física.


**Uniform-Cost Search (UCS / Dijkstra) sobre Graph Search.** La frontera OPEN es una cola de prioridad ordenada por `g(n)`; CLOSED es un diccionario sobre estados canónicos.

**Por qué UCS y no otra de las vistas en clase.** Los costos son heterogéneos (corredores de 3 a 12, acciones de 1 a 3) y la misión exige explícitamente el plan de **menor costo acumulado**. BFS e IDS solo son óptimos con costos de paso uniformes: aquí devolverían el plan con menos acciones, no el más barato. DFS no ofrece optimalidad en ningún caso. UCS es la única estrategia no informada del temario que garantiza el óptimo con costos heterogéneos.

**Completitud.** El espacio de estados es finito (zonas, objetos, batería acotada y variables booleanas monótonas) y todos los costos son `≥ 1 > 0`, luego `ε > 0` y no hay caminos de costo acumulado acotado con infinitas acciones. UCS termina: o encuentra meta, o vacía OPEN y retorna `FAILURE` (`solution_found: false`, `steps: []`). El caso sin solución no queda atrapado.

**Optimalidad.** La prueba de meta se hace **al extraer** el nodo de la frontera, no al generarlo. Como UCS extrae siempre el nodo de menor `g`, al extraer un nodo se garantiza que no existe camino más barato hacia él; testear al generar devolvería el primer camino *descubierto* y no el más *barato*. Además aplico *parent discarding*: si un sucesor corresponde a un estado que ya está en OPEN con `g` mayor, reemplazo el nodo viejo por el nuevo y actualizo su puntero `parent`.

**Tiempo y espacio.** `O(b^(1+⌊C*/ε⌋))` en ambos, con `ε = min(action_costs)`. El punto crítico es que **`b` no es el grado del grafo de zonas (2 o 3): es `|Applicable(s)|`**, es decir la suma de movimientos, `PICKUP`, `DROP` e `INTERACT` que genero por estado. Sin las podas de la sección anterior, `b` crece con el número de objetos cargables y con las zonas donde se puede soltar, y el espacio —el verdugo habitual de la búsqueda no informada— se vuelve inmanejable mucho antes que el tiempo. Reducir `b` en `Applicable` es la decisión de ingeniería que hace viable a UCS aquí; el algoritmo no cambia.

**Cuándo se rompen las garantías.**

- Costos 0 o negativos: se pierde `ε > 0` y con él la terminación y la optimalidad. Aquí todos los
  costos son enteros positivos, así que la condición se cumple; el agente lo valida al cargar el
  escenario.
- Estados mal canonicalizados (payload sin ordenar, materiales con id individual, objetos muertos no
  colapsados): CLOSED deja de reconocer situaciones equivalentes, Graph Search degenera en Tree
  Search y reaparecen los ciclos y las rutas redundantes.
- Prueba de meta al generar en lugar de al extraer: se pierde la optimalidad.
- Podas no *sound* en `Applicable`: si eliminara una acción que sí aparece en algún plan óptimo,
  UCS seguiría siendo óptimo **sobre el espacio podado**, pero ese óptimo podría no ser el del
  problema real. Por eso cada poda va acompañada de su argumento arriba.

**Cómo CLOSED evita reexplorar.** CLOSED se indexa por el estado canónico. Antes de insertar un
sucesor se consulta: si esa situación física ya fue expandida y el nuevo nodo no aporta nada (ver dominancia), se descarta. Esto elimina tanto los ciclos (`Z1→Z4→Z1`) como los caminos redundantes (varias rutas al mismo mundo).


### Batería como recurso

La batería **sí** va en el estado (§2.1). Eso no implica explorar todos los
paseos que solo gastan energía. Si dos caminos llegan a la **misma**
configuración del mundo (zona, carga, suelo, entorno) y uno trae **más batería
residual** a un **costo menor o igual**, el otro no puede mejorar ningún plan
futuro: está dominado. Tratar cada nivel de batería como un mundo distinto,
sin esa observación, hace que UCS recorra detours inútiles hasta agotar
memoria. Justifique cómo CLOSED aprovecha (o no) esta dominancia.

La batería está en el estado, pero **no en la clave de CLOSED**. Uso la proyección

```text
key(s) = ⟨ zone, payload, ground, doors, panels, stations ⟩      (todo s menos battery)
```

y `CLOSED : key → mejor batería observada`. Separar «qué es el estado» de «cómo lo indexo» es lo que permite podar sin mutilar el modelo.

**Lema (monotonía del recurso).** Para todo mundo `w` y niveles de batería `b ≤ b'`, se cumple `Applicable(w, b) ⊆ Applicable(w, b')`, y el efecto de cada acción sobre las variables distintas de la batería es idéntico. Por tanto todo plan ejecutable desde `(w, b)` lo es también desde `(w, b')` al mismo costo. Más batería nunca es peor.

**Regla de dominancia.** Al extraer de OPEN un nodo `n` con mundo `w = key(s)` y batería `b`:

- si `w ∉ CLOSED`, se expande y se registra `CLOSED[w] = b`. Como UCS extrae en orden creciente de
  `g`, esta es la ruta más barata hacia `w`;
- si `w ∈ CLOSED` y `b ≤ CLOSED[w]`, el nodo está **dominado** (llega a la misma configuración
  costando más o igual y con menos o igual batería) y se poda, por el lema;
- si `w ∈ CLOSED` y `b > CLOSED[w]`, se expande de nuevo y se **actualiza** `CLOSED[w] = b`: la
  ruta es más cara pero deja al robot con más autonomía, y eso puede habilitar acciones que la ruta
  barata no permitía.

Sin esta regla, tratar cada nivel de batería como un mundo distinto multiplicaría el espacio por `battery_max + 1` y UCS recorrería detours que solo gastan energía. Con ella, el óptimo se conserva: las únicas ramas descartadas son las que el lema garantiza que no pueden mejorar ningún plan futuro.


---

## Formulación y tamaño del espacio (obligatorio)

El mapa visible es pequeño. El espacio de estados **no** lo es, si se formula
mal. Responda con sus palabras:

1. ¿Por qué «5 zonas, ~10 objetos, capacidad 3» puede generar millones de nodos
   en un UCS ingenuo?
2. ¿Qué papel tiene `DROP` en esa explosión?
3. ¿Qué podas o abstracciones aplicó y por qué **no pierden el óptimo**
   (*sound*)?
4. ¿Por qué **no** es solución subir la capacidad, bajar las estaciones o
   ignorar la batería?

Porque el estado no es «dónde está el robot», sino «cómo está el mundo». Cota superior para esta instancia, sin podas:

| Factor | Cuenta |
|---|---|
| 6 objetos únicos (3 llaves + 3 herramientas) × 6 ubicaciones (5 zonas + payload) | `6⁶ = 46 656` |
| Materiales por multiconjunto: FUSE (2 idénticos, 6 ubicaciones) = 21, CHIP = 6, CABLE = 6 | `756` |
| Zona del robot | `5` |
| Puertas × paneles × estaciones (`2³ · 2³ · 2³`) | `512` |
| Niveles de batería (0..100) | `101` |

Producto ≈ **9 × 10¹² estados** (cota superior; la restricción de capacidad recorta parte, pero el orden de magnitud se mantiene). El mapa es pequeño; el espacio no.

**2. El papel de `DROP`.** `DROP` es el multiplicador. Es lo que convierte «la posición de cada
objeto» en una variable libre sobre las 5 zonas en lugar de una constante del escenario: sin él, el factor `6⁶ · 756` colapsa a un puñado de configuraciones alcanzables. Además actúa en cada nivel del árbol, así que infla `b` y `C*/ε` simultáneamente.

**3. Podas aplicadas y por qué son *sound*.** `PICKUP` solo de objetos relevantes; `DROP` solo para liberar capacidad (objeto muerto o payload lleno con objeto relevante disponible); nunca `DROP` de materiales; colapso de objetos irrelevantes en el suelo a `GONE`; dominancia de batería en CLOSED.
Cada una tiene su argumento arriba, y todas comparten la misma forma: la acción eliminada admite un plan gemelo sin ella de costo menor o igual, luego ningún plan de costo mínimo la usa. El óptimo del espacio podado es el óptimo del problema.

**4. Por qué no es solución subir la capacidad, bajar las estaciones o ignorar la batería.** Porque eso cambia el problema en lugar de resolverlo. `scenario.json` es la fuente de verdad y el profesor probará otras instancias con las mismas reglas y otros valores: un agente que solo termina con `cargo_capacity` alta falla en cuanto la capacidad vuelva a apretar, y uno que ignora la batería produce planes que el simulador rechaza por energía insuficiente. El problema no es que UCS sea lento: es que `Applicable` era demasiado generoso. El arreglo pertenece al modelo.

---

## Validación

| Caso | Qué demuestra | Cómo |
|---|---|---|
| 1. Estados equivalentes | Dos historias distintas hacia el mismo mundo producen el mismo estado lógico | Construir el mismo mundo por dos secuencias de acciones; comprobar `==` y `hash` iguales |
| 2. Información relevante | Dos configuraciones que difieren en algo que cambia el futuro siguen siendo estados distintos | Mismo mundo con `DOOR1` `OPEN` vs `CLOSED`, y mismo mundo con distinta batería → estados distintos |
| 3. Costos diferentes | Menos acciones ≠ menor costo | Ejecutar BFS y UCS sobre la misma instancia: BFS da menos pasos y mayor `total_cost` |
| 4. Sin solución | Terminación correcta y `FAILURE` | Instancia con batería insuficiente o llave inalcanzable → `solution_found: false`, `steps: []`, sin colgarse |
| 5. Rutas alternativas | El agente conserva la ruta que corresponde a `g` | Z5 alcanzable por `Z4→Z5` (con `DOOR3`) y por `Z2→Z5` (12): comprobar que el plan elige la de menor costo total |

El plan emitido por `/api/solve` se valida además contra el simulador antes de responder: todos los pasos deben ser legales, los costos deben coincidir con los oficiales del escenario y el estado final debe satisfacer `Goal`.