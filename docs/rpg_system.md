# Sistema RPG de PongIA

Documentación técnica del sistema de progresión RPG implementado el 3 de abril de 2026.
Referencia para futuras ampliaciones o modificaciones.

---

## Arquitectura general

El sistema sigue el patrón **mixin** del resto del proyecto:

```
pong/config/rpg.py          Constantes: tabla de niveles, definiciones de habilidades
pong/config/ui_rpg.py       Constantes de UI: colores, dimensiones de tarjetas y botones
pong/rpg_engine.py           Motor RPG puro (RPGState dataclass, logica de compra/ascension)
pong/game_rpg.py             GameRPGMixin — integra RPG en el game loop
pong/renderer_rpg.py         RPGRendererMixin — dibujado de barra XP, pantallas overlay
```

**Dependencias entre archivos:**

```
config/rpg.py  <--  rpg_engine.py  <--  game_rpg.py  <--  game.py
config/ui_rpg.py  <--  renderer_rpg.py  <--  renderer.py
```

`rpg_engine.py` es el único archivo que contiene lógica de negocio RPG.
Los mixins (`game_rpg.py` y `renderer_rpg.py`) solo orquestan llamadas al engine.

---

## Tres capas de progresión

### 1. XP y niveles (50 niveles)

- **Desbloqueo**: 600 segundos de juego acumulado (`RPG_UNLOCK_TOTAL_SECONDS`).
- **Fórmula**: `xp(n) = round(5 * n^2 + 5 * n)` donde `n = nivel - 1`.
- La XP se mide en **segundos reales de juego**, multiplicados por `get_xp_multiplier()`.
- **Barra de XP**: zona de 22px entre el área de juego y la narración (`XP_BAR_TOP = 544`).
- La ventana mide 766px de alto (44 score + 500 game + 22 xp + 200 narration).

### 2. Habilidades normales (10)

Se compran con **skill_seconds** (segundos de juego acumulados como moneda).
Se desbloquean por nivel. **Se pierden al ascender.**

| ID | Nombre | Coste | Nivel | Efecto |
|----|--------|-------|-------|--------|
| `spin` | Efecto en la pelota | 1s | 2 | Spin proporcional a posición de impacto |
| `directional` | Control direccional | 1s | 4 | Rebote según movimiento de pala |
| `wider_paddle` | Pala ampliada | 1s | 6 | +12px altura de pala |
| `fast_reaction` | Reacción veloz | 2s | 9 | +2 velocidad de pala |
| `tense_shot` | Golpe tenso | 2s | 12 | x1.25 velocidad de pelota |
| `auto_reflex` | Reflejo automático | 2s | 16 | x1.2 velocidad si golpea borde de pala |
| `xp_bonus` | Bonificación XP | 2s | 20 | x1.5 multiplicador de XP |
| `curved_shot` | Disparo curvo | 3s | 25 | Drift sinusoidal durante 2s |
| `double_impulse` | Doble impulso | 3s | 32 | x1.3 velocidad tras anotar punto |
| `dual_instinct` | Instinto dual | 5s | 40 | 15% prob. de duplicar pelota |

### 3. Habilidades de ascensión (10, hasta 10 niveles cada una)

Se compran con **ascensión points** (AP = puntos anotados al ordenador).
**Permanentes**: sobreviven a la ascensión. Cada habilidad tiene hasta 10 niveles.

**Coste del nivel N** = `base_cost * N`

