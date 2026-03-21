"""
tests/test_benchmark.py -- Benchmarks de rendimiento para detectar regresiones.

Ejecutan el game loop headless y verifican que el rendimiento no baje
de umbrales minimos. Los umbrales son generosos para funcionar en
GitHub Actions (runners lentos y con varianza).
"""

from __future__ import annotations

import time

import pytest

from pong.harness import GameHarness


@pytest.mark.slow
class TestBenchmark:
    """Benchmarks del game loop headless."""

    def test_fps_headless_baseline(self, game_harness: GameHarness) -> None:
        """El game loop headless mantiene >= 200 FPS sin subsistemas pesados."""
        h = game_harness
        # Warmup
        h.step(300)
        h.game.perf.reset()
        # Medicion
        h.step(600)
        perf = h.get_perf()
        assert perf["fps"]["avg"] >= 200, (
            f"FPS promedio {perf['fps']['avg']:.0f} por debajo del umbral 200"
        )

    def test_frame_budget_no_spikes(self, game_harness: GameHarness) -> None:
        """Ningun frame excede 50ms (20 FPS) durante juego headless."""
        h = game_harness
        h.step(600)
        perf = h.get_perf()
        assert perf["frame_worst_ms"] < 50, (
            f"Peor frame: {perf['frame_worst_ms']:.1f}ms (limite: 50ms)"
        )

    def test_update_throughput(self, game_harness: GameHarness) -> None:
        """Benchmark puro de logica (update) sin draw: >= 500 updates/s."""
        h = game_harness
        t0 = time.perf_counter()
        for _ in range(1000):
            h.game.update()
        elapsed = time.perf_counter() - t0
        updates_per_sec = 1000 / elapsed
        assert updates_per_sec >= 500, (
            f"Updates/s: {updates_per_sec:.0f} (minimo: 500)"
        )

    def test_perf_snapshot_structure(self, game_harness: GameHarness) -> None:
        """El snapshot de metricas tiene la estructura esperada."""
        h = game_harness
        h.step(60)
        perf = h.get_perf()
        assert "fps" in perf
        assert "avg" in perf["fps"]
        assert "min" in perf["fps"]
        assert "frame_worst_ms" in perf
        assert "llm" in perf
        assert "sd" in perf
        assert perf["frames"] >= 60
