"""Tests de conformidad: verifican que las clases reales y Null Objects
satisfacen sus Protocol correspondiente."""

from __future__ import annotations

from pong.harness import _NullMusicEngine, _NullNarrationBridge, _NullNarrator, _NullSoundManager
from pong.protocols import (
    MusicEngineProtocol,
    NarrationBridgeProtocol,
    NarratorProtocol,
    SoundManagerProtocol,
)


# --- Null Objects ---

class TestNullObjectConformity:
    """Cada Null Object debe satisfacer su Protocol."""

    def test_null_sound_manager(self) -> None:
        assert isinstance(_NullSoundManager(), SoundManagerProtocol)

    def test_null_music_engine(self) -> None:
        assert isinstance(_NullMusicEngine(), MusicEngineProtocol)

    def test_null_narrator(self) -> None:
        assert isinstance(_NullNarrator(), NarratorProtocol)

    def test_null_narration_bridge(self) -> None:
        assert isinstance(_NullNarrationBridge(), NarrationBridgeProtocol)


# --- Clases reales (sin dependencias pesadas) ---

class TestRealClassConformity:
    """Las clases reales deben satisfacer su Protocol.

    Algunas requieren pygame o un modelo LLM, asi que solo verificamos
    las que se pueden instanciar sin efectos secundarios.
    """

    def test_retro_sound_manager(self) -> None:
        import pygame
        pygame.mixer.quit()  # evitar error si no hay audio
        from pong.sound import RetroSoundManager
        assert isinstance(RetroSoundManager(), SoundManagerProtocol)

    def test_music_engine(self) -> None:
        from pong.music import MusicEngine
        assert isinstance(MusicEngine(), MusicEngineProtocol)
