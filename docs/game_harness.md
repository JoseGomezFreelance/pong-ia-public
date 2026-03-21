# GameHarness -- Testing programatico del juego

El `GameHarness` permite ejecutar Pong sin ventana visible, controlar el
juego frame a frame, inyectar inputs de teclado, leer el estado completo y
capturar screenshots del renderizado. Es util para:

- Tests automatizados (pytest) que verifican logica de juego.
- Simulacion de partidas completas para detectar bugs.
- Captura de screenshots para regresion visual.
- Pruebas con LLM e imagegen sin necesidad de interfaz grafica.


## API rapida

### HeadlessConfig

Controla que subsistemas se activan:

```python
from pong.harness import HeadlessConfig

config = HeadlessConfig(
    enable_narration=False,   # Cargar el LLM narrador (Qwen 2.5 3B)
    enable_music=False,       # Inicializar motor musical MIDI
    enable_sound=False,       # Inicializar efectos de sonido
    enable_imagegen=False,    # Habilitar Stable Diffusion
    skip_splash=True,         # Saltar terminal de carga y portada
)
```

Por defecto todo esta desactivado para tests rapidos. Los subsistemas
desactivados se reemplazan por null objects que implementan la misma interfaz
sin hacer nada.

### GameHarness

```python
from pong.harness import GameHarness

harness = GameHarness.create(config)   # o sin config para defaults
harness.step(60)                       # avanzar 60 frames
harness.press_keys([pygame.K_UP])      # pulsar tecla
harness.release_all_keys()             # soltar todas
state = harness.get_state()            # leer estado completo
frame = harness.capture_frame()        # obtener Surface (800x744)
harness.save_screenshot("/tmp/f.png")  # guardar como PNG
harness.close()                        # limpiar recursos
```

Tambien funciona como context manager:

```python
with GameHarness.create() as h:
    h.step(60)
    print(h.get_state())
```


## Ejemplo basico

Script minimo que arranca el juego, avanza 1 segundo y captura un screenshot:

```python
from pong.harness import GameHarness

with GameHarness.create() as h:
    h.step(60)  # 60 frames = 1 segundo a 60fps
    state = h.get_state()
    print(f"Bola en ({state['ball']['x']}, {state['ball']['y']})")
    print(f"Score: {state['score']}")
    h.save_screenshot("/tmp/pong_frame.png")
```

Para resultados reproducibles, fijar la semilla aleatoria:

```python
import random
random.seed(42)
harness = GameHarness.create()
```


## Jugar una partida automatizada

Ejemplo completo de una partida con estrategia "humana imperfecta" que
produce puntos y termina. La estrategia alterna entre seguir la bola (modo
activo) y despistarse (modo distraido):

```python
import random
import pygame
from pong.harness import GameHarness

random.seed(777)
harness = GameHarness.create()

mode = "playing"
mode_timer = 0
frames = 0

while frames < 60 * 600:  # maximo 10 minutos
    state = harness.get_state()
    if not state["running"] or state["showing_end_screen"]:
        break

    # --- Alternar modo ---
    mode_timer -= 1
    if mode_timer <= 0:
        if mode == "playing":
            if random.random() < 0.35:
                mode = "distracted"
                mode_timer = random.randint(20, 50)
            else:
                mode_timer = random.randint(30, 90)
        else:
            mode = "playing"
            mode_timer = random.randint(40, 120)

    # --- Decidir input ---
    ball_y = state["ball"]["y"]
    ball_sx = state["ball"]["speed_x"]
    paddle_center = state["player"]["y"] + 40  # mitad de paleta (80px)

    if mode == "playing" and ball_sx < 0:
        # Bola viene hacia nosotros: seguirla
        diff = ball_y - paddle_center
        if diff < -10:
            harness.press_keys([pygame.K_UP])
        elif diff > 10:
            harness.press_keys([pygame.K_DOWN])
        else:
            harness.release_all_keys()
    elif mode == "distracted":
        # Mover aleatoriamente
        r = random.random()
        if r < 0.3:
            harness.press_keys([pygame.K_UP])
        elif r < 0.6:
            harness.press_keys([pygame.K_DOWN])
        else:
            harness.release_all_keys()
    else:
        harness.release_all_keys()

    harness.step(1)
    frames += 1

    # Fin de partido
    score = state["score"]
    if score["player_sets"] >= 1 or score["computer_sets"] >= 1:
        break

harness.save_screenshot("/tmp/pong_final.png")
print(harness.get_state()["score"])
harness.close()
```

