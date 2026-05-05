# Integridad criptográfica del sistema de guardado

Documentación técnica del sistema de protección anti-manipulación
implementado el 4 de abril de 2026. Referencia para futuras ampliaciones
y como caso de estudio de seguridad en aplicaciones locales.

---

## El problema

PongIA almacena todo el progreso del jugador (partidas, records, logros,
nivel RPG, puntos de ascensión) en un único archivo JSON:

```
~/Library/Application Support/PongIA/saves/game_history.json   (macOS)
%APPDATA%/PongIA/saves/game_history.json                       (Windows)
```

Al ser JSON plano, cualquier usuario podía abrir el archivo con un editor
de texto y falsificar records, desbloquear logros o inflarse el nivel RPG.

---

## Opciones evaluadas

Se analizaron cuatro enfoques de protección local (sin servidor):

| Opción | Descripción | Pros | Contras |
|--------|-------------|------|---------|
| **HMAC con clave embebida** | Firmar el JSON con una clave secreta hardcodeada en el código | Simple, stdlib pura | Con código público la clave es visible: cualquiera puede firmar |
| **HMAC + ofuscación de clave** | Derivar la clave en runtime dispersando constantes en el código | Dificulta la extracción | Con código público, la lógica de derivación es visible igualmente |
| **Cifrado completo (Fernet/AES)** | Guardar el archivo cifrado, ilegible sin la clave | El usuario no puede leer ni modificar | Misma limitación de clave embebida; añade dependencia externa (`cryptography`, ~5-10 MB en el bundle) |
| **Cadena de hashes (blockchain)** | Cada sesión incluye un hash que depende de la anterior | No depende de secretos; integridad estructural | Un atacante puede regenerar la cadena completa desde cero |

### Decisión

Ninguna opción individual es suficiente con código fuente público.
La combinación elegida fue:

> **Cadena de hashes (integridad estructural) + HMAC con clave derivada del hardware (anti-falsificación)**

Esta combinación no requiere dependencias externas (solo stdlib: `hashlib`,
`hmac`, `subprocess`) y su seguridad no se degrada por tener el código público,
ya que la clave depende del hardware físico del usuario, no del código.

---

## Cómo funciona

### Capa 1: Cadena de hashes

Cada sesión de juego guardada incluye un campo `_chain_hash` calculado como:

```
_chain_hash = SHA-256( hash_sesion_anterior + "|" + JSON_canonico_sesion )
```

- La primera sesión usa `"genesis"` como hash anterior.
- El JSON canónico excluye el propio `_chain_hash` y se serializa con
  `sort_keys=True` y separadores fijos para garantizar determinismo.
- Si alguien edita, inserta o elimina una sesión, la cadena se rompe.

**Limitación:** un atacante puede regenerar la cadena completa desde cero
si construye todas las sesiones. Esta capa protege contra ediciones parciales.

### Capa 2: HMAC con clave de placa base

Todo el contenido del archivo se firma con HMAC-SHA256 usando una clave
derivada del UUID de la placa base (SMBIOS UUID):

```python
# macOS
ioreg -rd1 -c IOPlatformExpertDevice  ->  IOPlatformUUID

# Windows
wmic csproduct get uuid
```

La clave se deriva así:

```python
clave = SHA-256( salt_publico + UUID_placa_base )
```

- El salt (`b"PongIA-save-integrity-v1"`) es público y solo sirve para
  separación de dominio criptográfico.
- La firma se almacena como campo `_hmac` en el nivel raíz del JSON.
- Al cargar, se recalcula el HMAC y se compara con el almacenado.

**Por qué UUID de placa base y no MAC address:**

| Identificador | Estabilidad | Cambia si... |
|---------------|-------------|-------------|
| MAC address (`uuid.getnode()`) | Media | Cambias adaptador de red, VPN, MAC aleatoria del SO |
| Serial de disco | Alta | Reemplazas el disco/SSD |
| **UUID de placa base** | **Muy alta** | **Solo si cambias la placa base** |

Se descartó la MAC address por su inestabilidad ante cambios de red.

### Estructura del archivo firmado

