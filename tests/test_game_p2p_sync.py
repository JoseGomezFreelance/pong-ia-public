"""Tests para la resincronizacion de records locales hacia la red P2P."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pong.save_manager as sm
from pong.harness import GameHarness


class TestGameP2PSync(unittest.TestCase):
    """Valida que Game republique records locales sin reiniciar."""

    def _make_tmp(self) -> tuple[Path, Path, Path]:
        tmpdir = Path(tempfile.mkdtemp())
        save_dir = tmpdir / "saves"
        save_file = save_dir / "game_history.json"
        return tmpdir, save_dir, save_file

    @staticmethod
    def _sample_session() -> dict[str, int | str]:
        return {
            "winner": "jugador",
            "player_points_total": 18,
            "elapsed_seconds": 90,
            "max_rally": 10,
            "longest_player_streak": 4,
            "point_differential": 6,
        }

    def test_sync_helper_broadcasts_recomputed_local_entries(self) -> None:
        tmpdir, save_dir, save_file = self._make_tmp()
        try:
            with patch.object(sm, "SAVE_DIR", save_dir), \
                 patch.object(sm, "SAVE_FILE", save_file), \
                 patch("pong.save_manager._get_platform_uuid", return_value="TEST-UUID-1234"):
                sm.set_player_alias("Tester")
                sm.save_session(self._sample_session())

                with GameHarness.create() as h:
                    g = h.game
                    g._peer_network = Mock()

                    g._sync_local_records_to_peer_network()

                    g._peer_network.broadcast_records.assert_called_once()
                    entries = g._peer_network.broadcast_records.call_args.args[0]
                    self.assertGreater(len(entries), 0)
                    self.assertIn("max_score", {entry.category for entry in entries})
                    self.assertTrue(all(entry.alias == "Tester" for entry in entries))
        finally:
            import shutil
            shutil.rmtree(tmpdir)

    def test_save_game_republishes_records_when_peer_network_is_active(self) -> None:
        tmpdir, save_dir, save_file = self._make_tmp()
        try:
            with patch.object(sm, "SAVE_DIR", save_dir), \
                 patch.object(sm, "SAVE_FILE", save_file), \
                 patch("pong.save_manager._get_platform_uuid", return_value="TEST-UUID-1234"):
                sm.set_player_alias("Tester")

                with GameHarness.create() as h:
                    g = h.game
                    g._peer_network = Mock()
                    g.match.score.player_sets = 1
                    g.match.score.computer_sets = 0
                    g.match.max_rally_hits = 7
                    g.match.score_timeline = [
                        {"description": "Punto del jugador", "scoreboard": "15-0"},
                        {"description": "Punto del jugador", "scoreboard": "30-0"},
                    ]
                    g.match_summary_text = "Resumen de prueba."
                    g.game_end_time = g.game_start_time + 12.3

                    g._save_game()

                    g._peer_network.broadcast_records.assert_called_once()
                    entries = g._peer_network.broadcast_records.call_args.args[0]
                    categories = {entry.category for entry in entries}
                    self.assertIn("max_score", categories)
                    self.assertIn("fastest_win", categories)
                    self.assertEqual(len(sm.load_history()["sessions"]), 1)
        finally:
            import shutil
            shutil.rmtree(tmpdir)