**Nota sobre estrategia perfecta:** Si la paleta del jugador sigue la bola
sin errores, el rally se extiende indefinidamente (se han observado rallies
de 257+ golpes sin que nadie anote). Esto ocurre porque la IA del ordenador
tampoco falla. Para producir puntos, la estrategia debe incluir periodos de
inactividad o movimiento aleatorio.


## Partida con LLM e imagegen

Para probar con todos los subsistemas activos (narrador IA, generador de
imagenes), hay que tener en cuenta que el tiempo del juego depende de
`time.monotonic()`. Como `step()` no llama `clock.tick()`, los frames corren
a velocidad maxima y el reloj real apenas avanza. Los subsistemas que usan
temporizadores (narracion cada 8s, imagegen a los 180s) necesitan que pase
tiempo real.

Solucion: intercalar `time.sleep()` entre batches de frames para que el
reloj real avance al ritmo del juego:

```python
import time
from pong.harness import GameHarness, HeadlessConfig

config = HeadlessConfig(
    enable_narration=True,    # Cargar LLM (~3-5s de inicializacion)
    enable_imagegen=True,     # Habilitar Stable Diffusion
    enable_music=False,
    enable_sound=False,
    skip_splash=True,
)

harness = GameHarness.create(config)

BATCH = 6       # frames por iteracion (~0.1s de juego)
SLEEP = 0.1     # pausa real entre iteraciones (ratio ~1:1)

last_narration = ""

for _ in range(27000):  # ~4.5 minutos reales
    # ... logica de input (ver ejemplo anterior) ...

    harness.step(BATCH)
    time.sleep(SLEEP)

    # Detectar nueva narracion
    state = harness.get_state()
    if state["narration_text"] != last_narration:
        print(f"[LLM] {state['narration_text']}")
        last_narration = state["narration_text"]

harness.close()
```

**Tiempos de referencia** (observados en pruebas):

| Evento                     | Tiempo real |
|----------------------------|-------------|
| Inicializacion LLM         | ~3-5s       |
| Primera narracion           | ~3s         |
| Narraciones periodicas     | cada ~8s    |
| Activacion imagegen        | ~180s (3 min) |
| Generacion de imagen SD    | ~15-30s     |
| Partida completa con LLM   | ~4-5 min    |


## Testing interactivo frame a frame

Si necesitas inspeccionar un bug visual especifico, puedes usar el harness
desde un script o desde la consola de un agente para avanzar
frame a frame, ver screenshots y tomar decisiones:

```python
import pygame
from pong.harness import GameHarness

h = GameHarness.create()

# Avanzar hasta un momento interesante
h.step(300)  # 5 segundos
h.save_screenshot("/tmp/debug_01.png")
# --> Leer /tmp/debug_01.png para ver el estado visual

# Inyectar input y avanzar poco a poco
h.press_keys([pygame.K_DOWN])
h.step(10)
h.save_screenshot("/tmp/debug_02.png")
# --> Leer /tmp/debug_02.png, comparar con el anterior

# Inyectar un evento discreto (por ejemplo, pausar)
h.inject_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_p))
h.step(1)
h.save_screenshot("/tmp/debug_03.png")
# --> Verificar que la pausa se activo visualmente

h.close()
```

## Hallazgos y notas tecnicas

### Rallies infinitos

