"""Recolector ligero de metricas de rendimiento para Pong-IA."""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, NamedTuple


class _LLMRecord(NamedTuple):
    timestamp: float
    duration: float
    label: str


class _SDRecord(NamedTuple):
    timestamp: float
    duration: float


_FRAME_WINDOW = 120
_LLM_MAX = 50
_SD_MAX = 20


class PerformanceMetrics:
    """Metricas de FPS, latencia LLM y tiempo de generacion SD."""

    def __init__(self) -> None:
        self._frame_times: deque[float] = deque(maxlen=_FRAME_WINDOW)
        self._last_tick: float | None = None
        self._frame_count: int = 0
        self._start_time: float = time.perf_counter()

        self._llm_records: deque[_LLMRecord] = deque(maxlen=_LLM_MAX)
        self._llm_lock = threading.Lock()

        self._sd_records: deque[_SDRecord] = deque(maxlen=_SD_MAX)

    # -- Registro --

    def tick_frame(self) -> None:
        now = time.perf_counter()
        if self._last_tick is not None:
            self._frame_times.append(now - self._last_tick)
        self._last_tick = now
        self._frame_count += 1

    def record_llm(self, duration: float, label: str = "") -> None:
        with self._llm_lock:
            self._llm_records.append(
                _LLMRecord(time.perf_counter(), duration, label)
            )

    def record_sd(self, duration: float) -> None:
        self._sd_records.append(_SDRecord(time.perf_counter(), duration))

    def reset(self) -> None:
        self._frame_times.clear()
        self._last_tick = None
        self._frame_count = 0
        self._start_time = time.perf_counter()
        with self._llm_lock:
            self._llm_records.clear()
        self._sd_records.clear()

    # -- Consulta --

    def snapshot(self) -> dict[str, Any]:
        frames = list(self._frame_times)
        with self._llm_lock:
            llm = list(self._llm_records)
        sd = list(self._sd_records)

        fps_avg = 0.0
        fps_min = 0.0
        frame_worst_ms = 0.0
        if frames:
            avg_dt = sum(frames) / len(frames)
            fps_avg = 1.0 / avg_dt if avg_dt > 0 else 0.0
            worst_dt = max(frames)
            fps_min = 1.0 / worst_dt if worst_dt > 0 else 0.0
            frame_worst_ms = worst_dt * 1000.0

        llm_durations = [r.duration for r in llm]
        sd_durations = [r.duration for r in sd]

        return {
            "duration_seconds": round(
                time.perf_counter() - self._start_time, 1
            ),
            "frames": self._frame_count,
            "fps": {
                "avg": round(fps_avg, 1),
                "min": round(fps_min, 1),
                "samples": len(frames),
            },
            "frame_worst_ms": round(frame_worst_ms, 1),
            "llm": {
                "calls": len(llm_durations),
                "avg_ms": round(
                    sum(llm_durations) / len(llm_durations) * 1000, 1
                )
                if llm_durations
                else 0.0,
                "max_ms": round(max(llm_durations) * 1000, 1)
                if llm_durations
                else 0.0,
            },
            "sd": {
                "calls": len(sd_durations),
                "avg_ms": round(
                    sum(sd_durations) / len(sd_durations) * 1000, 1
                )
                if sd_durations
                else 0.0,
                "max_ms": round(max(sd_durations) * 1000, 1)
                if sd_durations
                else 0.0,
            },
        }

    def summary_line(self) -> str:
        s = self.snapshot()
        fps = s["fps"]
        llm = s["llm"]
        sd = s["sd"]
        parts = [f"FPS avg={fps['avg']:.0f} min={fps['min']:.0f}"]
        if llm["calls"]:
            parts.append(
                f"LLM {llm['calls']} calls avg={llm['avg_ms']:.0f}ms"
            )
        if sd["calls"]:
            parts.append(f"SD {sd['calls']} calls avg={sd['avg_ms']:.0f}ms")
        return " | ".join(parts)

    def export_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self.snapshot()
        data["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
