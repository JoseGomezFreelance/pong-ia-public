"""Pruebas del retraso minimo del resumen final en NarrationBridge."""
from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import patch

from pong.narration_bridge import NarrationBridge


class _FakeLLMProvider:
    """Provider LLM fake para instanciar NarrationBridge sin cargar modelo."""

    enabled = False
    status_message = "Test: fake provider"

    def chat_completion(self, messages: list[dict[str, str]], **_kw: Any) -> dict[str, Any]:
        return {"choices": [{"message": {"content": ""}}]}


class NarrationBridgeSummaryTests(unittest.TestCase):
    def test_consume_pending_summary_waits_until_ready_timestamp(self) -> None:
        bridge = NarrationBridge(llm_provider=_FakeLLMProvider())
        with bridge._summary_lock:
            bridge._pending_summary = "Resumen listo"
            bridge._pending_summary_ready_at = 120.0

        with patch("pong.narration_bridge.time.monotonic", return_value=119.9):
            self.assertIsNone(bridge.consume_pending_summary())

        with patch("pong.narration_bridge.time.monotonic", return_value=120.0):
            self.assertEqual("Resumen listo", bridge.consume_pending_summary())

        self.assertIsNone(bridge.consume_pending_summary())

    def test_consume_pending_summary_without_delay_returns_immediately(self) -> None:
        bridge = NarrationBridge(llm_provider=_FakeLLMProvider())
        with bridge._summary_lock:
            bridge._pending_summary = "Resumen instantaneo"
            bridge._pending_summary_ready_at = None

        self.assertEqual("Resumen instantaneo", bridge.consume_pending_summary())
        self.assertIsNone(bridge.consume_pending_summary())


if __name__ == "__main__":
    unittest.main()