Cuando ambas paletas (jugador y ordenador) siguen la bola sin error, la
partida entra en un punto muerto indefinido. Se han observado rallies de
129 y 257 golpes sin que nadie anote. Esto es un comportamiento emergente
de la fisica del juego: la bola no acelera y los angulos son predecibles.

### Tiempo real vs tiempo de juego

`step()` **no** llama `clock.tick()`. Los frames corren a velocidad maxima
del CPU. Esto significa:

- 18.000 frames (5 min de juego a 60fps) se ejecutan en ~8 segundos reales.
- `time.monotonic()` avanza por reloj de pared, no por frames simulados.
- Funcionalidades con delay (preguntas a los 30s, musica a los 30s, imagegen
  a los 180s) se activan segun el tiempo real transcurrido.
- La deteccion de inactividad del jugador (`idle_score`) tambien usa tiempo
  real, por lo que se activa muy rapido en modo headless.

Para tests de logica pura (colisiones, scoring, movimiento), esto no importa.
Para tests que involucren timing (narracion, imagegen, emociones), usar
`time.sleep()` entre batches.

### _FakeKeyState y pygame 2 (SDL2)

En Pygame 2, las constantes de tecla como `pygame.K_UP` son valores grandes
(~1073741906, scancodes SDL2), no indices de una lista de 512 elementos.
`pygame.key.get_pressed()` retorna un `ScancodeWrapper` que convierte
internamente. El harness usa `_FakeKeyState`, un objeto cuyo `__getitem__`
simplemente comprueba pertenencia a un `set`:

```python
class _FakeKeyState:
    def __init__(self, pressed):
        self._pressed = pressed
    def __getitem__(self, key):
        return key in self._pressed
```

### SDL dummy driver

El harness configura `SDL_VIDEODRIVER=dummy` y `SDL_AUDIODRIVER=dummy` antes
de `pygame.init()`. Esto crea un `Surface` real de 800x744 que se puede
renderizar y leer, pero sin crear ventana ni inicializar audio. Las llamadas
a `pygame.display.flip()` se convierten en no-ops silenciosos. No hace falta
modificar el renderer.


## Referencia de get_state()

`harness.get_state()` retorna un diccionario con esta estructura:

```python
{
    "ball": {
        "x": int,        # posicion horizontal del rect
        "y": int,        # posicion vertical del rect
        "speed_x": int,  # velocidad horizontal (+ = derecha)
        "speed_y": int,  # velocidad vertical (+ = abajo)
    },
    "player": {
        "x": int,        # posicion horizontal de la paleta izquierda
        "y": int,        # posicion vertical (top del rect)
    },
    "computer": {
        "x": int,        # posicion horizontal de la paleta derecha
        "y": int,        # posicion vertical (top del rect)
    },
    "score": {
        "player_points": int,    # 0-2 (3 = gana juego)
        "computer_points": int,
        "player_games": int,     # 0-1 (2 = gana set)
        "computer_games": int,
        "player_sets": int,      # 0 (1 = gana partido)
        "computer_sets": int,
    },
    "rally_hits": int,           # golpes en el rally actual
    "max_rally_hits": int,       # record del partido
    "paused": bool,
    "showing_end_screen": bool,
    "running": bool,             # False = juego cerrado
    "narration_text": str,       # ultimo texto del narrador
    "elapsed_seconds": float,    # segundos reales desde inicio
    "emotion": {
        "aggressiveness": float, # 0.0-1.0
        "stability": float,     # 0.0-1.0
        "motivation": float,    # 0.0-1.0
        "mood_tag": str,         # "neutral", "aburrido", etc.
    },
}
```

### Dimensiones de referencia

| Elemento        | Valor       |
|-----------------|-------------|
| Ventana         | 800 x 744   |
| Zona de juego   | 800 x 500   |
| Paleta          | 15 x 80     |
| Bola            | 12 x 12     |
| Zona narracion  | 800 x 200   |
| Banda marcador  | 800 x 44    |
