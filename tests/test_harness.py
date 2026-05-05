"""Tests del modo headless / GameHarness (pong/harness.py)."""
from __future__ import annotations

import os
import tempfile
import unittest

import pygame

from pong.harness import GameHarness, HeadlessConfig


class TestHarnessLifecycle(unittest.TestCase):
    """Ciclo de vida basico: crear, step, cerrar."""

    def test_create_and_close(self) -> None:
        harness = GameHarness.create()
        self.assertIsNotNone(harness.game)
        self.assertTrue(harness.game.running)
        harness.close()

    def test_context_manager(self) -> None:
        with GameHarness.create() as h:
            self.assertIsNotNone(h.game)

    def test_step_advances_game(self) -> None:
        with GameHarness.create() as h:
            state_before = h.get_state()
            h.step(10)
            state_after = h.get_state()
            ball_moved = (
                state_after["ball"]["x"] != state_before["ball"]["x"]
                or state_after["ball"]["y"] != state_before["ball"]["y"]
            )
            self.assertTrue(ball_moved, "La bola deberia moverse tras step()")


class TestHarnessInput(unittest.TestCase):
    """Inyeccion de inputs de teclado."""

    def test_press_up_moves_paddle(self) -> None:
        with GameHarness.create() as h:
            h.step(1)  # un frame para estabilizar
            initial_y = h.get_state()["player"]["y"]
            h.press_keys([pygame.K_UP])
            h.step(30)
            final_y = h.get_state()["player"]["y"]
            self.assertLess(final_y, initial_y, "UP deberia mover la paleta arriba")

    def test_press_down_moves_paddle(self) -> None:
        with GameHarness.create() as h:
            h.step(1)
            initial_y = h.get_state()["player"]["y"]
            h.press_keys([pygame.K_DOWN])
            h.step(30)
            final_y = h.get_state()["player"]["y"]
            self.assertGreater(final_y, initial_y, "DOWN deberia mover la paleta abajo")

    def test_release_all_keys(self) -> None:
        with GameHarness.create() as h:
            h.press_keys([pygame.K_UP])
            h.step(5)
            h.release_all_keys()
            y_after_release = h.get_state()["player"]["y"]
            h.step(5)
            y_later = h.get_state()["player"]["y"]
            self.assertEqual(y_after_release, y_later,
                             "Sin teclas pulsadas la paleta no deberia moverse")


class TestHarnessState(unittest.TestCase):
    """Lectura de estado del juego."""

    def test_get_state_keys(self) -> None:
        with GameHarness.create() as h:
            state = h.get_state()
            expected_keys = {
                "ball", "player", "computer", "score", "rally_hits",
                "max_rally_hits", "paused", "showing_end_screen", "running",
                "narration_text", "elapsed_seconds", "emotion",
            }
            self.assertEqual(set(state.keys()), expected_keys)

    def test_score_starts_at_zero(self) -> None:
        with GameHarness.create() as h:
            score = h.get_state()["score"]
            self.assertEqual(score["player_points"], 0)
            self.assertEqual(score["computer_points"], 0)

    def test_game_starts_unpaused(self) -> None:
        with GameHarness.create() as h:
            state = h.get_state()
            self.assertFalse(state["paused"])
            self.assertFalse(state["showing_end_screen"])
            self.assertTrue(state["running"])


class TestHarnessScreenshot(unittest.TestCase):
    """Captura de screenshots."""

    def test_capture_frame_returns_surface(self) -> None:
        with GameHarness.create() as h:
            h.step(1)
            frame = h.capture_frame()
            self.assertIsInstance(frame, pygame.Surface)
            self.assertEqual(frame.get_size(), (800, 766))

    def test_save_screenshot(self) -> None:
        with GameHarness.create() as h:
            h.step(1)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                path = f.name
            try:
                h.save_screenshot(path)
                self.assertTrue(os.path.exists(path))
                self.assertGreater(os.path.getsize(path), 0)
            finally:
                os.unlink(path)


class TestHarnessConfig(unittest.TestCase):
    """Configuracion de subsistemas."""

    def test_default_config_disables_heavy_subsystems(self) -> None:
        config = HeadlessConfig()
        self.assertFalse(config.enable_narration)
        self.assertFalse(config.enable_music)
        self.assertFalse(config.enable_sound)
        self.assertFalse(config.enable_imagegen)
        self.assertTrue(config.skip_splash)

    def test_null_narration_bridge(self) -> None:
        with GameHarness.create() as h:
            self.assertFalse(h.game.narration.narrator.enabled)
            self.assertEqual(h.game.narration.narration_text, "Modo de prueba.")


if __name__ == "__main__":
    unittest.main()
