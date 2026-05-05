"""
pong/game_state.py -- Dataclasses de estado y factory de subsistemas.

Agrupa atributos relacionados del juego en clases con nombre para
mejorar la legibilidad de Game.__init__ y simplificar resets en
_restart_match().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from pong.scoring import ScoreState

if TYPE_CHECKING:
    from pong.harness import HeadlessConfig
    from pong.perf import PerformanceMetrics
    from pong.protocols import (
        MusicEngineProtocol,
        NarrationBridgeProtocol,
        SoundManagerProtocol,
    )


@dataclass
class MatchState:
    """Estado del partido en curso (marcador, rally, timeline)."""

    score: ScoreState = field(default_factory=ScoreState)
    last_play: str = "Saque inicial"
    rally_hits: int = 0
    max_rally_hits: int = 0
    score_timeline: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class UIState:
    """Flags y scroll de las pantallas de UI (fin, logros, debug, RPG)."""

    showing_end_screen: bool = False
    showing_achievements_screen: bool = False
    showing_debug_screen: bool = False
    showing_skills_screen: bool = False
    showing_ascension_confirm: bool = False
    showing_ascension_screen: bool = False
    showing_leaderboard_screen: bool = False
    showing_alias_prompt: bool = False
    showing_p2p_connecting: bool = False
    p2p_connect_start_time: float = 0.0
    leaderboard_active_tab: int = 0
    leaderboard_screen_scroll: int = 0
    alias_input_text: str = ""
    end_screen_scroll: int = 0
    achievements_screen_scroll: int = 0
    debug_screen_scroll: int = 0
    skills_screen_scroll: int = 0
    ascension_screen_scroll: int = 0
    copy_status_text: str = ""
    copy_status_expires_at: float = 0.0


def create_subsystems(
    headless_config: HeadlessConfig | None,
    perf: PerformanceMetrics,
    log_fn: Callable[[str, str], None],
    progress_fn: Callable[[str], None] | None = None,
) -> tuple[SoundManagerProtocol, MusicEngineProtocol, NarrationBridgeProtocol]:
    """
    Crea los subsistemas de sonido, musica y narracion.

    Centraliza la logica headless/normal que antes se repetia 3 veces
    en Game.__init__. Devuelve la tupla (sounds, music, narration)
    ya configurados y listos para usar.

    Args:
        headless_config: Config headless (None = modo normal con todo activo).
        perf: Metricas de rendimiento (se pasa al narrador).
        log_fn: Funcion de log del juego.
        progress_fn: Callback opcional para reportar progreso de carga.
    """
    _hl = headless_config

    # --- Sonido ---
    if _hl is None or _hl.enable_sound:
        if progress_fn:
            progress_fn("Generando efectos de sonido...")
        from pong.sound import RetroSoundManager
        sounds: SoundManagerProtocol = RetroSoundManager()
        if progress_fn:
            progress_fn("Efectos de sonido listos")
    else:
        from pong.harness import _NullSoundManager
        sounds = _NullSoundManager()

    # --- Musica ---
    if _hl is None or _hl.enable_music:
        if progress_fn:
            progress_fn("Cargando tema musical MIDI...")
        from pong.music import MusicEngine
        music: MusicEngineProtocol = MusicEngine()
        music_status = "tema cargado" if music.loaded else "no disponible"
        if progress_fn:
            progress_fn(f"Musica: {music_status}")
    else:
        from pong.harness import _NullMusicEngine
        music = _NullMusicEngine()

    # --- Narracion ---
    if _hl is None or _hl.enable_narration:
        if progress_fn:
            progress_fn("Cargando narrador IA...")
        from pong.narration_bridge import NarrationBridge
        narration: NarrationBridgeProtocol = NarrationBridge()
        narration.set_perf(perf)
        if progress_fn:
            progress_fn(f"Narrador: {narration.narrator.status_message}")
        narration.start(log_fn=log_fn)
    else:
        from pong.harness import _NullNarrationBridge
        narration = _NullNarrationBridge()

    return sounds, music, narration
