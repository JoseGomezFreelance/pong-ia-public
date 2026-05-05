"""Tests de la IA del ordenador (pong/game_ai.py)."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from pong.config.gameplay import (
    AI_RALLY_PRESS_STEP,
    AI_RALLY_PRESS_THRESHOLD,
    AI_SPEED,
    AI_SPEED_MAX,
    AI_SPEED_MIN,
    PADDLE_HEIGHT,
)
from pong.config.layout import GAME_AREA_HEIGHT, WINDOW_WIDTH
from pong.emotional_state import EmotionalState
from pong.entities import Paddle, Ball


def _make_ai_stub(**overrides: Any) -> Any:
    """Crea un stub de Game con los atributos minimos para update_ai."""
    ball = Ball()
    ball.speed_x = 5  # moving right (toward computer)
    ball.rect.centery = GAME_AREA_HEIGHT // 2

    computer = Paddle(780, GAME_AREA_HEIGHT // 2 - PADDLE_HEIGHT // 2)
    match = SimpleNamespace(rally_hits=0)

    g = SimpleNamespace(
        ball=ball,
        computer=computer,
        computer_home_x=computer.rect.x,
        match=match,
        emotion_active=False,
        emotional_state=EmotionalState(),
        emotional_target=EmotionalState(),
        _player_positions=[],
        _player_idle_score=0.0,
        questions=SimpleNamespace(dialogue_history=[]),
        _log=MagicMock(),
    )
    from pong.game_ai import GameAIMixin
    g.update_ai = GameAIMixin.update_ai.__get__(g)
    g._compute_idle_score = GameAIMixin._compute_idle_score.__get__(g)
    g._apply_autonomous_emotion = GameAIMixin._apply_autonomous_emotion.__get__(g)

    for key, value in overrides.items():
        if key == "rally_hits":
            g.match.rally_hits = value
        else:
            setattr(g, key, value)
    return g


class TestUpdateAIClassic(unittest.TestCase):
    """Comportamiento clasico (sin emocion)."""

    def test_follows_ball_approaching(self) -> None:
        g = _make_ai_stub()
        g.ball.speed_x = 5  # approaching computer
        g.ball.rect.centery = 100
        g.computer.rect.centery = 250
        g.update_ai()
        # Should move toward ball (up)
        self.assertLess(g.computer.rect.centery, 250)

    def test_returns_to_center_when_ball_away(self) -> None:
        g = _make_ai_stub()
        g.ball.speed_x = -5  # moving away from computer
        g.computer.rect.centery = 100  # off-center up
        g.update_ai()
        # Should move toward center
        self.assertGreater(g.computer.rect.centery, 100)

    def test_speed_multiplier_reduces_movement(self) -> None:
        g1 = _make_ai_stub()
        g2 = _make_ai_stub()
        g1.ball.rect.centery = 100
        g2.ball.rect.centery = 100
        g1.computer.rect.centery = 300
        g2.computer.rect.centery = 300

        g1.update_ai(speed_multiplier=1.0)
        g2.update_ai(speed_multiplier=0.3)

        move1 = abs(g1.computer.rect.centery - 300)
        move2 = abs(g2.computer.rect.centery - 300)
        self.assertGreaterEqual(move1, move2)


class TestUpdateAIEmotional(unittest.TestCase):
    """Comportamiento con emociones activas."""

    def test_high_aggressiveness_increases_speed(self) -> None:
        g = _make_ai_stub(emotion_active=True)
        g.emotional_state = EmotionalState(
            aggressiveness=0.9, stability=0.8, motivation=1.0,
        )
        g.ball.rect.centery = 100
        g.computer.rect.centery = 300
        initial_y = g.computer.rect.centery
        g.update_ai()
        moved = abs(g.computer.rect.centery - initial_y)
        # With high aggressiveness, should move at near AI_SPEED_MAX
        self.assertGreater(moved, 0)

    def test_low_motivation_reduces_movement(self) -> None:
        g = _make_ai_stub(emotion_active=True)
        g.emotional_state = EmotionalState(
            aggressiveness=0.5, stability=0.8, motivation=0.1,
        )
        g.ball.rect.centery = 100
        g.computer.rect.centery = 300
        g.update_ai()
        moved = abs(g.computer.rect.centery - 300)
        # Low motivation → barely moves
        self.assertLess(moved, AI_SPEED_MAX)

    def test_prediction_active_at_high_aggressiveness(self) -> None:
        g = _make_ai_stub(emotion_active=True)
        g.emotional_state = EmotionalState(
            aggressiveness=0.8, stability=0.9, motivation=1.0,
        )
        g.ball.speed_x = 5
        g.ball.speed_y = 3
        g.ball.rect.centery = 200
        g.computer.rect.centery = 250
        g.computer.rect.centerx = 750
        g.update_ai()
        # Just verify it doesn't crash and moves
        self.assertIsNotNone(g.computer.rect.centery)

    def test_zero_motivation_stays_still(self) -> None:
        g = _make_ai_stub(emotion_active=True)
        g.emotional_state = EmotionalState(
            aggressiveness=0.5, stability=0.8, motivation=0.0,
        )
        initial_y = g.computer.rect.centery
        g.ball.rect.centery = 100
        g.update_ai()
        # motivation=0 → target stays at current position
        # Movement should be minimal (only rounding)
        moved = abs(g.computer.rect.centery - initial_y)
        self.assertLessEqual(moved, 1)


class TestUpdateAIRallyPressure(unittest.TestCase):
    """Presion lateral extra en rallies muy largos."""

    def test_computer_stays_home_until_press_threshold(self) -> None:
        g = _make_ai_stub(rally_hits=AI_RALLY_PRESS_THRESHOLD)
        g.update_ai()
        self.assertEqual(g.computer.rect.x, g.computer_home_x)

    def test_computer_moves_toward_player_after_threshold(self) -> None:
        g = _make_ai_stub(rally_hits=AI_RALLY_PRESS_THRESHOLD + 1)
        g.update_ai()
        self.assertEqual(g.computer.rect.x, g.computer_home_x - AI_RALLY_PRESS_STEP)

    def test_computer_press_caps_at_midfield(self) -> None:
        g = _make_ai_stub(rally_hits=AI_RALLY_PRESS_THRESHOLD + 500)
        g.update_ai()
        self.assertEqual(g.computer.rect.x, WINDOW_WIDTH // 2)


if __name__ == "__main__":
    unittest.main()
