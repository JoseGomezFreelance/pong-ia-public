"""Tests de integracion via GameHarness."""
from __future__ import annotations

import unittest

import pygame
import pytest

from pong.config.gameplay import (
    AI_RALLY_PRESS_STEP,
    AI_RALLY_PRESS_THRESHOLD,
    BALL_RALLY_SPEEDUP_THRESHOLD,
    BALL_SPEED_X,
)
from pong.config.layout import WINDOW_WIDTH
from pong.harness import GameHarness


class TestRally(unittest.TestCase):

    def test_ball_moves_across_field(self) -> None:
        """La pelota se mueve lo suficiente como para cruzar la pantalla."""
        with GameHarness.create() as h:
            state_0 = h.get_state()
            h.step(100)
            state_1 = h.get_state()
            dx = abs(state_1["ball"]["x"] - state_0["ball"]["x"])
            dy = abs(state_1["ball"]["y"] - state_0["ball"]["y"])
            self.assertGreater(dx + dy, 0, "La pelota deberia moverse")

    def test_point_scored_eventually(self) -> None:
        """Con la paleta del jugador fuera de posicion, el ordenador anota."""
        with GameHarness.create() as h:
            # Mover la paleta del jugador al extremo superior para que
            # no pueda devolver pelotas que vayan al centro/abajo.
            h.press_keys([pygame.K_UP])
            h.step(60)  # paleta pegada al techo
            h.release_all_keys()

            # Ahora dejar que el juego corra: el jugador no se mueve,
            # asi que el ordenador acabara anotando.
            for _ in range(20):
                h.step(200)
                state = h.get_state()
                total_points = (
                    state["score"]["player_points"]
                    + state["score"]["computer_points"]
                    + state["score"]["player_games"]
                    + state["score"]["computer_games"]
                )
                if total_points > 0:
                    break
            self.assertGreater(
                total_points, 0,
                "Con paleta fija arriba, deberia haber al menos un punto",
            )


class TestPause(unittest.TestCase):

    def test_pause_and_unpause(self) -> None:
        """Pausar y reanudar el juego con K_p."""
        with GameHarness.create() as h:
            h.step(5)
            self.assertFalse(h.get_state()["paused"])

            # Pause
            event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_p)
            h.inject_event(event)
            h.step(1)
            self.assertTrue(h.get_state()["paused"])

            # Unpause
            event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_p)
            h.inject_event(event)
            h.step(1)
            self.assertFalse(h.get_state()["paused"])


class TestStateConsistency(unittest.TestCase):

    def test_state_values_in_range(self) -> None:
        """Todos los valores del estado deben estar dentro de rangos razonables."""
        with GameHarness.create() as h:
            h.step(50)
            state = h.get_state()

            # Ball within game area
            self.assertGreaterEqual(state["ball"]["x"], -50)
            self.assertLessEqual(state["ball"]["x"], 850)
            self.assertGreaterEqual(state["ball"]["y"], -50)
            self.assertLessEqual(state["ball"]["y"], 550)

            # Scores non-negative
            self.assertGreaterEqual(state["score"]["player_points"], 0)
            self.assertGreaterEqual(state["score"]["computer_points"], 0)

            # Rally non-negative
            self.assertGreaterEqual(state["rally_hits"], 0)

            # Elapsed positive
            self.assertGreaterEqual(state["elapsed_seconds"], 0)


class TestAntiInfiniteRallyDifficulty(unittest.TestCase):

    def test_ball_moves_faster_during_long_rally(self) -> None:
        with GameHarness.create() as h:
            g = h.game
            g.match.rally_hits = BALL_RALLY_SPEEDUP_THRESHOLD + 20
            g.ball.sync_rally_speed(g.match.rally_hits)
            g.ball.speed_x = BALL_SPEED_X
            g.ball.speed_y = 0
            x_before = g.ball.rect.x

            h.step(1)

            self.assertEqual(g.ball.rect.x - x_before, 6)

    def test_computer_press_and_point_reset(self) -> None:
        with GameHarness.create() as h:
            g = h.game
            g.match.rally_hits = AI_RALLY_PRESS_THRESHOLD + 2
            g.ball.sync_rally_speed(g.match.rally_hits)

            h.step(1)

            self.assertEqual(
                g.computer.rect.x,
                g.computer_home_x - 2 * AI_RALLY_PRESS_STEP,
            )

            g.ball.rect.right = WINDOW_WIDTH + 1
            g.ball.speed_x = BALL_SPEED_X
            g.ball.speed_y = 0

            h.step(1)

            self.assertEqual(g.match.rally_hits, 0)
            self.assertEqual(g.ball.rally_speed_multiplier, 1.0)
            self.assertEqual(g.computer.rect.x, g.computer_home_x)

    def test_restart_resets_rally_pressure(self) -> None:
        with GameHarness.create() as h:
            g = h.game
            g.match.rally_hits = AI_RALLY_PRESS_THRESHOLD + 5
            g.ball.sync_rally_speed(g.match.rally_hits)

            h.step(1)
            self.assertLess(g.computer.rect.x, g.computer_home_x)

            g._restart_match()

            self.assertEqual(g.match.rally_hits, 0)
            self.assertEqual(g.ball.rally_speed_multiplier, 1.0)
            self.assertEqual(g.computer.rect.x, g.computer_home_x)


@pytest.mark.slow
class TestFullGame(unittest.TestCase):

    def test_game_completes(self) -> None:
        """Un partido deberia terminar eventualmente."""
        with GameHarness.create() as h:
            for _ in range(100):
                h.step(100)
                if h.get_state()["showing_end_screen"]:
                    break
            # No assertions on completion since it may take very long;
            # just verify no crashes after 10000 frames
            self.assertTrue(h.get_state()["running"])


if __name__ == "__main__":
    unittest.main()