| ID | Nombre | Base | Efecto por nivel |
|----|--------|------|------------------|
| `veteran_start` | Inicio veterano | 1 AP | XP x(1.0 + 0.1 * N) |
| `persistent_memory` | Memoria persistente | 1 AP | +3N s XP al anotar |
| `legacy_paddle` | Pala de legado | 2 AP | +8N px pala |
| `rival_reading` | Lectura del rival | 2 AP | Trayectoria 40N px |
| `master_spin` | Efecto maestro | 2 AP | Efectos x(1.0 + 0.2 * N) |
| `superior_reflex` | Reflejo superior | 3 AP | +N velocidad pala |
| `hacker` | Hacker | 3 AP | IA falla (10+3N)%, offset 5-(10+3N) px |
| `critical_hit` | Golpe crítico | 3 AP | (10+3N)% prob, x(1.5+0.1N) mult |
| `victory_echo` | Eco de victoria | 4 AP | +5N s habilidad al anotar |
| `sovereign` | Ascensión soberana | 5 AP | Conservar 5N% XP, 8N% segundos |

---

## Mecánica de ascensión

1. **Requisito**: `ascension_points_total >= 10` (ASCENSION_MIN_POINTS).
2. **Flujo UI**: Botón "Ascender" (end screen) -> Diálogo de confirmación -> Pantalla de ascensión (sin volver) -> Botón ASCENDER -> Pantalla de título -> Jugar.
3. **Qué hace `perform_ascension()`**:
   - `level = 1`
   - `total_xp_seconds *= keep_xp_ratio` (0% sin sovereign, 5% por nivel)
   - `skill_seconds_balance *= keep_seconds_ratio` (0% sin sovereign, 8% por nivel)
   - `purchased_skills.clear()` (se pierden las normales)
   - `ascension_count += 1`
   - `ascension_points_available += 1` (bonus por ascender)
   - Las habilidades de ascensión **NO se pierden**.
4. **Irreversible**: una vez aceptado el diálogo de confirmación, el jugador solo puede comprar habilidades de ascensión y pulsar ASCENDER. No hay botón "Volver".

---

## Persistencia

### Dónde se guarda

En `saves/game_history.json`, clave `"rpg"`:

```json
{
  "rpg": {
    "rpg_unlocked": true,
    "level": 15,
    "total_xp_seconds": 1234.56,
    "skill_seconds_balance": 89.30,
    "purchased_skills": ["spin", "directional", "wider_paddle"],
    "ascension_count": 2,
    "ascension_points_total": 47,
    "ascension_points_available": 12,
    "purchased_ascension_skills": {
      "veteran_start": 3,
      "legacy_paddle": 1
    }
  }
}
```

### Cuándo se guarda

- **Cada compra/ascensión**: `_rpg_persist_now()` escribe inmediatamente a disco.
  No depende de `_save_game()` (que espera al resumen LLM).
- **Fin de partida**: `_save_game()` también persiste `rpg_data` vía `save_session()`.
- **Tick de XP**: NO se persiste cada frame. Se guarda al final de la partida o al comprar.

### Migración de datos

- `save_manager.py` version `"1.3"`: añade `"rpg": {}` al historial si falta.
- `RPGState.from_dict()` migra el formato antiguo de `purchased_ascension_skills`
  (lista de strings) al nuevo (dict de string -> int con niveles).

---

## Layout de ventana

```
y=0    +---------------------------+
       |     Banda marcador (44px) |
y=44   +---------------------------+
       |                           |
       |    Area de juego (500px)  |
       |                           |
y=544  +---------------------------+
       |    Barra de XP RPG (22px) |
y=566  +---------------------------+
       |                           |
       |    Narracion (200px)      |
       |                           |
y=766  +---------------------------+
```

Constantes en `pong/config/layout.py`:
- `XP_BAR_TOP = 544`, `XP_BAR_HEIGHT = 22`
- `NARRATION_TOP = 566`, `WINDOW_HEIGHT = 766`

---

## Pantallas overlay (UI)

Ambas son overlays a pantalla completa dibujados por `renderer_rpg.py`.

### Pantalla de habilidades (magenta)

- Acceso: botón "Habilidades" en end screen.
- Muestra 10 tarjetas (760x52px) con estados: bloqueada / disponible / comprada.
- Cada tarjeta tiene nombre, descripción, botón COMPRAR con coste en segundos.
- Scroll con flechas arriba/abajo. Botón "Volver" para cerrar.