```json
{
  "version": "1.4",
  "sessions": [
    {
      "date": "2026-04-04T15:30:00",
      "winner": "jugador",
      "player_points_total": 18,
      "_chain_hash": "a1b2c3d4..."
    }
  ],
  "records": {},
  "achievements": {},
  "career_stats": {},
  "phases_unlocked": {},
  "rpg": {},
  "_hmac": "e5f6a7b8..."
}
```

---

## Comportamiento ante manipulación

### Detección y consecuencia: descarte total

Al cargar el archivo, `load_history()` valida ambas capas. Si cualquiera
falla, **el archivo se descarta completamente** y se devuelve un historial
vacío. El juego empieza de cero:

1. **HMAC inválido:** el archivo fue manipulado o transferido a otra máquina.
2. **Cadena rota:** se editaron, insertaron o eliminaron sesiones.
3. **Sin firma:** archivo de versión anterior o fabricado externamente.

En todos los casos se emite un `warnings.warn()` para dejar constancia en
los logs, y el usuario comienza con un historial limpio.

**Justificación:** congelar el progreso (la estrategia anterior) no era
suficiente — un archivo falso con todo desbloqueado ya tendría todo el
progreso, y congelar la progresión no revertía nada. Solo descartando el
archivo completo se cierra este vector.

### Aviso al usuario

En la primera ejecución del juego, se muestra un overlay informativo en la
pantalla de título (antes del botón JUGAR) avisando de que el sistema de
guardado está protegido y que un cambio de placa base puede invalidar la firma.
Este mensaje aparece una sola vez (controlado por el flag
`_integrity_notice_shown` en el historial).

---

## Migración desde versiones anteriores (desactivada)

La migración automática de archivos v1.3 a v1.4 fue implementada inicialmente
pero se desactivó por ser un vector de ataque: un usuario podía fabricar un
archivo v1.3 con todo el progreso desbloqueado, colocarlo en la carpeta de
saves, y el juego lo firmaría como legítimo al migrar.

Al no existir un servidor que valide la autenticidad de los archivos antiguos,
no hay forma de distinguir un archivo v1.3 genuino de uno fabricado. La decisión
fue priorizar la integridad futura del sistema sobre la comodidad de migrar
datos de versiones anteriores.

**Comportamiento actual:** si se detecta un archivo sin firma HMAC (v1.3 o
anterior), se descarta y se inicia un historial vacío v1.4. No se admiten
archivos sin firmar bajo ningún concepto.

El código de migración se conserva comentado en `save_manager.py` por si en
el futuro se implementa un mecanismo seguro de verificación (por ejemplo,
validación del lado del servidor).

---

## Ofuscación del binario: evaluación

Se evaluó ofuscar el `.exe`/`.app` para dificultar la lectura del algoritmo:

| Herramienta | Coste | Resultado |
|-------------|-------|-----------|
| **PyArmor** | De pago (versión free limitada) | Ofusca bytecode, dificulta decompilación |
| **Cython** | Gratuito | Compila a C, pero requiere compilador y complica el build |
| **Nuitka** | Gratuito | Compila a binario nativo, reemplaza PyInstaller |

**Decisión:** se descartó la ofuscación porque el código fuente es público
(repositorio GitHub). Ofuscar el binario no aporta protección si el algoritmo
completo es visible en el repositorio. Sería como poner una puerta blindada
y dejar la ventana abierta.

---

## Limitaciones asumidas

1. **Sin servidor, la protección es disuasoria, no absoluta.** Un programador
   que lea el código fuente, obtenga su UUID de placa base (un comando del SO)
   y escriba 20 líneas de Python puede generar un archivo perfectamente firmado.

2. **El archivo es legible** (JSON, no cifrado). Cualquiera puede ver sus
   partidas, records y logros. Lo que no puede es modificarlos sin romper la firma.

3. **Cambio de placa base** invalida el HMAC. El archivo se descarta y el
   usuario pierde su progreso. Se avisa de esto en la primera ejecución del
   juego mediante un overlay informativo en la pantalla de título.

### Resumen de protección

| Amenaza | Protegido |
|---------|-----------|
| Edición casual del JSON | Sí |
| Transferir saves entre máquinas | Sí |
| Insertar/eliminar sesiones | Sí |
| Script externo con código público + UUID propio | No |
| Servidor de validación | No implementado (fuera de alcance) |

