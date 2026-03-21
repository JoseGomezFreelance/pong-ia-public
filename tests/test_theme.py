"""Pruebas del sistema de colores dinamico ZX Spectrum."""
from __future__ import annotations

import unittest

from pong.config.narrator import QUESTION_FIRST_DELAY_SECONDS
from pong.config.zx_spectrum import (
    THEME_AWAKENING_DURATION,
    ZX_BLACK,
    ZX_BLUE_BRIGHT,
    ZX_BROWN,
    ZX_CYAN_BRIGHT,
    ZX_GREEN_BRIGHT,
    ZX_MAGENTA_BRIGHT,
    ZX_RED_BRIGHT,
    ZX_RED_DARK,
    ZX_WHITE,
    ZX_YELLOW,
)
from pong.emotional_state import EmotionalState
from pong.theme import (
    MOOD_COLOR_SCHEMES,
    ThemeColors,
    ThemeManager,
    _lerp_rgb,
)


class LerpRGBTests(unittest.TestCase):
    """Tests para la funcion de interpolacion RGB."""

    def test_factor_zero_returns_current(self) -> None:
        self.assertEqual(_lerp_rgb((100, 50, 0), (200, 100, 255), 0.0), (100, 50, 0))

    def test_factor_one_returns_target(self) -> None:
        self.assertEqual(_lerp_rgb((100, 50, 0), (200, 100, 255), 1.0), (200, 100, 255))

    def test_factor_half_returns_midpoint(self) -> None:
        result = _lerp_rgb((0, 0, 0), (200, 100, 50), 0.5)
        self.assertEqual(result, (100, 50, 25))

    def test_clamps_to_0_255(self) -> None:
        # Con factor > 1.0 podria exceder 255 sin clamping
        result = _lerp_rgb((250, 0, 0), (255, 0, 0), 2.0)
        self.assertEqual(result[0], 255)
        # Resultado negativo se clampea a 0
        result = _lerp_rgb((5, 0, 0), (0, 0, 0), 2.0)
        self.assertEqual(result[0], 0)


class ThemeColorsDefaultsTests(unittest.TestCase):
    """Verifica que los valores por defecto coinciden con el estilo monocromo."""

    def test_defaults_are_monochrome(self) -> None:
        c = ThemeColors()
        self.assertEqual(c.background, (0, 0, 0))
        self.assertEqual(c.player_paddle, (255, 255, 255))
        self.assertEqual(c.computer_paddle, (255, 255, 255))
        self.assertEqual(c.ball, (255, 255, 255))
        self.assertEqual(c.center_line, (255, 255, 255))
        self.assertEqual(c.score_text, (255, 255, 255))
        self.assertEqual(c.narration_text, (255, 255, 255))


class ThemeManagerPhaseTests(unittest.TestCase):
    """Tests de las transiciones de fase del ThemeManager."""

    def setUp(self) -> None:
        self.tm = ThemeManager()
        self.emotion = EmotionalState(mood_tag="neutral")

    def test_initial_phase_is_monochrome(self) -> None:
        self.assertEqual(self.tm.phase, "monochrome")

    def test_monochrome_during_first_30_seconds(self) -> None:
        self.tm.update(10.0, self.emotion, emotion_active=False)
        self.assertEqual(self.tm.phase, "monochrome")

    def test_awakening_at_threshold(self) -> None:
        self.tm.update(QUESTION_FIRST_DELAY_SECONDS, self.emotion, emotion_active=False)
        self.assertEqual(self.tm.phase, "awakening")

    def test_emotional_after_awakening_duration(self) -> None:
        # Primero cruzar el umbral para iniciar awakening
        self.tm.update(QUESTION_FIRST_DELAY_SECONDS, self.emotion, emotion_active=False)
        # Avanzar mas alla de la duracion del despertar
        self.tm.update(
            QUESTION_FIRST_DELAY_SECONDS + THEME_AWAKENING_DURATION + 1.0,
            self.emotion,
            emotion_active=True,
        )
        self.assertEqual(self.tm.phase, "emotional")

    def test_monochrome_colors_are_white(self) -> None:
        """En fase monocromo todos los elementos deben ser blancos."""
        self.tm.update(5.0, self.emotion, emotion_active=False)
        self.assertEqual(self.tm.colors.computer_paddle, (255, 255, 255))
        self.assertEqual(self.tm.colors.ball, (255, 255, 255))
        self.assertEqual(self.tm.colors.center_line, (255, 255, 255))