### Pantalla de ascensión (dorada)

- Acceso: botón "Ascender" en end screen -> diálogo confirmación -> aceptar.
- Muestra 10 tarjetas (760x44px) con nivel actual (Nv. X/10) y botón con coste AP.
- Tarjetas al máximo muestran "MAX" en vez de botón de compra.
- **Sin botón "Volver"** — solo botón ASCENDER al final.
- Scroll con flechas.

### Diálogo de confirmación

- Overlay semitransparente sobre el end screen.
- Caja centrada (500x220px) con título, advertencia y botones Aceptar/Cancelar.
- Se puede cerrar con ESC (equivale a Cancelar).

---

## Hooks en el game loop

El mixin `GameRPGMixin` inyecta lógica en estos puntos de `game.py`:

| Punto de inyección | Método | Qué hace |
|----|--------|---------|
| `_prepare_match()` | `_init_rpg()` | Carga estado RPG del JSON |
| `update()` (cada frame) | `_rpg_update(dt)` | Tick XP, curva, bolas extra |
| Colisión jugador-pelota | `_rpg_on_player_collision()` | Spin, direccional, crítico, etc. |
| Punto anotado | `_rpg_on_point_scored(winner)` | AP, bonus XP/segundos, doble impulso |
| `_restart_match()` | `_init_rpg()` | Recarga estado RPG |
| `draw()` | `draw_xp_bar()`, `draw_trajectory_prediction()` | Visual durante gameplay |

---

## Bugs conocidos y soluciones aplicadas

### Persistencia de compras (resuelto)

**Problema**: las compras se perdían al reiniciar partida porque `_save_game()` tiene
un guard `if self.game_saved: return` y podía ejecutarse antes de que el jugador comprara.

**Solución**: `_rpg_persist_now()` escribe directamente a disco en cada compra,
sin depender del ciclo normal de guardado.

### Botón ASCENDER fuera de ventana (resuelto)

**Problema**: 10 tarjetas de 52px + márgenes excedían 766px.

**Solución**: reducir tarjetas de ascensión a 44px alto, 3px gap (en `ui_rpg.py`).

### Ascensiones múltiples (resuelto)

**Problema**: al pulsar ASCENDER, se quedaba en la pantalla permitiendo pulsar de nuevo.

**Solución**: tras ascender, cerrar pantalla y mostrar pantalla de título (ZXTitleScreen).
El jugador debe pulsar "Jugar" para iniciar nueva partida.

### Comprar skills de ascensión sin ascender (resuelto)

**Problema**: el jugador podía entrar a la pantalla de ascensión, gastar AP y volver sin ascender.

**Solución**: flujo irreversible con diálogo de confirmación previo.
La pantalla de ascensión no tiene botón "Volver".

---

## Ideas para futuras ampliaciones

- **Más habilidades normales**: añadir a `RPG_SKILLS` en `config/rpg.py`. Solo requiere
  un getter en `rpg_engine.py` y el hook correspondiente en `game_rpg.py`.
- **Más habilidades de ascensión**: añadir a `RPG_ASCENSION_SKILLS`. La UI las muestra
  automáticamente. Añadir getter en `rpg_engine.py`.
- **Balanceo**: todos los números de escalado están centralizados en `config/rpg.py`
  y en los getters de `rpg_engine.py`. Ajustar sin tocar la UI.
- **Achievements ligados al RPG**: comprobar `rpg.level`, `rpg.ascension_count`, etc.
  en el sistema de logros existente.
- **Efectos visuales de ascensión**: animación especial al ascender (en `renderer_rpg.py`).
- **Habilidades con cooldown**: el timer de curva (`_rpg_curve_timer`) es un precedente.
- **Tests unitarios del RPG engine**: `RPGState` es una dataclass pura, fácil de testear
  sin pygame. Probar `tick_xp()`, `buy_skill()`, `perform_ascension()`, etc.