La protección actual detiene al 99% de los usuarios. El 1% restante
(programadores que entienden criptografía y Python) requeriría validación
del lado del servidor, que queda fuera del alcance de este proyecto.

---

## Archivos relevantes

```
pong/save_manager.py       Firma, validacion, cadena de hashes, descarte de archivos invalidos
pong/game.py               Aviso one-time de integridad en pantalla de titulo
pong/splash.py             Overlay de aviso de integridad (ZXTitleScreen)
```

---
---

# Adenda: Proof of Gameplay (propuesta teórica)

## El problema que queda abierto

La protección actual (cadena de hashes + HMAC con UUID de placa base) impide
la edición casual del archivo de guardado, pero un usuario con acceso al
código fuente y a su propio UUID puede generar un archivo perfectamente
firmado con datos fabricados. Con herramientas de IA generativa, este
proceso puede completarse en minutos.

La raíz del problema es que el sistema actual protege la **integridad del**
archivo** (que no fue modificado), pero no verifica la **autenticidad del
gameplay** (que las partidas realmente se jugaron).

## Qué es Proof of Gameplay

En vez de proteger el contenedor (el JSON), se trata de hacer que el
**contenido sea imposible de fabricar sin jugar de verdad**. La idea es
registrar suficiente telemetría de cada partida como para poder reproducir
la simulación y verificar que el resultado final (score, duración, records)
es físicamente consistente con los inputs registrados.

Un archivo falso necesitaría no solo inventar resultados, sino generar una
secuencia completa de inputs y estados físicos que produzcan exactamente esos
resultados al pasar por el motor de física del juego — algo órdenes de
magnitud más difícil que editar un JSON.

## Datos a registrar por sesión

Cada sesión guardaría, además de los datos actuales, un bloque de telemetría:

```json
{
  "replay": {
    "rng_seed": 48291,
    "physics_fps": 60,
    "inputs": [
      {"frame": 12, "type": "move", "y": 245},
      {"frame": 13, "type": "move", "y": 250},
      {"frame": 87, "type": "move", "y": 310}
    ],
    "ball_bounces": [
      {"frame": 45, "x": 780, "y": 203, "angle": 2.41},
      {"frame": 102, "x": 20, "y": 387, "angle": 0.73}
    ],
    "points": [
      {"frame": 150, "scorer": "player", "ball_x": 800, "ball_y": 195},
      {"frame": 312, "scorer": "computer", "ball_x": 0, "ball_y": 420}
    ],
    "checksum": "sha256 del bloque replay completo"
  }
}
```

### Campos clave

- **`rng_seed`**: semilla del generador aleatorio usada para la IA y la
  física. Con la misma semilla e inputs, la simulación es determinista.

- **`inputs`**: posición Y de la pala del jugador en cada frame donde hubo
  movimiento. No es necesario registrar todos los frames — solo los que
  tienen cambio de input (compresión delta).

- **`ball_bounces`**: posición y ángulo de cada rebote de la pelota. Sirven
  como checkpoints intermedios para validación rápida sin reproducir toda
  la simulación.

- **`points`**: frame exacto y posición de la pelota en cada punto anotado.

- **`checksum`**: hash del bloque replay, incluido en la cadena de hashes
  de la sesión para que no se pueda alterar independientemente.

## Proceso de verificacion

### Verificación completa (exhaustiva)

1. Inicializar el motor de física con `rng_seed` y `physics_fps`.
2. Alimentar los `inputs` frame a frame.
3. Simular la física completa (pelota, IA, colisiones).
4. Comparar cada punto anotado con `points` (frame, scorer, posición).
5. Comparar el score final con el registrado en la sesión.

Si la simulación no produce el mismo resultado, la sesión es falsa.

### Verificación rápida (checkpoints)

Para no reproducir toda la simulación (costoso en CPU):

1. Verificar que `ball_bounces` son físicamente plausibles:
   - Los ángulos de rebote son consistentes con las posiciones.
   - El tiempo entre rebotes es compatible con la velocidad de la pelota.
   - Las posiciones Y de los rebotes en los bordes laterales están dentro
     del rango de la pantalla.