class ThemeManagerInvariantsTests(unittest.TestCase):
    """Verifica invariantes que deben cumplirse en todas las fases."""

    def test_player_paddle_always_white(self) -> None:
        tm = ThemeManager()
        for mood in MOOD_COLOR_SCHEMES:
            emotion = EmotionalState(mood_tag=mood)
            # Cruzar a fase emocional
            tm.update(QUESTION_FIRST_DELAY_SECONDS, emotion, emotion_active=True)
            tm.update(
                QUESTION_FIRST_DELAY_SECONDS + THEME_AWAKENING_DURATION + 1.0,
                emotion,
                emotion_active=True,
            )
            # Forzar muchas iteraciones para que el lerp converja
            for _ in range(500):
                tm.update(
                    QUESTION_FIRST_DELAY_SECONDS + THEME_AWAKENING_DURATION + 10.0,
                    emotion,
                    emotion_active=True,
                )
            self.assertEqual(
                tm.colors.player_paddle,
                ZX_WHITE,
                f"player_paddle no es blanco para mood_tag={mood!r}",
            )

    def test_background_always_black(self) -> None:
        tm = ThemeManager()
        for mood in MOOD_COLOR_SCHEMES:
            emotion = EmotionalState(mood_tag=mood)
            tm.update(QUESTION_FIRST_DELAY_SECONDS, emotion, emotion_active=True)
            tm.update(
                QUESTION_FIRST_DELAY_SECONDS + THEME_AWAKENING_DURATION + 1.0,
                emotion,
                emotion_active=True,
            )
            for _ in range(500):
                tm.update(
                    QUESTION_FIRST_DELAY_SECONDS + THEME_AWAKENING_DURATION + 10.0,
                    emotion,
                    emotion_active=True,
                )
            self.assertEqual(
                tm.colors.background,
                ZX_BLACK,
                f"background no es negro para mood_tag={mood!r}",
            )


class ThemeManagerMoodColorTests(unittest.TestCase):
    """Verifica que cada mood_tag produce los colores esperados tras converger."""

    def _converged_colors(self, mood_tag: str) -> ThemeColors:
        """Devuelve ThemeColors tras converger a un mood_tag."""
        tm = ThemeManager()
        emotion = EmotionalState(mood_tag=mood_tag)
        # Cruzar fases
        tm.update(QUESTION_FIRST_DELAY_SECONDS, emotion, emotion_active=True)
        tm.update(
            QUESTION_FIRST_DELAY_SECONDS + THEME_AWAKENING_DURATION + 1.0,
            emotion,
            emotion_active=True,
        )
        # Iterar hasta convergencia
        for _ in range(500):
            tm.update(
                QUESTION_FIRST_DELAY_SECONDS + THEME_AWAKENING_DURATION + 10.0,
                emotion,
                emotion_active=True,
            )
        return tm.colors

    def test_neutral_computer_paddle_is_blue(self) -> None:
        colors = self._converged_colors("neutral")
        self.assertEqual(colors.computer_paddle, ZX_BLUE_BRIGHT)

    def test_relajado_computer_paddle_is_green(self) -> None:
        colors = self._converged_colors("relajado")
        self.assertEqual(colors.computer_paddle, ZX_GREEN_BRIGHT)

    def test_tenso_computer_paddle_is_red(self) -> None:
        colors = self._converged_colors("tenso")
        self.assertEqual(colors.computer_paddle, ZX_RED_BRIGHT)

    def test_furioso_computer_paddle_is_dark_red(self) -> None:
        colors = self._converged_colors("furioso")
        self.assertEqual(colors.computer_paddle, ZX_RED_DARK)

    def test_euforico_computer_paddle_is_yellow(self) -> None:
        colors = self._converged_colors("euforico")
        self.assertEqual(colors.computer_paddle, ZX_YELLOW)

    def test_erratico_computer_paddle_is_magenta(self) -> None:
        colors = self._converged_colors("erratico")
        self.assertEqual(colors.computer_paddle, ZX_MAGENTA_BRIGHT)

    def test_unknown_mood_falls_back_to_neutral(self) -> None:
        colors = self._converged_colors("desconocido")
        self.assertEqual(colors.computer_paddle, ZX_BLUE_BRIGHT)

    def test_narration_text_matches_computer_paddle(self) -> None:
        """La voz del ordenador (narracion) debe usar el mismo color que su paleta."""
        for mood in MOOD_COLOR_SCHEMES:
            colors = self._converged_colors(mood)
            scheme = MOOD_COLOR_SCHEMES[mood]
            self.assertEqual(
                colors.narration_text,
                scheme["narration_text"],
                f"narration_text no coincide para mood_tag={mood!r}",
            )


class ThemeManagerAwakeningTests(unittest.TestCase):
    """Verifica que la fase de despertar tiende al marron."""

    def test_awakening_target_is_brown(self) -> None:
        tm = ThemeManager()
        emotion = EmotionalState(mood_tag="neutral")
        # Entrar en awakening
        tm.update(QUESTION_FIRST_DELAY_SECONDS, emotion, emotion_active=False)
        self.assertEqual(tm.phase, "awakening")
        # Iterar para que el lerp converja dentro de la fase awakening
        for _ in range(500):
            tm.update(
                QUESTION_FIRST_DELAY_SECONDS + 1.0,
                emotion,
                emotion_active=False,
            )
        self.assertEqual(tm.colors.computer_paddle, ZX_BROWN)
        self.assertEqual(tm.colors.ball, ZX_BROWN)


if __name__ == "__main__":
    unittest.main()
