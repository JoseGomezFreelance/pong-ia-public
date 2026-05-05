"""
pong/harness.py -- API programatica para testing headless del juego.

Permite ejecutar el juego sin ventana visible, avanzar frame a frame,
inyectar inputs de teclado, leer el estado completo y capturar screenshots.

Uso basico::

    from pong.harness import GameHarness

    with GameHarness.create() as h:
        h.step(60)                          # avanzar 1 segundo
        state = h.get_state()               # leer estado
        h.press_keys([pygame.K_UP])         # pulsar tecla
        h.step(30)
        h.save_screenshot("/tmp/frame.png") # capturar pantalla

Para resultados deterministas, fijar la semilla antes de crear el harness::

    import random
    random.seed(42)
    harness = GameHarness.create()
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from types import TracebackType
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

if TYPE_CHECKING:
    from pong.emotional_state import EmotionalState

import pygame


# ============================================================
# Configuracion headless
# ============================================================

@dataclass
class HeadlessConfig:
    """Controla que subsistemas se activan en modo headless."""

    enable_narration: bool = False
    enable_music: bool = False
    enable_sound: bool = False
    enable_imagegen: bool = False
    skip_splash: bool = True


# ============================================================
# Null objects (reemplazan subsistemas desactivados)
# ============================================================

class _NullSoundManager:
    """Drop-in silencioso para RetroSoundManager."""

    def play_paddle_hit(self) -> None:
        pass

    def play_achievement(self) -> None:
        pass

    def set_music_mode(self, active: bool) -> None:
        pass


class _NullMusicEngine:
    """Drop-in silencioso para MusicEngine."""

    loaded = False
    playing = False

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def set_bullet_time(self, active: bool) -> None:
        pass

    def update(self, dt: float, emotional_state: Any = None, emotion_active: bool = False,
               is_bullet_time: bool = False) -> None:
        pass


class _NullNarrator:
    """Sustituye al narrador LLM real."""

    enabled = False
    status_message = "Narrador desactivado (modo headless)"
    memory: list[dict[str, str]] = []

    def reload_llm(self) -> None:
        pass


class _NullNarrationBridge:
    """Drop-in silencioso para NarrationBridge."""

    narration_text = "Modo de prueba."
    narration_log: list[dict[str, Any]] = []
    narrator = _NullNarrator()

    def set_perf(self, perf: Any) -> None:
        pass

    def start(self, log_fn: Any = None) -> None:
        pass

    def stop(self) -> None:
        pass

    def request(self, event_label: str, game_state: dict[str, Any], priority: bool = False) -> None:
        pass

    def request_reformulation(self, original_question: str) -> None:
        pass

    def request_new_question(self, dialogue_summary: str, game_state: dict[str, Any]) -> None:
        pass

    def request_match_summary(self, match_data: dict[str, Any]) -> None:
        pass

    def build_game_state(self, event_label: str, score: Any, ball: Any, rally_hits: int,
                         last_play: str, elapsed_seconds: float, event_data: dict[str, Any] | None = None) -> dict[str, Any]:
        return {}

    def has_pending(self) -> bool:
        return False

    def consume_pending(self) -> None:
        pass

    def consume_pending_question(self) -> str | None:
        return None

    def consume_pending_emotion(self) -> EmotionalState | None:
        return None

    def consume_pending_summary(self) -> str | None:
        return None

    def should_request_periodic(self) -> bool:
        return False

    def get_summary_progress(self) -> float:
        return 0.0

    def request_image_prompt_enrichment(
        self, base_prompt: str, negative_prompt: str, context: dict[str, Any],
    ) -> None:
        pass

    def consume_pending_image_prompt(self) -> tuple[str, str] | None:
        return None

    def reset_match_state(self, opening_text: str | None = None) -> None:
        pass


# ============================================================
# Helpers
# ============================================================

class _FakeKeyState:
    """Objeto que imita ``pygame.key.get_pressed()`` (ScancodeWrapper).

    En Pygame 2 (SDL2), las constantes como ``pygame.K_UP`` son valores
    grandes (~1073741906) que ScancodeWrapper convierte internamente a
    scancodes. Este objeto simplemente devuelve True/False segun si la
    tecla esta en el set de teclas pulsadas.
    """

    def __init__(self, pressed: set[int]):
        self._pressed = pressed

    def __getitem__(self, key: int) -> bool:
        return key in self._pressed


# ============================================================
# GameHarness
# ============================================================

class GameHarness:
    """
    Wrapper programatico para testing del juego Pong.

    Ejecuta el juego en modo headless (sin ventana) y expone una API
    para avanzar frames, inyectar inputs, leer estado y capturar
    screenshots.
    """

    def __init__(self, game: Any) -> None:
        self.game = game
        self._pressed_keys: set[int] = set()
        self._pending_events: list[pygame.event.Event] = []

    @classmethod
    def create(cls, config: HeadlessConfig | None = None) -> GameHarness:
        """
        Crea un GameHarness con el juego inicializado en modo headless.

        Configura los drivers SDL dummy antes de ``pygame.init()``
        para evitar crear ventana o inicializar audio real.
        """
        if config is None:
            config = HeadlessConfig()

        # Drivers dummy ANTES de pygame.init()
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_AUDIODRIVER"] = "dummy"

        from pong.game import Game
        game = Game(headless_config=config)
        return cls(game)

    # -- Control de frames --

    def step(self, n_frames: int = 1) -> None:
        """
        Avanza el juego ``n_frames`` frames.

        Cada frame ejecuta: handle_input() -> update() -> draw().
        No llama ``clock.tick()`` — corre a maxima velocidad.
        """
        key_state = _FakeKeyState(self._pressed_keys)

        for _ in range(n_frames):
            events = list(self._pending_events)
            self._pending_events.clear()

            with patch("pygame.event.get", return_value=events), \
                 patch("pygame.key.get_pressed", return_value=key_state):
                self.game.handle_input()

            self.game.update()
            self.game.draw()
            self.game.perf.tick_frame()

    # -- Inyeccion de inputs --

    def press_keys(self, keys: list[int]) -> None:
        """
        Marca teclas como pulsadas (mantenidas).

        Args:
            keys: Lista de constantes pygame (e.g. ``[pygame.K_UP]``).
                  Reemplaza cualquier tecla anteriormente pulsada.
        """
        self._pressed_keys = set(keys)

    def release_all_keys(self) -> None:
        """Suelta todas las teclas."""
        self._pressed_keys.clear()

    def inject_event(self, event: pygame.event.Event) -> None:
        """Encola un evento pygame para el proximo ``step()``."""
        self._pending_events.append(event)

    # -- Lectura de estado --

    def get_state(self) -> dict[str, Any]:
        """
        Retorna un diccionario con el estado completo del juego.

        Incluye: posicion de bola, paletas, marcador, estado emocional,
        rally, flags de pausa/fin, y tiempo transcurrido.
        """
        g = self.game
        elapsed = time.monotonic() - g.game_start_time

        return {
            "ball": {
                "x": g.ball.rect.x,
                "y": g.ball.rect.y,
                "speed_x": g.ball.speed_x,
                "speed_y": g.ball.speed_y,
            },
            "player": {
                "x": g.player.rect.x,
                "y": g.player.rect.y,
            },
            "computer": {
                "x": g.computer.rect.x,
                "y": g.computer.rect.y,
            },
            "score": {
                "player_points": g.match.score.player_points,
                "computer_points": g.match.score.computer_points,
                "player_games": g.match.score.player_games,
                "computer_games": g.match.score.computer_games,
                "player_sets": g.match.score.player_sets,
                "computer_sets": g.match.score.computer_sets,
            },
            "rally_hits": g.match.rally_hits,
            "max_rally_hits": g.match.max_rally_hits,
            "paused": g.paused,
            "showing_end_screen": g.ui.showing_end_screen,
            "running": g.running,
            "narration_text": g.narration.narration_text,
            "elapsed_seconds": elapsed,
            "emotion": {
                "aggressiveness": g.emotional_state.aggressiveness,
                "stability": g.emotional_state.stability,
                "motivation": g.emotional_state.motivation,
                "mood_tag": g.emotional_state.mood_tag,
            },
        }

    def get_perf(self) -> dict[str, Any]:
        """Retorna snapshot de metricas de rendimiento."""
        result: dict[str, Any] = self.game.perf.snapshot()
        return result

    # -- Captura de screenshots --

    def capture_frame(self) -> pygame.Surface:
        """Retorna una copia del Surface actual (800x744)."""
        surface: pygame.Surface = self.game.screen.copy()
        return surface

    def save_screenshot(self, path: str) -> None:
        """Captura el frame actual y lo guarda como PNG."""
        frame = self.capture_frame()
        pygame.image.save(frame, path)

    # -- Ciclo de vida --

    def close(self) -> None:
        """Limpia recursos: detiene hilos de fondo y cierra pygame."""
        try:
            if hasattr(self.game, '_imagegen') and self.game._imagegen:
                self.game._shutdown_imagegen()
            self.game.narration.stop()
        except (AttributeError, RuntimeError, OSError):
            pass
        try:
            pygame.quit()
        except pygame.error:
            pass

    def __enter__(self) -> GameHarness:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()