2. Verificar que los `inputs` del jugador son humanamente plausibles:
   - La velocidad de movimiento de la pala no supera el máximo permitido.
   - No hay teletransportaciones (saltos de Y imposibles entre frames).

### Verificación estadística (heurística)

Para detección de anomalías sin reproducir la física:

- Distribución de tiempos de reacción (demasiado uniformes = bot).
- Varianza en la posición de impacto (demasiado perfecta = fabricado).
- Entropía de los inputs (demasiado baja = patrón repetitivo).

## Coste de implementación

| Aspecto | Impacto |
|---------|---------|
| **Tamaño del archivo** | Crece significativamente (~50-200 KB por sesión vs ~1 KB actual) |
| **Rendimiento en gameplay** | Mínimo (registrar inputs es trivial, ~1 dict.append por frame) |
| **Complejidad de código** | Alta (requiere motor de física determinista y replay system) |
| **Determinismo** | Crítico: el motor de física debe producir resultados idénticos en todas las plataformas, incluyendo operaciones de punto flotante |

## Desafío principal: determinismo de punto flotante

El mayor obstáculo técnico no es registrar los datos, sino garantizar que
la simulación sea **bitwise determinista** entre plataformas. Las operaciones
de punto flotante (float) pueden dar resultados ligeramente diferentes en:

- macOS vs Windows (diferentes compiladores, instrucciones FPU).
- Diferentes versiones de Python o pygame.
- Diferentes arquitecturas de CPU (x86 vs ARM).

**Mitigaciones posibles:**

- Usar aritmética de punto fijo (enteros) en vez de floats para la física.
- Acotar la verificación a checkpoints con tolerancia epsilon.
- Verificar solo propiedades cualitativas (orden de puntos, scorer) y no
  posiciones exactas.

## Por qué no se implementó

1. **Complejidad desproporcionada**: implementar un sistema de replay
   determinista es un proyecto en sí mismo, comparable en esfuerzo al
   propio juego.

2. **El juego no es competitivo**: PongIA es un prototipo de portafolio
   sin rankings online ni monetización. El incentivo para hacer trampa
   es mínimo.

3. **La protección actual es suficiente**: la cadena de hashes + HMAC
   disuade al 99% de los usuarios. El 1% restante haría trampa de todas
   formas con suficiente motivación.

4. **Valor como documentación**: explicar por qué una solución existe
   pero no se implementa demuestra más criterio de ingeniería que
   implementarla sin justificación.

## Conclusión

Proof of Gameplay es la única solución local que resiste el análisis del
código fuente y la generación asistida por IA. No protege el archivo —
hace que **fabricar datos válidos sea más difícil que jugar de verdad**.
Es el siguiente paso natural si PongIA evolucionara hacia un juego
competitivo con rankings públicos, pero para un prototipo de portafolio
la protección criptográfica actual es el equilibrio correcto entre
seguridad y complejidad.

---
---

# Adenda: Visión P2P descentralizada (propuesta conceptual)

## Motivación

La protección criptográfica actual (cadena de hashes + HMAC) y la propuesta
de Proof of Gameplay comparten una limitación fundamental: la autoridad de
verificación reside en el ordenador del usuario. Si el verificador y el
tramposo son la misma persona, ninguna protección local es definitiva.

La solución clásica es un servidor central que actúe como tercero de
confianza. Pero existe una alternativa: que **los propios jugadores se
verifiquen entre sí** mediante una red 'peer-to-peer' (P2P), eliminando la
necesidad de infraestructura centralizada. Esta adenda explora cómo
evolucionaría PongIA si se llevara esta idea a sus últimas consecuencias.

## Nivel 1: Verificación P2P de saves

### Concepto

Cada jugador publica el hash de su historial en una red de pares. Los demás
jugadores almacenan esos hashes. Si alguien modifica su archivo local, el
hash ya no coincide con lo que la red tiene registrado.

### Arquitectura

```
Jugador A                     Jugador B
+-----------------+           +-----------------+
| game_history    |           | game_history    |
| _hmac (local)   |           | _hmac (local)   |
+-----------------+           +-----------------+
        |                             |
        v                             v
+------------------------------------------------+
|            Red P2P (DHT / gossip)              |
|                                                |
|  hash_A = sha256(history_A)  [firmado por A]   |
|  hash_B = sha256(history_B)  [firmado por B]   |
|  hash_C = sha256(history_C)  [firmado por C]   |
+------------------------------------------------+
```

