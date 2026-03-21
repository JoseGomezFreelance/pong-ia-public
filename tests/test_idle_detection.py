"""Pruebas de deteccion de inactividad del jugador y ajuste emocional autonomo."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from pong.config.gameplay import (
    PLAYER_IDLE_VARIANCE_THRESHOLD,
    PLAYER_TRACK_WINDOW,
    RALLY_IDLE_RAMP,
    RALLY_IDLE_THRESHOLD,
)
from pong.emotional_state import EmotionalState
from pong.question_system import DialogueEntry


def _make_stub_game(**overrides: Any) -> Any:
    """Crea un objeto con los atributos minimos de Game para testear."""
    g = SimpleNamespace(
        _player_positions=[],
        _player_idle_score=0.0,
        rally_hits=0,
        emotional_target=EmotionalState(),
        emotion_active=False,
        questions=SimpleNamespace(dialogue_history=[]),
        _log=MagicMock(),
    )
    # Bind methods from Game class
    from pong.game import Game

    g._compute_idle_score = Game._compute_idle_score.__get__(g)
    g._apply_autonomous_emotion = Game._apply_autonomous_emotion.__get__(g)
    for key, value in overrides.items():
        setattr(g, key, value)
    return g


class ComputeIdleScoreTests(unittest.TestCase):

    def test_too_few_samples_returns_zero(self) -> None:
        g = _make_stub_game(_player_positions=[250] * 5)
        self.assertAlmostEqual(g._compute_idle_score(), 0.0)

    def test_all_same_position_returns_one(self) -> None:
        g = _make_stub_game(_player_positions=[250] * 20)
        self.assertAlmostEqual(g._compute_idle_score(), 1.0)

    def test_high_variance_returns_zero(self) -> None:
        # Positions alternating widely
        positions = [50, 450] * 10
        g = _make_stub_game(_player_positions=positions)
        self.assertAlmostEqual(g._compute_idle_score(), 0.0)

    def test_low_variance_near_threshold_returns_partial(self) -> None:
        # Create positions with variance just above threshold
        # Mean=250, variance=200 (between 100 and 400)
        # sqrt(200) ≈ 14 px deviation
        import math

        dev = math.sqrt(PLAYER_IDLE_VARIANCE_THRESHOLD * 2)
        positions = [250 + dev, 250 - dev] * 10
        g = _make_stub_game(_player_positions=positions)
        score = g._compute_idle_score()
        self.assertGreater(score, 0.0)
        self.assertLess(score, 1.0)

    def test_player_at_top_idle(self) -> None:
        # Player stuck at top (Si position)
        g = _make_stub_game(_player_positions=[3] * 20)
        self.assertAlmostEqual(g._compute_idle_score(), 1.0)

    def test_player_at_bottom_idle(self) -> None:
        # Player stuck at bottom (No position)
        g = _make_stub_game(_player_positions=[417] * 20)
        self.assertAlmostEqual(g._compute_idle_score(), 1.0)


class ApplyAutonomousEmotionTests(unittest.TestCase):

    def test_no_effect_when_active_player(self) -> None:
        g = _make_stub_game(
            _player_positions=[50, 200, 350, 100, 400, 250, 150, 300] * 3,
            rally_hits=50,
        )
        original_aggr = g.emotional_target.aggressiveness
        g._apply_autonomous_emotion()
        # Active player → idle_score ~0 → urgency ~0 → no change
        self.assertAlmostEqual(g.emotional_target.aggressiveness, original_aggr)

    def test_no_effect_when_short_rally(self) -> None:
        g = _make_stub_game(
            _player_positions=[250] * 20,
            rally_hits=5,  # Below threshold
        )
        original_aggr = g.emotional_target.aggressiveness
        g._apply_autonomous_emotion()
        self.assertAlmostEqual(g.emotional_target.aggressiveness, original_aggr)

    def test_raises_aggressiveness_on_idle_long_rally(self) -> None:
        g = _make_stub_game(
            _player_positions=[250] * 20,
            rally_hits=RALLY_IDLE_THRESHOLD + RALLY_IDLE_RAMP,  # 45 = max urgency
        )
        g.emotional_target.aggressiveness = 0.3  # Low initial
        g._apply_autonomous_emotion()
        self.assertGreater(g.emotional_target.aggressiveness, 0.7)

    def test_activates_emotion_if_inactive(self) -> None:
        g = _make_stub_game(
            _player_positions=[250] * 20,
            rally_hits=30,
            emotion_active=False,
        )
        g._apply_autonomous_emotion()
        self.assertTrue(g.emotion_active)

    def test_monotone_duda_increases_urgency(self) -> None:
        g = _make_stub_game(
            _player_positions=[250] * 20,
            rally_hits=20,
        )
        g.questions.dialogue_history = [
            DialogueEntry("Pregunta uno?", "Duda", 30),
            DialogueEntry("Pregunta dos?", "Duda", 60),
            DialogueEntry("Pregunta tres?", "Duda", 90),
        ]
        g.emotional_target.aggressiveness = 0.3
        g._apply_autonomous_emotion()
        # With monotone bonus, should be higher than without
        self.assertGreater(g.emotional_target.aggressiveness, 0.5)

    def test_monotone_si_also_triggers(self) -> None:
        g = _make_stub_game(
            _player_positions=[3] * 20,  # top = "Si"
            rally_hits=25,
        )
        g.questions.dialogue_history = [
            DialogueEntry("Pregunta?", "Si", 30),
            DialogueEntry("Otra pregunta?", "Si", 60),
        ]
        g.emotional_target.aggressiveness = 0.3
        g._apply_autonomous_emotion()
        self.assertGreater(g.emotional_target.aggressiveness, 0.5)

    def test_does_not_lower_llm_aggressiveness(self) -> None:
        """El ajuste autonomo pone suelo, no techo."""
        g = _make_stub_game(
            _player_positions=[250] * 20,
            rally_hits=30,
        )
        g.emotional_target.aggressiveness = 0.95  # LLM ya puso alta
        g._apply_autonomous_emotion()
        # Should NOT lower it
        self.assertGreaterEqual(g.emotional_target.aggressiveness, 0.95)

    def test_mood_tag_irritado_at_high_urgency(self) -> None:
        g = _make_stub_game(
            _player_positions=[250] * 20,
            rally_hits=RALLY_IDLE_THRESHOLD + RALLY_IDLE_RAMP,
        )
        g._apply_autonomous_emotion()
        self.assertEqual(g.emotional_target.mood_tag, "irritado")

    def test_mood_tag_aburrido_at_medium_urgency(self) -> None:
        g = _make_stub_game(
            _player_positions=[250] * 20,
            rally_hits=RALLY_IDLE_THRESHOLD + 10,  # Moderate urgency
        )
        g._apply_autonomous_emotion()
        self.assertIn(g.emotional_target.mood_tag, ("aburrido", "irritado"))


if __name__ == "__main__":
    unittest.main()
