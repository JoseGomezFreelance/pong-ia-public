"""
pong/game_imagegen.py -- Mixin con la fase visual generativa.

Extraído de game.py para reducir su tamaño. La clase Game hereda
de GameImagegenMixin para obtener estos métodos.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pong.emotional_state import EmotionalState
    from pong.game_state import MatchState
    from pong.image_generator import ImageGenerator
    from pong.perf import PerformanceMetrics
    from pong.protocols import NarrationBridgeProtocol
    from pong.question_system import QuestionSystem
    from pong.renderer import Renderer
    from pong.splash import ZXTerminal


class GameImagegenMixin:
    """Métodos de generación de imágenes, usados por Game vía herencia."""

    # -- Atributos declarados en Game, visibles aquí para mypy --
    _imagegen: ImageGenerator | None
    _headless: Any
    imagegen_active: bool
    imagegen_unlocked: bool
    _last_imagegen_time: float
    perf: PerformanceMetrics
    emotional_state: EmotionalState
    emotion_active: bool
    match: MatchState
    narration: NarrationBridgeProtocol
    game_start_time: float
    questions: QuestionSystem
    renderer: Renderer

    def _log(self, category: str, message: str) -> None:
        raise NotImplementedError  # Provided by Game

    def _init_imagegen_phase(self, terminal: ZXTerminal | None = None) -> None:
        """
        Inicializa el estado de la fase visual generativa.

        Comprueba si la fase está desbloqueada y prepara los atributos.
        No descarga el modelo aquí (eso se hace en __init__ después de
        crear los subsistemas).

        Args:
            terminal: Terminal de carga ZX Spectrum (None si headless).
        """
        from pong.save_manager import load_history, check_phase_unlocks, _write_history

        _history: dict[str, Any] = load_history()
        _newly = check_phase_unlocks(_history)
        if _newly:
            _write_history(_history)
        self.imagegen_unlocked = "imagegen" in _history.get("phases_unlocked", {})
        self.imagegen_active = False
        self._imagegen = None
        self._last_imagegen_time = 0.0

    def _activate_imagegen(self) -> None:
        """Activa el generador de imágenes (carga lazy del modelo)."""
        from pong.providers import load_imagegen_provider
        from pong.config.models import load_models_config

        _, image_config = load_models_config()
        gen = load_imagegen_provider(image_config)
        self._imagegen = gen  # type: ignore[assignment]
        gen.set_perf(self.perf)
        gen.set_log_fn(self._log)
        gen.activate()
        self.imagegen_active = True
        self._log("IMAGEGEN", "Fase visual generativa activada")

    def _request_background_image(self) -> None:
        """Solicita enriquecimiento LLM del prompt y luego genera la imagen."""
        if self._imagegen is None or not self._imagegen.is_ready:
            return

        from pong.image_generator import build_image_prompt

        context = {
            "mood_tag": (
                self.emotional_state.mood_tag if self.emotion_active else "neutral"
            ),
            "score_player": self.match.score.player_sets,
            "score_computer": self.match.score.computer_sets,
            "rally_hits": self.match.rally_hits,
            "narration_text": self.narration.narration_text,
            "elapsed": time.monotonic() - self.game_start_time,
            "dialogue_history": [
                {"q": e.question, "a": e.answer}
                for e in self.questions.dialogue_history[-3:]
            ],
        }
        prompt, negative = build_image_prompt(context)

        # Si el narrador está disponible, enriquecer vía hilo de fondo
        if self.narration.narrator.enabled:
            self.narration.request_image_prompt_enrichment(
                prompt, negative, context
            )
            self._log("IMAGEGEN", f"Prompt base enviado a enriquecer: {prompt[:60]}...")
        else:
            # Sin LLM: enviar directamente a Stable Diffusion
            self._imagegen.request(prompt, negative)
            self._log("IMAGEGEN", f"Prompt (sin LLM): {prompt[:80]}...")

    def _shutdown_imagegen(self) -> None:
        """Detiene el generador de imágenes y libera recursos."""
        if self._imagegen is not None:
            self._imagegen.shutdown()
            self._imagegen = None
        self.imagegen_active = False
        self.renderer.clear_background_image()