### Protocolo básico

1. Al completar una partida, el jugador calcula el hash de su historial.
2. Firma el hash con su clave privada (par de claves generado al instalar).
3. Publica el hash firmado en la red P2P.
4. Los peers almacenan el hash y lo comparan con publicaciones anteriores.
5. Si un jugador publica un hash incompatible con su historial previo
   (por ejemplo, un historial que crece pero el hash anterior no es prefijo
   del nuevo), la red lo marca como sospechoso.

### Tecnologías candidatas

- **libp2p**: framework de red P2P usado por IPFS y Ethereum 2.0.
- **DHT (Distributed Hash Table)**: almacenamiento clave-valor distribuido
  sin servidor central (tipo Kademlia).
- **Gossip protocol**: propagación de mensajes por difusión entre peers.

### Limitaciones de este nivel

- Requiere que haya jugadores conectados simultáneamente.
- PongIA es actualmente un juego offline contra IA — pocos peers disponibles.
- Un jugador nuevo sin peers no puede verificar a nadie ni ser verificado.

## Nivel 2: Rankings descentralizados

### Concepto

Los resultados de partidas se registran como transacciones en una estructura
de datos distribuida (blockchain ligera o DAG). Los rankings se calculan
por consenso: cada nodo tiene la misma información y llega al mismo resultado.

### Estructura de una "transacción de partida"

```json
{
  "player_id": "clave_publica_del_jugador",
  "session_hash": "sha256 de la sesion completa",
  "result": {
    "winner": "jugador",
    "score": "3-1",
    "duration_seconds": 245
  },
  "replay_checksum": "sha256 de la telemetria (Proof of Gameplay)",
  "timestamp": 1712234567,
  "previous_tx": "hash de la transaccion anterior del jugador",
  "signature": "firma con clave privada del jugador"
}
```

### Cálculo de rankings

Cada nodo calcula los rankings localmente a partir de todas las
transacciones validadas. Al ser determinista, todos llegan al mismo
resultado sin necesidad de un servidor que lo dicte:

- **Elo rating**: ajustado tras cada partida verificada.
- **Logros globales**: "Top 10 en rally más largo" calculado sobre
  todas las sesiones publicadas en la red.
- **Temporadas**: rankings que se reinician periódicamente por consenso
  (bloque genesis cada N días).

### Desafío: verificación sin repetir la partida

Los demás jugadores no pueden reproducir tu partida contra la IA (no
estaban ahí). Para confiar en el resultado sin servidor, las opciones son:

1. **Confiar en la firma + Proof of Gameplay**: si la telemetría es
   físicamente plausible y está firmada por el jugador, se acepta.
2. **Verificación por muestreo**: peers aleatorios reproducen un fragmento
   de la partida con la telemetría publicada y validan los checkpoints.
3. **Reputación**: jugadores con historial largo y consistente tienen
   más peso que cuentas nuevas.

## Nivel 3: Multijugador P2P

### Concepto

Dos jugadores juegan una partida de Pong directamente, sin servidor
intermedio. Cada jugador ejecuta la simulación localmente y se
sincronizan los inputs por red. Al terminar, ambos firman el resultado.

### Arquitectura de red

```
Jugador A                          Jugador B
+-------------+     UDP/WebRTC     +-------------+
| Simulacion  | <=================> | Simulacion  |
| Input A     |    intercambio     | Input B     |
| Render      |    de inputs       | Render      |
+-------------+                    +-------------+
       |                                  |
       v                                  v
  Firma resultado                   Firma resultado
       |                                  |
       +----------> Red P2P <-------------+
                  (resultado con
                  doble firma)
```

### Protocolo de partida

1. **Descubrimiento**: los jugadores se encuentran vía DHT o servidor
   de señalización ligero (solo para el handshake inicial, como WebRTC).
2. **Sincronización**: intercambio de inputs cada frame vía UDP.
   Cada jugador ejecuta la misma simulación determinista.
3. **Finalización**: al terminar, ambos jugadores firman el resultado.
   Si las simulaciones divergen, se usa la telemetría como arbitraje.
