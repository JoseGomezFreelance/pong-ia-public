"""Tests de persistencia y records (pong/save_manager.py)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pong.save_manager as sm


class TestEmptyHistory(unittest.TestCase):

    def test_structure(self) -> None:
        h = sm._empty_history()
        self.assertIn("version", h)
        self.assertIn("sessions", h)
        self.assertIn("records", h)
        self.assertIn("achievements", h)
        self.assertIn("career_stats", h)
        self.assertIn("phases_unlocked", h)
        self.assertIsInstance(h["sessions"], list)


class TestLoadHistory(unittest.TestCase):

    def test_returns_empty_when_no_file(self, tmp_path: Any = None) -> None:
        with patch.object(sm, "SAVE_FILE", Path("/nonexistent/path.json")):
            h = sm.load_history()
        self.assertEqual(h["sessions"], [])

    def test_returns_empty_on_corrupt_json(self, tmp_path: Any = None) -> None:
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{broken json")
            path = Path(f.name)
        try:
            with patch.object(sm, "SAVE_FILE", path):
                h = sm.load_history()
            self.assertEqual(h["sessions"], [])
        finally:
            path.unlink()

    def test_loads_valid_json(self) -> None:
        import tempfile
        data = {
            "version": "1.2",
            "sessions": [{"date": "2025-01-01", "winner": "jugador"}],
            "records": {},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = Path(f.name)
        try:
            with patch.object(sm, "SAVE_FILE", path):
                h = sm.load_history()
            self.assertEqual(len(h["sessions"]), 1)
            # Should migrate missing keys
            self.assertIn("achievements", h)
            self.assertIn("career_stats", h)
            self.assertIn("phases_unlocked", h)
        finally:
            path.unlink()

    def test_returns_empty_on_missing_sessions_key(self) -> None:
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"version": "1.0"}, f)
            path = Path(f.name)
        try:
            with patch.object(sm, "SAVE_FILE", path):
                h = sm.load_history()
            self.assertEqual(h["sessions"], [])
        finally:
            path.unlink()


class TestComputeRecords(unittest.TestCase):

    def test_empty_sessions(self) -> None:
        records = sm.compute_records([])
        self.assertEqual(records, {})

    def test_single_session_player_win(self) -> None:
        sessions = [{
            "date": "2025-01-01",
            "winner": "jugador",
            "player_points_total": 15,
            "elapsed_seconds": 120,
            "max_rally": 8,
            "longest_player_streak": 3,
            "point_differential": 5,
        }]
        records = sm.compute_records(sessions)
        self.assertEqual(records["max_score"]["value"], 15)
        self.assertEqual(records["fastest_win"]["value"], 120)
        self.assertEqual(records["longest_rally"]["value"], 8)
        self.assertEqual(records["longest_streak"]["value"], 3)
        self.assertEqual(records["biggest_domination"]["value"], 5)

    def test_computer_win_no_fastest_win(self) -> None:
        sessions = [{
            "date": "2025-01-01",
            "winner": "ordenador",
            "player_points_total": 10,
            "elapsed_seconds": 60,
            "max_rally": 5,
            "longest_player_streak": 1,
            "point_differential": -3,
        }]
        records = sm.compute_records(sessions)
        # fastest_win and biggest_domination only for player wins
        self.assertNotIn("fastest_win", records)
        self.assertNotIn("biggest_domination", records)
        self.assertIn("max_score", records)

    def test_multiple_sessions_best_wins(self) -> None:
        sessions = [
            {
                "date": "2025-01-01", "winner": "jugador",
                "player_points_total": 10, "elapsed_seconds": 200,
                "max_rally": 5, "longest_player_streak": 2,
                "point_differential": 3,
            },
            {
                "date": "2025-01-02", "winner": "jugador",
                "player_points_total": 20, "elapsed_seconds": 100,
                "max_rally": 12, "longest_player_streak": 5,
                "point_differential": 8,
            },
        ]
        records = sm.compute_records(sessions)
        self.assertEqual(records["max_score"]["value"], 20)
        self.assertEqual(records["max_score"]["session_index"], 1)
        self.assertEqual(records["fastest_win"]["value"], 100)
        self.assertEqual(records["longest_rally"]["value"], 12)


class TestFormatRecordValue(unittest.TestCase):

    def test_fastest_win(self) -> None:
        self.assertEqual(sm.format_record_value("fastest_win", 125), "2:05")

    def test_longest_rally(self) -> None:
        self.assertEqual(sm.format_record_value("longest_rally", 15), "15 golpes")

    def test_biggest_domination(self) -> None:
        self.assertEqual(sm.format_record_value("biggest_domination", 7), "+7 pts")

    def test_max_score(self) -> None:
        self.assertEqual(sm.format_record_value("max_score", 42), "42 pts")

    def test_longest_streak(self) -> None:
        self.assertEqual(sm.format_record_value("longest_streak", 5), "5 pts")


class TestFormatRecordDate(unittest.TestCase):

    def test_valid_iso_date(self) -> None:
        self.assertEqual(sm.format_record_date("2025-03-15T14:30:00"), "15/03/2025")

    def test_invalid_date(self) -> None:
        self.assertEqual(sm.format_record_date("not-a-date"), "\u2014")

    def test_empty_string(self) -> None:
        self.assertEqual(sm.format_record_date(""), "\u2014")


class TestFormatTime(unittest.TestCase):

    def test_minutes_seconds(self) -> None:
        self.assertEqual(sm._format_time(125), "2:05")

    def test_hours(self) -> None:
        self.assertEqual(sm._format_time(3661), "1:01:01")

    def test_zero(self) -> None:
        self.assertEqual(sm._format_time(0), "0:00")


class TestComputeDerivedStats(unittest.TestCase):

    def test_empty_history(self) -> None:
        history = sm._empty_history()
        stats = sm.compute_derived_stats(history)
        self.assertEqual(stats["total_matches"], 0)
        self.assertEqual(stats["win_rate"], 0)
        self.assertEqual(stats["total_time"], 0)

    def test_with_sessions_and_career(self) -> None:
        history = {
            "sessions": [
                {"elapsed_seconds": 100, "computer_points_total": 5},
                {"elapsed_seconds": 200, "computer_points_total": 8},
            ],
            "career_stats": {
                "total_matches": 2,
                "total_victories": 1,
                "total_points_scored": 25,
                "total_rallies": 30,
                "moods_experienced": ["neutral", "tenso"],
            },
            "records": {
                "longest_rally": {"value": 10},
                "max_score": {"value": 20},
            },
        }
        stats = sm.compute_derived_stats(history)
        self.assertEqual(stats["total_matches"], 2)
        self.assertEqual(stats["total_victories"], 1)
        self.assertEqual(stats["total_defeats"], 1)
        self.assertEqual(stats["win_rate"], 50)
        self.assertEqual(stats["total_time"], 300)
        self.assertEqual(stats["longest_match"], 200)
        self.assertEqual(stats["total_computer_points"], 13)
        self.assertEqual(stats["rec_longest_rally"], "10 golpes")
        self.assertEqual(stats["rec_max_score"], "20 pts")
        self.assertEqual(stats["rec_fastest_win"], "\u2014")


class TestSaveSession(unittest.TestCase):

    def test_save_and_load(self, tmp_path: Any = None) -> None:
        """save_session persiste datos y devuelve records correctos."""
        import tempfile
        tmpdir = Path(tempfile.mkdtemp())
        save_dir = tmpdir / "saves"
        save_file = save_dir / "game_history.json"

        with patch.object(sm, "SAVE_DIR", save_dir), \
             patch.object(sm, "SAVE_FILE", save_file):
            session = {
                "winner": "jugador",
                "player_points_total": 18,
                "elapsed_seconds": 90,
                "max_rally": 10,
                "longest_player_streak": 4,
                "point_differential": 6,
            }
            records, new_keys, phases = sm.save_session(session)
            self.assertIn("max_score", records)
            self.assertIn("max_score", new_keys)

            # Verify file was written
            self.assertTrue(save_file.exists())
            with open(save_file) as f:
                data = json.load(f)
            self.assertEqual(len(data["sessions"]), 1)

        # Cleanup
        import shutil
        shutil.rmtree(tmpdir)


class TestCheckPhaseUnlocks(unittest.TestCase):

    def test_no_unlock_below_threshold(self) -> None:
        history = {
            "sessions": [{"elapsed_seconds": 60}],
            "phases_unlocked": {},
        }
        unlocked = sm.check_phase_unlocks(history)
        self.assertEqual(unlocked, [])

    def test_unlock_imagegen_at_threshold(self) -> None:
        from pong.config.media import IMAGEGEN_UNLOCK_TOTAL_SECONDS

        history = {
            "sessions": [{"elapsed_seconds": IMAGEGEN_UNLOCK_TOTAL_SECONDS}],
            "phases_unlocked": {},
        }
        unlocked = sm.check_phase_unlocks(history)
        self.assertIn("imagegen", unlocked)
        self.assertIn("imagegen", history["phases_unlocked"])

    def test_no_duplicate_unlock(self) -> None:
        from pong.config.media import IMAGEGEN_UNLOCK_TOTAL_SECONDS

        history = {
            "sessions": [{"elapsed_seconds": IMAGEGEN_UNLOCK_TOTAL_SECONDS + 100}],
            "phases_unlocked": {"imagegen": {"unlocked_at": "2025-01-01"}},
        }
        unlocked = sm.check_phase_unlocks(history)
        self.assertEqual(unlocked, [])


if __name__ == "__main__":
    unittest.main()
