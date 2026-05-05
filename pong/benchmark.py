"""Benchmark de rendimiento: partida demo IA vs IA con LLM activo.

Ejecuta un bucle de pygame independiente durante ~45 segundos donde dos
paletas controladas por IA juegan entre si mientras el LLM genera
narraciones en segundo plano.  Mide FPS y latencia LLM para decidir si
el modelo seleccionado es viable en el hardware del usuario.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass
from typing import Any

import pygame

from pong.config.colors import COLOR_BACKGROUND, COLOR_FOREGROUND
from pong.config.gameplay import (
    AI_SPEED,
    BALL_SIZE,
    FPS,
    PADDLE_HEIGHT,
    PADDLE_MARGIN,
    PADDLE_WIDTH,
)
from pong.config.layout import (
    CENTER_DASH_GAP,
    CENTER_DASH_HEIGHT,
    CENTER_DASH_WIDTH,
    GAME_AREA_HEIGHT,
    GAME_AREA_TOP,
    SCORE_BAND_HEIGHT,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)
from pong.config.models import LLMModelConfig
from pong.config.zx_spectrum import (
    ZX_BLACK,
    ZX_CYAN_BRIGHT,
    ZX_GRAY_DARK,
    ZX_GRAY_LIGHT,
    ZX_GREEN_BRIGHT,
    ZX_RED_BRIGHT,
    ZX_WHITE,
    ZX_YELLOW,
)
from pong.entities import Ball, Paddle
from pong.perf import PerformanceMetrics

logger = logging.getLogger(__name__)

__all__ = ["BenchmarkResult", "run_benchmark"]


# ============================================================
# Resultado
# ============================================================

@dataclass
class BenchmarkResult:
    """Resultado del benchmark."""

    fps_avg: float
    fps_min: float
    llm_avg_ms: float
    llm_calls_completed: int
    passed: bool
    reason: str  # "" si paso, explicacion si fallo


# ============================================================
# Constantes del benchmark
# ============================================================

BENCHMARK_DURATION_S: int = 45
BENCHMARK_FPS_MIN: float = 30.0
BENCHMARK_LLM_MAX_MS: float = 5000.0
_LLM_CALL_INTERVAL_S: float = 8.0


# ============================================================
# Benchmark principal
# ============================================================

def run_benchmark(
    screen: pygame.Surface,
    llm_config: LLMModelConfig,
) -> BenchmarkResult | None:
    """Ejecuta el benchmark con partida demo IA vs IA.

    Toma control del display durante ~45 segundos.

    Args:
        screen: Superficie principal de pygame.
        llm_config: Configuracion del modelo LLM a probar.

    Returns:
        ``BenchmarkResult`` con los resultados, o ``None`` si el usuario
        cancela con ESC.
    """
    # -- Pre-cargar el modelo LLM (no cuenta para el benchmark) --
    status_font = pygame.font.SysFont("Courier", 20)
    _draw_loading_screen(screen, status_font, "Cargando modelo LLM...")
    pygame.display.flip()

    provider = _load_provider(llm_config)
    if provider is None:
        return BenchmarkResult(
            fps_avg=0, fps_min=0, llm_avg_ms=0,
            llm_calls_completed=0, passed=False,
            reason="No se pudo cargar el modelo LLM",
        )

    # -- Preparar entidades --
    left_paddle = Paddle(
        PADDLE_MARGIN,
        GAME_AREA_HEIGHT // 2 - PADDLE_HEIGHT // 2,
    )
    right_paddle = Paddle(
        WINDOW_WIDTH - PADDLE_MARGIN - PADDLE_WIDTH,
        GAME_AREA_HEIGHT // 2 - PADDLE_HEIGHT // 2,
    )
    ball = Ball()
    perf = PerformanceMetrics()

    score_left = 0
    score_right = 0

    # -- Estado LLM en background --
    llm_lock = threading.Lock()
    llm_busy = False
    llm_last_text = ""
    llm_last_ms: float = 0.0
    last_llm_call_time = 0.0

    # -- Fuentes --
    banner_font = pygame.font.SysFont("Courier", 22)
    score_font = pygame.font.Font(None, 48)
    info_font = pygame.font.SysFont("Courier", 18)
    if info_font.get_height() < 10:
        info_font = pygame.font.Font(None, 18)

    clock = pygame.time.Clock()
    start_time = time.monotonic()
    cancelled = False

    # -- Estado errático para la paleta izquierda ("jugador") --
    # Hace la demo más entretenida: la paleta izquierda comete errores,
    # varía velocidad y a veces se distrae, evitando rallies infinitos.
    erratic_offset = 0.0          # offset vertical respecto a la bola
    erratic_speed_factor = 0.8    # multiplicador de velocidad
    erratic_paused = False         # si está "distraída" y no se mueve
    erratic_next_change = start_time + random.uniform(0.8, 1.5)

    while True:
        now = time.monotonic()
        elapsed = now - start_time

        if elapsed >= BENCHMARK_DURATION_S:
            break

        # -- Eventos --
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                cancelled = True
                break
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                cancelled = True
                break

        if cancelled:
            return None

        # -- IA para ambas paletas --

        # Izquierda: comportamiento errático para que la demo sea entretenida
        if now >= erratic_next_change:
            erratic_next_change = now + random.uniform(0.8, 2.0)
            roll = random.random()
            if roll < 0.15:
                # ~15%: se distrae, no se mueve
                erratic_paused = True
                erratic_next_change = now + random.uniform(0.5, 1.5)
            elif roll < 0.25:
                # ~10%: vuelve al centro (pierde posición)
                erratic_paused = False
                erratic_offset = GAME_AREA_HEIGHT // 2 - ball.rect.centery
                erratic_speed_factor = random.uniform(0.5, 0.8)
            else:
                # ~75%: sigue la bola pero con offset e imprecisión
                erratic_paused = False
                erratic_offset = random.uniform(-70, 70)
                erratic_speed_factor = random.uniform(0.4, 1.0)

        if not erratic_paused:
            erratic_target = ball.rect.centery + int(erratic_offset)
            erratic_spd = max(1, int(AI_SPEED * erratic_speed_factor))
            left_paddle.move_toward(erratic_target, erratic_spd)

        # Derecha: velocidad normal
        right_paddle.move_toward(ball.rect.centery, AI_SPEED)

        # -- Actualizar bola --
        ball.update()

        # -- Colisiones --
        ball.check_paddle_collision(left_paddle)
        ball.check_paddle_collision(right_paddle)

        # -- Gol: bola sale por los lados --
        if ball.rect.left <= 0:
            score_right += 1
            ball.reset()
        elif ball.rect.right >= WINDOW_WIDTH:
            score_left += 1
            ball.reset()

        # -- Llamada LLM periodica --
        with llm_lock:
            is_busy = llm_busy

        if not is_busy and (now - last_llm_call_time) >= _LLM_CALL_INTERVAL_S:
            last_llm_call_time = now
            with llm_lock:
                llm_busy = True

            def _llm_task(
                _provider: object = provider,
                _perf: PerformanceMetrics = perf,
                _lock: threading.Lock = llm_lock,
            ) -> None:
                nonlocal llm_last_text, llm_last_ms, llm_busy
                t0 = time.perf_counter()
                text = _run_llm_call(_provider)
                dur = time.perf_counter() - t0
                _perf.record_llm(dur, "benchmark")
                with _lock:
                    llm_last_text = text
                    llm_last_ms = dur * 1000
                    llm_busy = False

            threading.Thread(target=_llm_task, daemon=True).start()

        # -- Dibujar --
        screen.fill(COLOR_BACKGROUND)

        # Banner superior
        _draw_banner(screen, banner_font, elapsed)

        # Marcador
        _draw_score(screen, score_font, score_left, score_right)

        # Linea central punteada
        _draw_center_line(screen)

        # Entidades
        left_paddle.draw(screen, GAME_AREA_TOP)
        right_paddle.draw(screen, GAME_AREA_TOP)
        ball.draw(screen, GAME_AREA_TOP)

        # Overlay inferior con metricas
        snap = perf.snapshot()
        with llm_lock:
            last_text = llm_last_text
            last_ms = llm_last_ms
            is_generating = llm_busy

        _draw_overlay(
            screen, info_font,
            fps_avg=snap["fps"]["avg"],
            llm_ms=last_ms,
            llm_generating=is_generating,
            llm_text=last_text,
            elapsed=elapsed,
            total=BENCHMARK_DURATION_S,
        )

        pygame.display.flip()
        perf.tick_frame()
        clock.tick(FPS)

    # -- Evaluar resultado --
    snap = perf.snapshot()
    fps_avg: float = snap["fps"]["avg"]
    fps_min: float = snap["fps"]["min"]
    llm_avg: float = snap["llm"]["avg_ms"]
    llm_count: int = snap["llm"]["calls"]

    passed = True
    reason = ""

    if fps_avg < BENCHMARK_FPS_MIN:
        passed = False
        reason = f"FPS medio ({fps_avg:.0f}) por debajo del minimo ({BENCHMARK_FPS_MIN:.0f})"
    elif llm_count < 3:
        passed = False
        reason = "El LLM no completo suficientes llamadas durante el benchmark"
    elif llm_avg > BENCHMARK_LLM_MAX_MS:
        passed = False
        reason = (
            f"Latencia LLM media ({llm_avg:.0f} ms) supera "
            f"el maximo ({BENCHMARK_LLM_MAX_MS:.0f} ms)"
        )

    return BenchmarkResult(
        fps_avg=fps_avg,
        fps_min=fps_min,
        llm_avg_ms=llm_avg,
        llm_calls_completed=llm_count,
        passed=passed,
        reason=reason,
    )


# ============================================================
# Helpers de LLM
# ============================================================

def _load_provider(config: LLMModelConfig) -> Any:
    """Carga un LocalLLMProvider con la config dada.

    Returns:
        El provider cargado, o ``None`` si fallo.
    """
    try:
        from pong.providers import LocalLLMProvider
        prov = LocalLLMProvider(config)
        if not prov.enabled:
            return None
        return prov
    except Exception as exc:
        logger.error("Error cargando LLM para benchmark: %s", exc)
        return None


def _run_llm_call(provider: Any) -> str:
    """Ejecuta una llamada al LLM con un prompt realista para medir latencia.

    El prompt replica la estructura y longitud que ``LocalNarrator.commentate``
    envia durante el juego real (system prompt con estilo + user prompt con
    estado de partida, marcador, historial y restricciones).  Asi la latencia
    medida refleja el rendimiento efectivo en gameplay, no un caso optimista
    con prompt corto.
    """
    try:
        result: dict[str, Any] = provider.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Comenta partidos de Pong en espanol como narrador "
                        "deportivo. Genera UNA sola frase de 8 a 18 palabras. "
                        "Usa un tono epico y emocionante, como una final. "
                        "Prohibido: inventar resultados, repetir frases "
                        "anteriores, usar la palabra Foco, usar coordenadas "
                        "o datos tecnicos."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "AHORA MISMO: Rally largo, ambos jugadores al limite\n"
                        "Jugada: Golpe cruzado del jugador tras rally intenso\n"
                        "Marcador: Jugador 3 - Maquina 2 | Juegos: 1-1 | Sets: 0-0\n"
                        "Rally: 12 toques\n"
                        "---\n"
                        "Anteriores (NO repetir):\n"
                        "- juego en curso: Jugador 2 - Maquina 2 | Juegos: 1-1\n"
                        "- punto del jugador: Jugador 3 - Maquina 1 | Juegos: 1-0\n"
                        "- juego en curso: Jugador 1 - Maquina 1 | Juegos: 0-0\n"
                        "---\n"
                        "Narra lo de AHORA MISMO en una frase."
                    ),
                },
            ],
            max_tokens=64,
            temperature=0.85,
            top_p=0.92,
            repeat_penalty=1.18,
            frequency_penalty=0.15,
        )
        choices: list[dict[str, Any]] = result.get("choices", [])
        if choices:
            msg: str = choices[0].get("message", {}).get("content", "").strip()
            return msg
    except Exception as exc:
        logger.warning("Error en llamada LLM de benchmark: %s", exc)
    return ""


# ============================================================
# Helpers de dibujo
# ============================================================

def _draw_loading_screen(
    screen: pygame.Surface,
    font: pygame.font.Font,
    text: str,
) -> None:
    """Pantalla de carga simple."""
    screen.fill(ZX_BLACK)
    label = font.render(text, False, ZX_CYAN_BRIGHT)
    rect = label.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2))
    screen.blit(label, rect)


def _draw_banner(
    screen: pygame.Surface,
    font: pygame.font.Font,
    elapsed: float,
) -> None:
    """Banner superior: BENCHMARK - DEMO IA vs IA."""
    banner_rect = pygame.Rect(0, 0, WINDOW_WIDTH, SCORE_BAND_HEIGHT)
    pygame.draw.rect(screen, ZX_BLACK, banner_rect)

    text = f"BENCHMARK - DEMO IA vs IA  [{elapsed:.0f}/{BENCHMARK_DURATION_S}s]"
    label = font.render(text, False, ZX_CYAN_BRIGHT)
    label_rect = label.get_rect(center=banner_rect.center)
    screen.blit(label, label_rect)


def _draw_score(
    screen: pygame.Surface,
    font: pygame.font.Font,
    left: int,
    right: int,
) -> None:
    """Marcador centrado en la zona de juego."""
    text = f"{left}  -  {right}"
    label = font.render(text, False, ZX_WHITE)
    label_rect = label.get_rect(
        centerx=WINDOW_WIDTH // 2,
        top=GAME_AREA_TOP + 10,
    )
    screen.blit(label, label_rect)


def _draw_center_line(screen: pygame.Surface) -> None:
    """Linea central punteada."""
    x = WINDOW_WIDTH // 2 - CENTER_DASH_WIDTH // 2
    y = GAME_AREA_TOP
    while y < GAME_AREA_TOP + GAME_AREA_HEIGHT:
        pygame.draw.rect(
            screen, COLOR_FOREGROUND,
            (x, y, CENTER_DASH_WIDTH, CENTER_DASH_HEIGHT),
        )
        y += CENTER_DASH_HEIGHT + CENTER_DASH_GAP


def _draw_overlay(
    screen: pygame.Surface,
    font: pygame.font.Font,
    *,
    fps_avg: float,
    llm_ms: float,
    llm_generating: bool,
    llm_text: str,
    elapsed: float,
    total: int,
) -> None:
    """Overlay inferior con metricas y barra de progreso."""
    overlay_top = GAME_AREA_TOP + GAME_AREA_HEIGHT
    overlay_rect = pygame.Rect(0, overlay_top, WINDOW_WIDTH, WINDOW_HEIGHT - overlay_top)
    pygame.draw.rect(screen, ZX_BLACK, overlay_rect)

    x = 16
    y = overlay_top + 8

    # FPS
    fps_color = ZX_GREEN_BRIGHT if fps_avg >= BENCHMARK_FPS_MIN else ZX_RED_BRIGHT
    fps_label = font.render(f"FPS: {fps_avg:.0f}", False, fps_color)
    screen.blit(fps_label, (x, y))

    # LLM
    if llm_generating:
        llm_label = font.render("LLM: generando...", False, ZX_YELLOW)
    elif llm_ms > 0:
        llm_color = ZX_GREEN_BRIGHT if llm_ms <= BENCHMARK_LLM_MAX_MS else ZX_RED_BRIGHT
        llm_label = font.render(f"LLM: {llm_ms / 1000:.1f}s", False, llm_color)
    else:
        llm_label = font.render("LLM: esperando...", False, ZX_GRAY_LIGHT)
    screen.blit(llm_label, (x + 200, y))

    y += 24

    # Texto de la ultima narracion
    if llm_text:
        # Truncar si es muy largo
        display_text = llm_text[:80] + ("..." if len(llm_text) > 80 else "")
        text_surf = font.render(display_text, False, ZX_GRAY_LIGHT)
        screen.blit(text_surf, (x, y))

    y += 24

    # Barra de progreso temporal
    progress = min(elapsed / total, 1.0)
    bar_width = WINDOW_WIDTH - 32
    bar_height = 16

    pygame.draw.rect(screen, ZX_GRAY_DARK, (x, y, bar_width, bar_height))
    filled_width = int(bar_width * progress)
    if filled_width > 0:
        pygame.draw.rect(screen, ZX_CYAN_BRIGHT, (x, y, filled_width, bar_height))

    pct_label = font.render(f"{int(progress * 100)}%", False, ZX_WHITE)
    pct_rect = pct_label.get_rect(center=(x + bar_width // 2, y + bar_height // 2))
    screen.blit(pct_label, pct_rect)

    y += bar_height + 8

    # Instruccion
    esc_label = font.render("ESC = cancelar", False, ZX_GRAY_DARK)
    screen.blit(esc_label, (x, y))
