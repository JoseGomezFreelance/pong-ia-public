"""Tests para pong/perf.py — metricas de rendimiento."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pong.perf import PerformanceMetrics


class TestPerformanceMetrics(unittest.TestCase):
    """Tests para PerformanceMetrics."""

    def test_initial_snapshot(self) -> None:
        perf = PerformanceMetrics()
        snap = perf.snapshot()
        self.assertEqual(snap["fps"]["avg"], 0.0)
        self.assertEqual(snap["fps"]["min"], 0.0)
        self.assertEqual(snap["llm"]["calls"], 0)
        self.assertEqual(snap["sd"]["calls"], 0)
        self.assertEqual(snap["frames"], 0)

    def test_tick_frame_updates_fps(self) -> None:
        perf = PerformanceMetrics()
        # Simulate several frames
        for _ in range(10):
            perf.tick_frame()
        snap = perf.snapshot()
        self.assertEqual(snap["frames"], 10)
        self.assertGreater(snap["fps"]["avg"], 0.0)
        self.assertGreater(snap["fps"]["min"], 0.0)

    def test_record_llm(self) -> None:
        perf = PerformanceMetrics()
        perf.record_llm(0.5, "test1")
        perf.record_llm(1.0, "test2")
        snap = perf.snapshot()
        self.assertEqual(snap["llm"]["calls"], 2)
        self.assertAlmostEqual(snap["llm"]["avg_ms"], 750.0, places=0)
        self.assertAlmostEqual(snap["llm"]["max_ms"], 1000.0, places=0)

    def test_record_sd(self) -> None:
        perf = PerformanceMetrics()
        perf.record_sd(2.0)
        perf.record_sd(3.0)
        snap = perf.snapshot()
        self.assertEqual(snap["sd"]["calls"], 2)
        self.assertAlmostEqual(snap["sd"]["avg_ms"], 2500.0, places=0)
        self.assertAlmostEqual(snap["sd"]["max_ms"], 3000.0, places=0)

    def test_reset(self) -> None:
        perf = PerformanceMetrics()
        perf.tick_frame()
        perf.tick_frame()
        perf.record_llm(1.0)
        perf.record_sd(2.0)
        perf.reset()
        snap = perf.snapshot()
        self.assertEqual(snap["frames"], 0)
        self.assertEqual(snap["llm"]["calls"], 0)
        self.assertEqual(snap["sd"]["calls"], 0)
        self.assertEqual(snap["fps"]["avg"], 0.0)

    def test_summary_line_basic(self) -> None:
        perf = PerformanceMetrics()
        line = perf.summary_line()
        self.assertIn("FPS", line)

    def test_summary_line_with_llm(self) -> None:
        perf = PerformanceMetrics()
        perf.record_llm(0.5, "test")
        line = perf.summary_line()
        self.assertIn("LLM", line)
        self.assertIn("1 calls", line)

    def test_summary_line_with_sd(self) -> None:
        perf = PerformanceMetrics()
        perf.record_sd(1.0)
        line = perf.summary_line()
        self.assertIn("SD", line)

    def test_export_json(self) -> None:
        perf = PerformanceMetrics()
        perf.tick_frame()
        perf.record_llm(0.1)

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "subdir" / "perf.json"
            perf.export_json(path)
            self.assertTrue(path.exists())
            data = json.loads(path.read_text())
            self.assertIn("fps", data)
            self.assertIn("llm", data)
            self.assertIn("timestamp", data)

    def test_frame_worst_ms(self) -> None:
        perf = PerformanceMetrics()
        perf.tick_frame()
        perf.tick_frame()
        snap = perf.snapshot()
        self.assertIn("frame_worst_ms", snap)
        self.assertGreaterEqual(snap["frame_worst_ms"], 0.0)

    def test_duration_seconds(self) -> None:
        perf = PerformanceMetrics()
        snap = perf.snapshot()
        self.assertIn("duration_seconds", snap)
        self.assertGreaterEqual(snap["duration_seconds"], 0.0)