4. **Publicación**: el resultado con doble firma se publica en la red P2P.

### Desafíos técnicos

| Desafío | Descripción |
|---------|-------------|
| **NAT traversal** | La mayoría de jugadores están detrás de un router. Requiere STUN/TURN o hole punching para conexión directa |
| **Latencia** | Un juego de Pong requiere latencia <50ms para ser jugable. Limita el matchmaking a jugadores geográficamente cercanos |
| **Determinismo** | Ambas simulaciones deben producir resultados idénticos (mismo problema de punto flotante de la Adenda 1) |
| **Desconexión** | Si un jugador se desconecta a mitad de partida, hay que definir reglas de victoria/derrota por abandono |
| **Anti-cheat en tiempo real** | Un jugador podría modificar su cliente para mover la pala más rápido o ver el futuro de la pelota |

### Doble firma como prueba

Un resultado firmado por ambos jugadores es mucho más difícil de falsificar
que un resultado de un solo jugador contra la IA. Ambos tendrían que
cooperar para fabricar un resultado falso — y en un entorno competitivo
no tienen incentivo para hacerlo.

## Nivel 4: Economía tokenizada

### Concepto

Una criptomoneda o token asociado a PongIA que se otorga por victorias
verificadas y se usa para inscripciones en torneos, premios y gobernanza
de la comunidad.

### Arquitectura

```
+------------------+
|  Blockchain      |  (Polygon, Solana, o L2 propia)
|  Smart Contracts |
+------------------+
        |
        |--- Contrato de Token (ERC-20 / SPL)
        |    - Emision por victoria verificada
        |    - Transferencia entre jugadores
        |
        |--- Contrato de Torneo
        |    - Inscripcion (deposito de tokens)
        |    - Bracket automatico
        |    - Distribucion de premios al ganador
        |    - Arbitraje por Proof of Gameplay
        |
        |--- Contrato de Gobernanza
             - Votacion sobre reglas del juego
             - Propuestas de la comunidad
             - Actualizaciones de parametros
```

### Flujo de un torneo

1. El organizador despliega un contrato de torneo con reglas (formato,
   premio, fecha).
2. Los jugadores se inscriben depositando tokens en el contrato.
3. El contrato genera el bracket aleatoriamente (semilla del bloque).
4. Las partidas se juegan P2P con doble firma.
5. Los resultados firmados se envían al contrato como prueba.
6. El contrato verifica las firmas y avanza el bracket.
7. Al finalizar, el contrato distribuye los tokens al ganador automáticamente.

Ningún intermediario toca los fondos. El smart contract es el árbitro.

## Mapa de complejidad

```
Nivel 1 ──── Nivel 2 ──── Nivel 3 ──── Nivel 4
Verificacion   Rankings     Multijugador  Economia
P2P saves      descentral.  P2P           tokenizada

Complejidad:   ████         ████████      ████████████  ████████████████
Valor usuario: ██           ████████      ████████████  ████████████████
Dependencias:  libp2p       blockchain    networking    smart contracts
                            ligera        UDP/WebRTC    
```

Cada nivel presupone el anterior. No tiene sentido implementar rankings
sin verificación, ni torneos sin multijugador, ni economía sin torneos.

## Por qué no se implementa

1. **Desproporción total**: PongIA es un prototipo de portafolio. Implementar
   una red P2P con blockchain sería invertir 10x más esfuerzo en la
   infraestructura que en el propio juego.

2. **Masa crítica**: una red P2P necesita jugadores simultáneos para
   funcionar. Con la base de usuarios actual, la red estaría vacía.

3. **El juego no lo necesita**: PongIA es un juego contra IA para un solo
   jugador. La competición entre jugadores no es parte de su propuesta
   de valor actual.

## Valor como visión

Esta propuesta no pretende ser implementada en PongIA tal como es hoy.
Su valor es demostrar la capacidad de:

- **Pensar en sistemas**: ver cómo un problema local (proteger un JSON)
  escala hasta una economía descentralizada.
- **Evaluar trade-offs**: cada nivel tiene un coste y un beneficio
  concreto, y saber dónde detenerse es tan importante como saber
  cómo continuar.
- **Conectar dominios**: criptografía, redes P2P, teoría de juegos y
  economía de tokens — todo partiendo de un Pong.

