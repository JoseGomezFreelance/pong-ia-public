"""Pruebas del motor musical con sintesis ZX Spectrum."""
from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

import pygame


class MoodMusicParamsTests(unittest.TestCase):
    """Verifica que todos los mood_tags tienen parametros musicales."""

    def test_all_moods_have_params(self) -> None:
        from pong.music import MOOD_MUSIC_PARAMS
        expected_moods = [
            "neutral", "relajado", "tenso", "irritado", "furioso",
            "deprimido", "aburrido", "euforico", "erratico",
        ]
        for mood in expected_moods:
            self.assertIn(mood, MOOD_MUSIC_PARAMS, f"Falta mood '{mood}'")

    def test_tempo_mult_positive(self) -> None:
        from pong.music import MOOD_MUSIC_PARAMS
        for mood, params in MOOD_MUSIC_PARAMS.items():
            self.assertGreater(
                params.tempo_mult, 0.0,
                f"tempo_mult de '{mood}' debe ser positivo",
            )

    def test_active_voices_in_range(self) -> None:
        from pong.music import MOOD_MUSIC_PARAMS
        for mood, params in MOOD_MUSIC_PARAMS.items():
            self.assertGreaterEqual(params.active_voices, 1)
            self.assertLessEqual(params.active_voices, 3)


class EmotionalRemixerTests(unittest.TestCase):
    """Verifica la interpolacion de parametros musicales."""

    def test_default_values(self) -> None:
        from pong.music import EmotionalRemixer
        remixer = EmotionalRemixer()
        self.assertAlmostEqual(remixer.tempo_mult, 1.0)
        self.assertAlmostEqual(remixer.pitch_shift, 0.0)
        self.assertAlmostEqual(remixer.active_voices, 3.0)
        self.assertAlmostEqual(remixer.drum_intensity, 1.0)

    def test_update_moves_toward_target(self) -> None:
        from pong.music import EmotionalRemixer
        remixer = EmotionalRemixer()
        # Aplicar muchos frames de "furioso" (tempo_mult=1.4)
        for _ in range(200):
            remixer.update("furioso", dt=1 / 60)
        self.assertAlmostEqual(remixer.tempo_mult, 1.4, places=1)
        self.assertGreater(remixer.pitch_shift, 4.0)

    def test_update_deprimido_slows_down(self) -> None:
        from pong.music import EmotionalRemixer
        remixer = EmotionalRemixer()
        for _ in range(200):
            remixer.update("deprimido", dt=1 / 60)
        self.assertLess(remixer.tempo_mult, 0.7)
        self.assertLess(remixer.pitch_shift, -2.0)
        self.assertEqual(remixer.get_active_voice_count(), 1)

    def test_get_active_voice_count_clamped(self) -> None:
        from pong.music import EmotionalRemixer
        remixer = EmotionalRemixer()
        remixer.active_voices = 0.3
        self.assertEqual(remixer.get_active_voice_count(), 1)
        remixer.active_voices = 5.0
        self.assertEqual(remixer.get_active_voice_count(), 3)

    def test_unknown_mood_uses_neutral(self) -> None:
        from pong.music import EmotionalRemixer
        remixer = EmotionalRemixer()
        # No debe lanzar excepcion con mood desconocido
        remixer.update("inexistente", dt=1 / 60)
        self.assertAlmostEqual(remixer.tempo_mult, 1.0, places=1)


class NoteEventTests(unittest.TestCase):
    """Verifica la estructura de NoteEvent."""

    def test_note_event_creation(self) -> None:
        from pong.music import NoteEvent
        event = NoteEvent(time=1.5, midi_note=60, velocity=100, duration=0.25, voice=0)
        self.assertAlmostEqual(event.time, 1.5)
        self.assertEqual(event.midi_note, 60)
        self.assertEqual(event.velocity, 100)
        self.assertAlmostEqual(event.duration, 0.25)
        self.assertEqual(event.voice, 0)


class MusicEngineDurationBucketsTests(unittest.TestCase):
    """Verifica el snap de duraciones a buckets para cache."""

    def test_snap_small_duration(self) -> None:
        from pong.music import MusicEngine
        self.assertAlmostEqual(MusicEngine._snap_duration(0.02), 0.03)

    def test_snap_exact_bucket(self) -> None:
        from pong.music import MusicEngine
        self.assertAlmostEqual(MusicEngine._snap_duration(0.1), 0.1)

    def test_snap_large_duration(self) -> None:
        from pong.music import MusicEngine
        self.assertAlmostEqual(MusicEngine._snap_duration(3.0), 2.0)

    def test_snap_between_buckets(self) -> None:
        from pong.music import MusicEngine
        # 0.12 esta entre 0.1 y 0.15, debe ir a 0.15
        self.assertAlmostEqual(MusicEngine._snap_duration(0.12), 0.15)


