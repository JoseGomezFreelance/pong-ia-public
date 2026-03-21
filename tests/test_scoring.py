"""Tests del sistema de puntuacion (pong/scoring.py)."""
from __future__ import annotations

import unittest

from pong.config.gameplay import GAME_POINTS_TO_WIN, MATCH_SETS_TO_WIN, SET_GAMES_TO_WIN
from pong.scoring import ScoreState, apply_point


class TestScoreState(unittest.TestCase):

    def test_defaults_are_zero(self) -> None:
        s = ScoreState()
        self.assertEqual(s.player_points, 0)
        self.assertEqual(s.computer_points, 0)
        self.assertEqual(s.player_games, 0)
        self.assertEqual(s.computer_games, 0)
        self.assertEqual(s.player_sets, 0)
        self.assertEqual(s.computer_sets, 0)

    def test_scoreboard_text(self) -> None:
        s = ScoreState(player_sets=1, computer_games=2, player_points=2)
        text = s.scoreboard_text()
        self.assertIn("Sets 1-0", text)
        self.assertIn("Juegos 0-2", text)
        self.assertIn("Puntos 2-0", text)

    def test_display_score_line(self) -> None:
        s = ScoreState(player_sets=1, computer_sets=1, player_games=1, computer_games=0)
        line = s.display_score_line()
        self.assertIn("SETS 1-1", line)
        self.assertIn("JUEGOS 1-0", line)
        self.assertIn("|", line)


class TestApplyPointBasic(unittest.TestCase):

    def test_player_scores_point(self) -> None:
        s = ScoreState()
        result = apply_point(s, "player")
        self.assertEqual(s.player_points, 1)
        self.assertEqual(result.scorer_id, "jugador")
        self.assertEqual(result.scoring_streak, 1)
        self.assertTrue(result.point_won)
        self.assertFalse(result.game_won)

    def test_computer_scores_point(self) -> None:
        s = ScoreState()
        result = apply_point(s, "computer")
        self.assertEqual(s.computer_points, 1)
        self.assertEqual(result.scorer_id, "ordenador")
        self.assertIn("ordenador", result.event_label)

    def test_streak_increments(self) -> None:
        s = ScoreState()
        apply_point(s, "player")
        result = apply_point(s, "player")
        self.assertEqual(result.scoring_streak, 2)
        self.assertEqual(s.player_point_streak, 2)
        self.assertEqual(s.computer_point_streak, 0)

    def test_streak_resets_on_opponent_point(self) -> None:
        s = ScoreState()
        apply_point(s, "player")
        apply_point(s, "player")
        apply_point(s, "computer")
        self.assertEqual(s.player_point_streak, 0)
        self.assertEqual(s.computer_point_streak, 1)


class TestApplyPointGame(unittest.TestCase):

    def _win_game(self, s: ScoreState, winner: str) -> None:
        for _ in range(GAME_POINTS_TO_WIN):
            apply_point(s, winner)

    def test_player_wins_game(self) -> None:
        s = ScoreState()
        result = None
        for _ in range(GAME_POINTS_TO_WIN):
            result = apply_point(s, "player")
        assert result is not None
        self.assertTrue(result.game_won)
        self.assertIn("juego", result.event_label)
        self.assertEqual(s.player_points, 0)  # reset
        self.assertEqual(s.computer_points, 0)
        self.assertEqual(s.player_games, 1)

    def test_computer_wins_game(self) -> None:
        s = ScoreState()
        for _ in range(GAME_POINTS_TO_WIN):
            result = apply_point(s, "computer")
        self.assertTrue(result.game_won)
        self.assertEqual(s.computer_games, 1)


class TestApplyPointSet(unittest.TestCase):

    def _win_game(self, s: ScoreState, winner: str) -> None:
        for _ in range(GAME_POINTS_TO_WIN):
            apply_point(s, winner)

    def test_player_wins_set(self) -> None:
        s = ScoreState()
        result = None
        for _ in range(SET_GAMES_TO_WIN):
            for _ in range(GAME_POINTS_TO_WIN):
                result = apply_point(s, "player")
        assert result is not None
        self.assertTrue(result.set_won)
        # Con MATCH_SETS_TO_WIN=1, ganar un set = ganar el partido
        if MATCH_SETS_TO_WIN == 1:
            self.assertIn("partido", result.event_label)
        else:
            self.assertIn("set", result.event_label.lower())
        self.assertEqual(s.player_sets, 1)


class TestApplyPointMatch(unittest.TestCase):

    def test_player_wins_match(self) -> None:
        s = ScoreState()
        result = None
        for _ in range(MATCH_SETS_TO_WIN):
            for _ in range(SET_GAMES_TO_WIN):
                for _ in range(GAME_POINTS_TO_WIN):
                    result = apply_point(s, "player")
        assert result is not None
        self.assertTrue(result.match_won)
        self.assertIn("partido", result.event_label)
        self.assertEqual(result.scorer_id, "jugador")

    def test_computer_wins_match(self) -> None:
        s = ScoreState()
        result = None
        for _ in range(MATCH_SETS_TO_WIN):
            for _ in range(SET_GAMES_TO_WIN):
                for _ in range(GAME_POINTS_TO_WIN):
                    result = apply_point(s, "computer")
        assert result is not None
        self.assertTrue(result.match_won)
        self.assertIn("partido", result.event_label)
        self.assertEqual(result.scorer_id, "ordenador")

    def test_new_set_resets_games(self) -> None:
        """Si el partido no acaba tras un set, los juegos se resetean."""
        # Solo aplica si MATCH_SETS_TO_WIN > 1
        if MATCH_SETS_TO_WIN <= 1:
            self.skipTest("MATCH_SETS_TO_WIN=1, no hay sets intermedios")
        s = ScoreState()
        for _ in range(SET_GAMES_TO_WIN):
            for _ in range(GAME_POINTS_TO_WIN):
                apply_point(s, "player")
        self.assertEqual(s.player_sets, 1)
        self.assertEqual(s.player_games, 0)
        self.assertEqual(s.computer_games, 0)


class TestFullMatch(unittest.TestCase):

    def test_alternating_points_complete_match(self) -> None:
        """Simula un partido completo donde el jugador siempre gana."""
        s = ScoreState()
        total_points = (
            GAME_POINTS_TO_WIN * SET_GAMES_TO_WIN * MATCH_SETS_TO_WIN
        )
        for i in range(total_points):
            result = apply_point(s, "player")
        self.assertTrue(result.match_won)


if __name__ == "__main__":
    unittest.main()
