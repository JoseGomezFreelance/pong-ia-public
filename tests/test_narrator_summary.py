"""Tests del mixin de resumen de partido (pong/narrator_summary.py)."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from pong.narrator_summary import NarratorSummaryMixin


def _make_match_data(**overrides: Any) -> dict[str, Any]:
    """Datos minimos para generate_match_summary."""
    data: dict[str, Any] = {
        "winner": "el jugador",
        "final_sets": "1-0",
        "final_games_last_set": "2-1",
        "elapsed_text": "3:45",
        "total_points": 25,
        "player_points_total": 15,
        "computer_points_total": 10,
        "longest_streak_player": 3,
        "longest_streak_computer": 2,
        "dialogue_summary": "1. Pregunta: Test?\nRespuesta: Si",
        "narration_highlights": "Rally de 10 golpes.",
        "dialogue_essence": "jugador confiado",
        "dialogue_count": 3,
    }
    data.update(overrides)
    return data


def _make_narrator_stub(enabled: bool = True, response_text: str = "") -> Any:
    """Crea un stub con el mixin de resumen."""
    stub = SimpleNamespace(enabled=enabled)

    if enabled and response_text:
        stub._llm = MagicMock()
        stub._llm.chat_completion.return_value = {
            "choices": [{"message": {"content": response_text}}],
        }
    elif enabled:
        stub._llm = MagicMock()
        stub._llm.chat_completion.side_effect = Exception("LLM error")
    else:
        stub._llm = None

    # Bind mixin methods
    stub.enrich_image_prompt = NarratorSummaryMixin.enrich_image_prompt.__get__(stub)
    stub.reformulate_question = NarratorSummaryMixin.reformulate_question.__get__(stub)
    stub.generate_match_summary = NarratorSummaryMixin.generate_match_summary.__get__(stub)
    stub.generate_match_summary_streaming = NarratorSummaryMixin.generate_match_summary_streaming.__get__(stub)
    stub._fallback_match_summary = NarratorSummaryMixin._fallback_match_summary.__get__(stub)
    return stub


class TestFallbackSummary(unittest.TestCase):

    def test_includes_winner_and_time(self) -> None:
        stub = _make_narrator_stub(enabled=False)
        data = _make_match_data()
        summary = stub._fallback_match_summary(data)
        self.assertIn("el jugador", summary)
        self.assertIn("3:45", summary)

    def test_mentions_dialogue_count(self) -> None:
        stub = _make_narrator_stub(enabled=False)
        data = _make_match_data(dialogue_count=5)
        summary = stub._fallback_match_summary(data)
        self.assertIn("5 preguntas", summary)

    def test_no_dialogue(self) -> None:
        stub = _make_narrator_stub(enabled=False)
        data = _make_match_data(dialogue_count=0)
        summary = stub._fallback_match_summary(data)
        self.assertIn("No hubo dialogo", summary)


class TestEnrichImagePrompt(unittest.TestCase):

    def test_disabled_returns_base(self) -> None:
        stub = _make_narrator_stub(enabled=False)
        result = stub.enrich_image_prompt("base prompt", {})
        self.assertEqual(result, "base prompt")

    def test_enabled_appends_enrichment(self) -> None:
        stub = _make_narrator_stub(enabled=True, response_text="glowing neon grid")
        result = stub.enrich_image_prompt("base prompt", {"mood_tag": "tenso"})
        self.assertIn("base prompt", result)
        self.assertIn("glowing neon grid", result)

    def test_error_returns_base(self) -> None:
        stub = _make_narrator_stub(enabled=True)  # will raise Exception
        result = stub.enrich_image_prompt("base prompt", {})
        self.assertEqual(result, "base prompt")


class TestReformulateQuestion(unittest.TestCase):

    def test_disabled_returns_original(self) -> None:
        stub = _make_narrator_stub(enabled=False)
        result = stub.reformulate_question("Crees que puedes ganar?")
        self.assertEqual(result, "Crees que puedes ganar?")

    def test_valid_reformulation(self) -> None:
        stub = _make_narrator_stub(
            enabled=True,
            response_text="Piensas que tienes posibilidades de victoria en este encuentro?",
        )
        result = stub.reformulate_question("Crees que puedes ganar?")
        self.assertIn("?", result)
        self.assertNotEqual(result, "Crees que puedes ganar?")

    def test_too_short_returns_original(self) -> None:
        stub = _make_narrator_stub(enabled=True, response_text="Si?")
        result = stub.reformulate_question("Crees que puedes ganar?")
        self.assertEqual(result, "Crees que puedes ganar?")

    def test_error_returns_original(self) -> None:
        stub = _make_narrator_stub(enabled=True)  # raises
        result = stub.reformulate_question("Crees que puedes ganar?")
        self.assertEqual(result, "Crees que puedes ganar?")


class TestGenerateMatchSummary(unittest.TestCase):

    def test_disabled_returns_fallback(self) -> None:
        stub = _make_narrator_stub(enabled=False)
        data = _make_match_data()
        result = stub.generate_match_summary(data)
        self.assertIn("el jugador", result)
        self.assertIn("3:45", result)

    def test_valid_summary(self) -> None:
        long_text = (
            "Un partido intenso que mostro la determinacion del jugador. "
            "Desde el primer rally se noto la tension creciente. "
            "Las respuestas del jugador revelaron una actitud competitiva. "
            "La victoria fue merecida tras un dominio constante."
        )
        stub = _make_narrator_stub(enabled=True, response_text=long_text)
        data = _make_match_data()
        result = stub.generate_match_summary(data)
        self.assertIn("intenso", result)

    def test_too_short_response_returns_fallback(self) -> None:
        stub = _make_narrator_stub(enabled=True, response_text="Bien.")
        data = _make_match_data()
        result = stub.generate_match_summary(data)
        # Fallback because < 15 words
        self.assertIn("el jugador", result)

    def test_error_returns_fallback(self) -> None:
        stub = _make_narrator_stub(enabled=True)  # raises
        data = _make_match_data()
        result = stub.generate_match_summary(data)
        self.assertIn("Partido concluido", result)

    def test_strips_prefix(self) -> None:
        text = (
            "Resumen: Un partido intenso que mostro mucho sobre el jugador. "
            "La tension fue palpable desde el comienzo del encuentro. "
            "Las respuestas revelaron un caracter competitivo y decidido."
        )
        stub = _make_narrator_stub(enabled=True, response_text=text)
        data = _make_match_data()
        result = stub.generate_match_summary(data)
        self.assertFalse(result.startswith("Resumen:"))


class TestGenerateMatchSummaryStreaming(unittest.TestCase):

    def test_disabled_calls_progress_and_returns_fallback(self) -> None:
        stub = _make_narrator_stub(enabled=False)
        data = _make_match_data()
        progress_calls: list[tuple[int, int]] = []
        result = stub.generate_match_summary_streaming(
            data,
            progress_callback=lambda done, total: progress_calls.append((done, total)),
        )
        self.assertIn("el jugador", result)
        self.assertEqual(progress_calls, [(1, 1)])

    def test_streaming_collects_tokens(self) -> None:
        stub = _make_narrator_stub(enabled=True)
        # Override model to return a stream
        chunks = [
            {"choices": [{"delta": {"content": "Un "}}]},
            {"choices": [{"delta": {"content": "partido "}}]},
            {"choices": [{"delta": {"content": "memorable "}}]},
            {"choices": [{"delta": {"content": "que mostro la fuerza del jugador en cada intercambio y su capacidad de adaptarse. "}}]},
            {"choices": [{"delta": {"content": "Las respuestas revelaron un caracter firme. Victoria merecida sin duda alguna."}}]},
        ]
        stub._llm.chat_completion.side_effect = None
        stub._llm.chat_completion.return_value = iter(chunks)

        data = _make_match_data()
        progress_calls: list[tuple[int, int]] = []
        result = stub.generate_match_summary_streaming(
            data,
            progress_callback=lambda done, total: progress_calls.append((done, total)),
        )
        self.assertIn("partido", result)
        self.assertGreater(len(progress_calls), 0)


if __name__ == "__main__":
    unittest.main()
