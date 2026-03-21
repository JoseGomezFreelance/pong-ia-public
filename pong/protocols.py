"""
pong/protocols.py -- Interfaces formales (Protocol) para subsistemas del juego.

Define los contratos que deben cumplir tanto las implementaciones reales
(RetroSoundManager, MusicEngine, NarrationBridge, LocalNarrator) como
sus Null Objects de modo headless (_NullSoundManager, etc.).

Usar Protocol (subtyping estructural) permite que las clases existentes
satisfagan el contrato sin necesidad de herencia explicita.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, Sequence, runtime_checkable

if TYPE_CHECKING:
    from typing import Callable

    from pong.emotional_state import EmotionalState
    from pong.entities import Ball
    from pong.scoring import ScoreState


@runtime_checkable
class SoundManagerProtocol(Protocol):
    """Contrato para el gestor de efectos de sonido."""

    def play_paddle_hit(self) -> None: ...

    def play_achievement(self) -> None: ...

    def set_music_mode(self, active: bool) -> None: ...


@runtime_checkable
class MusicEngineProtocol(Protocol):
    """Contrato para el motor de musica MIDI."""

    loaded: bool
    playing: bool

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def set_bullet_time(self, active: bool) -> None: ...

    def update(
        self,
        dt: float,
        emotional_state: EmotionalState | None = None,
        emotion_active: bool = False,
        is_bullet_time: bool = False,
    ) -> None: ...


@runtime_checkable
class NarratorProtocol(Protocol):
    """Contrato para el narrador IA (atributos leidos por Game)."""

    @property
    def enabled(self) -> bool: ...

    @property
    def status_message(self) -> str: ...

    @property
    def memory(self) -> Sequence[Any]: ...


@runtime_checkable
class NarrationBridgeProtocol(Protocol):
    """Contrato para el puente asincrono entre Game y el narrador."""

    narration_text: str
    narration_log: list[dict[str, Any]]

    @property
    def narrator(self) -> NarratorProtocol: ...

    def set_perf(self, perf: Any) -> None: ...

    def start(self, log_fn: Callable[[str, str], None] | None = None) -> None: ...

    def stop(self) -> None: ...

    def request(
        self, event_label: str, game_state_data: dict[str, Any], priority: bool = False,
    ) -> None: ...

    def request_reformulation(self, original_question: str) -> None: ...

    def request_new_question(
        self, dialogue_summary: str, game_state: dict[str, Any],
    ) -> None: ...

    def request_match_summary(self, match_data: dict[str, Any]) -> None: ...

    def request_image_prompt_enrichment(
        self, base_prompt: str, negative_prompt: str, context: dict[str, Any],
    ) -> None: ...

    def has_pending(self) -> bool: ...

    def consume_pending(self) -> None: ...

    def consume_pending_question(self) -> str | None: ...

    def consume_pending_emotion(self) -> EmotionalState | None: ...

    def consume_pending_summary(self) -> str | None: ...

    def consume_pending_image_prompt(self) -> tuple[str, str] | None: ...

    def build_game_state(
        self,
        event_label: str,
        score: ScoreState,
        ball: Ball,
        rally_hits: int,
        last_play: str,
        elapsed_seconds: float,
        event_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def reset_match_state(self, opening_text: str | None = None) -> None: ...

    def should_request_periodic(self) -> bool: ...

    def get_summary_progress(self) -> float: ...