class MusicEngineLoadTests(unittest.TestCase):
    """Verifica la carga del MIDI."""

    def test_loaded_with_real_midi(self) -> None:
        """Comprueba que el MIDI del proyecto se parsea correctamente."""
        pygame.mixer.init(frequency=22050, size=-16, channels=1)
        try:
            from pong.music import MusicEngine
            engine = MusicEngine()
            if engine.loaded:
                self.assertGreater(len(engine._events), 0)
                self.assertGreater(engine.total_duration, 0.0)
                # Verificar que hay eventos de distintas voces
                voices = {e.voice for e in engine._events}
                self.assertIn(0, voices, "Debe haber voz 0 (melodia)")
        finally:
            pygame.mixer.quit()

    def test_not_loaded_with_missing_file(self) -> None:
        """Sin MIDI, loaded debe ser False."""
        pygame.mixer.init(frequency=22050, size=-16, channels=1)
        try:
            from pong.music import MusicEngine
            with patch("pong.music.MUSIC_MIDI_PATH", Path("/tmp/no_existe.mid")):
                engine = MusicEngine()
                self.assertFalse(engine.loaded)
        finally:
            pygame.mixer.quit()


class MusicEnginePlaybackTests(unittest.TestCase):
    """Verifica la logica de reproduccion."""

    def setUp(self) -> None:
        pygame.mixer.init(frequency=22050, size=-16, channels=1)
        pygame.mixer.set_num_channels(8)

    def tearDown(self) -> None:
        pygame.mixer.quit()

    def test_start_sets_playing(self) -> None:
        from pong.music import MusicEngine
        engine = MusicEngine()
        if not engine.loaded:
            self.skipTest("MIDI no disponible")
        engine.start()
        self.assertTrue(engine.playing)
        self.assertAlmostEqual(engine.playback_time, 0.0)

    def test_stop_clears_playing(self) -> None:
        from pong.music import MusicEngine
        engine = MusicEngine()
        if not engine.loaded:
            self.skipTest("MIDI no disponible")
        engine.start()
        engine.stop()
        self.assertFalse(engine.playing)

    def test_update_advances_time(self) -> None:
        from pong.music import MusicEngine
        engine = MusicEngine()
        if not engine.loaded:
            self.skipTest("MIDI no disponible")
        engine.start()
        engine.update(dt=1.0 / 60)
        self.assertGreater(engine.playback_time, 0.0)

    def test_update_without_start_does_nothing(self) -> None:
        from pong.music import MusicEngine
        engine = MusicEngine()
        engine.update(dt=1.0 / 60)
        self.assertAlmostEqual(engine.playback_time, 0.0)

    def test_bullet_time_changes_volume(self) -> None:
        from pong.music import MusicEngine
        from pong.config.media import MUSIC_BULLET_TIME_VOLUME
        engine = MusicEngine()
        engine.set_bullet_time(True)
        self.assertAlmostEqual(engine._volume_mult, MUSIC_BULLET_TIME_VOLUME)
        engine.set_bullet_time(False)
        self.assertAlmostEqual(engine._volume_mult, 1.0)


class SoundUtilitiesTests(unittest.TestCase):
    """Verifica las utilidades de sintesis en sound.py."""

    def setUp(self) -> None:
        pygame.mixer.init(frequency=22050, size=-16, channels=1)

    def tearDown(self) -> None:
        pygame.mixer.quit()

    def test_build_square_wave_returns_sound(self) -> None:
        from pong.sound import build_square_wave
        sound = build_square_wave(440, 0.1, 0.5)
        self.assertIsNotNone(sound)
        self.assertIsInstance(sound, pygame.mixer.Sound)

    def test_build_square_wave_zero_duration(self) -> None:
        from pong.sound import build_square_wave
        sound = build_square_wave(440, 0.0, 0.5)
        self.assertIsNone(sound)

    def test_build_noise_burst_returns_sound(self) -> None:
        from pong.sound import build_noise_burst
        sound = build_noise_burst(0.05, 0.3)
        self.assertIsNotNone(sound)
        self.assertIsInstance(sound, pygame.mixer.Sound)

    def test_build_noise_burst_zero_duration(self) -> None:
        from pong.sound import build_noise_burst
        sound = build_noise_burst(0.0, 0.3)
        self.assertIsNone(sound)


if __name__ == "__main__":
    unittest.main()