La línea entre un buen ingeniero y uno excelente no es lo que sabe
implementar, sino lo que sabe que **no debe** implementar todavía.

---
---

# Adenda: Estimación de tiempos y el factor IA (especulación)

## Tiempos estimados hoy (abril 2026, desarrollador en solitario)

| Nivel | Alcance | Estimación |
|-------|---------|------------|
| Proof of Gameplay | Replay determinista, registro de telemetría, verificación | 3-6 semanas |
| Nivel 1: Verificación P2P | Networking básico, DHT, protocolo de hashes | 2-3 meses |
| Nivel 2: Rankings descentralizados | Blockchain ligera, consenso, UI de rankings | 4-6 meses |
| Nivel 3: Multijugador P2P | NAT traversal, sincronización, anti-cheat | 6-12 meses |
| Nivel 4: Economía tokenizada | Smart contracts, integración wallet, asesoría legal | 12+ meses |

Estas estimaciones asumen un desarrollador trabajando en solitario a
tiempo parcial, aprendiendo las tecnologías sobre la marcha. El grueso
del tiempo no es escribir código sino entender los dominios (networking,
criptografía, consenso distribuido) lo suficiente como para tomar buenas
decisiones de diseño.

## El factor IA: cómo cambia esto

Este proyecto (PongIA) se desarrolló íntegramente con asistencia de
Claude Code. El sistema de integridad criptográfica documentado en este
informe — diseño, implementación, tests, iteración sobre vectores de
ataque y documentación — se completó en una sola sesión de trabajo.

Eso era impensable hace dos años. Y la tendencia no se detiene.

### Proyección con la evolución de modelos

**Hoy (Claude Opus 4.6, abril 2026):**
La IA asiste al desarrollador. Escribe código, sugiere arquitecturas,
encuentra bugs. Pero el humano toma las decisiones de diseño, valida
cada paso y entiende el sistema completo. El ratio es aproximadamente
70% IA / 30% humano en escritura de código, pero 100% humano en
dirección y criterio.

**Corto plazo (meses, ~Opus 4.7-4.8 o equivalentes):**
Modelos con mayor capacidad de contexto y razonamiento podrían manejar
la implementación de Proof of Gameplay y el Nivel 1 (P2P básico) con
supervisión humana mínima. El desarrollador define el qué y la IA
resuelve el cómo, incluyendo la integración entre subsistemas. Las
3-6 semanas del Proof of Gameplay podrían comprimirse a días.

**Medio plazo (1-2 años, modelos de nueva generación):**
Agentes de IA capaces de mantener proyectos completos en contexto,
ejecutar builds, correr tests, iterar autónomamente y proponer
arquitecturas distribuidas. Los niveles 2 y 3 (rankings y multijugador
P2P) podrían pasar de meses a semanas. El desarrollador se convierte
en director de proyecto y revisor de código más que en escritor.

**Largo plazo (especulativo):**
El Nivel 4 (economía tokenizada) seguiría requiriendo decisión humana
por el diseño de incentivos — la IA puede
escribir un smart contract, pero decidir si debería existir es una
pregunta humana (todavía).

### Lo que "no se debe" implementar hoy, mañana podría implementarse

La razón por la que estos niveles se descartan hoy no es solo técnica, es económica. 
El coste en tiempo de un desarrollador en solitario
supera el beneficio para un prototipo de portafolio.

Pero si la IA comprime esos tiempos un orden de magnitud, la ecuación
cambia. Lo que hoy es "desproporcionado" podría ser "una tarde de
trabajo" con las herramientas adecuadas. El criterio de "no implementar"
no desaparece — se recalibra con cada generación de modelos.

Este documento, escrito en abril de 2026, es en sí mismo una cápsula
del tiempo. Invitamos al lector futuro a evaluar cuánto de lo aquí
especulado se quedó corto, pongamos, para 2030.

(El autor de estas líneas ya tiene [otra apuesta abierta](secrets.md)
sobre si un LLM podrá jugar a Pong a 60 FPS antes de 2030. Si estás
leyendo esto en el futuro y la IA ya implementó la red P2P, los
rankings descentralizados y la economía tokenizada en una tarde —
por favor, que alguien me cobre también esa.)
