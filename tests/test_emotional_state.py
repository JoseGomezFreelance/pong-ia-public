"""Pruebas del sistema de estado emocional de la IA."""
from __future__ import annotations

import json
import unittest

from typing import Any
from unittest.mock import MagicMock

from pong.emotional_state import (
    VALID_MOOD_TAGS,
    EmotionalState,
    _clamp,
    parse_emotion_from_llm,
    parse_question_from_llm,
)


class ClampTests(unittest.TestCase):
    def test_clamp_within_range(self) -> None:
        self.assertEqual(_clamp(0.5), 0.5)

    def test_clamp_below_min(self) -> None:
        self.assertEqual(_clamp(-0.3), 0.0)

    def test_clamp_above_max(self) -> None:
        self.assertEqual(_clamp(1.5), 1.0)

    def test_clamp_exact_boundaries(self) -> None:
        self.assertEqual(_clamp(0.0), 0.0)
        self.assertEqual(_clamp(1.0), 1.0)


class EmotionalStateTests(unittest.TestCase):
    def test_default_values(self) -> None:
        state = EmotionalState()
        self.assertAlmostEqual(state.aggressiveness, 0.5)
        self.assertAlmostEqual(state.stability, 0.8)
        self.assertAlmostEqual(state.motivation, 0.7)
        self.assertEqual(state.mood_tag, "neutral")

    def test_lerp_toward_halfway(self) -> None:
        state = EmotionalState(aggressiveness=0.0, stability=0.0, motivation=0.0)
        target = EmotionalState(aggressiveness=1.0, stability=1.0, motivation=1.0,
                                mood_tag="tenso")
        state.lerp_toward(target, 0.5)
        self.assertAlmostEqual(state.aggressiveness, 0.5)
        self.assertAlmostEqual(state.stability, 0.5)
        self.assertAlmostEqual(state.motivation, 0.5)
        self.assertEqual(state.mood_tag, "tenso")

    def test_lerp_toward_zero_factor_no_change(self) -> None:
        state = EmotionalState(aggressiveness=0.3, stability=0.4, motivation=0.5)
        target = EmotionalState(aggressiveness=1.0, stability=1.0, motivation=1.0)
        state.lerp_toward(target, 0.0)
        self.assertAlmostEqual(state.aggressiveness, 0.3)
        self.assertAlmostEqual(state.stability, 0.4)
        self.assertAlmostEqual(state.motivation, 0.5)

    def test_lerp_toward_full_factor(self) -> None:
        state = EmotionalState(aggressiveness=0.0, stability=0.0, motivation=0.0)
        target = EmotionalState(aggressiveness=0.8, stability=0.6, motivation=0.4)
        state.lerp_toward(target, 1.0)
        self.assertAlmostEqual(state.aggressiveness, 0.8)
        self.assertAlmostEqual(state.stability, 0.6)
        self.assertAlmostEqual(state.motivation, 0.4)

    def test_copy_is_independent(self) -> None:
        original = EmotionalState(aggressiveness=0.9, mood_tag="furioso")
        copied = original.copy()
        copied.aggressiveness = 0.1
        copied.mood_tag = "relajado"
        self.assertAlmostEqual(original.aggressiveness, 0.9)
        self.assertEqual(original.mood_tag, "furioso")


class ParseEmotionFromLLMTests(unittest.TestCase):
    def test_valid_json(self) -> None:
        raw = json.dumps({
            "pregunta": "Te sientes presionado?",
            "emocion": {
                "agresividad": 0.8,
                "estabilidad": 0.3,
                "motivacion": 0.9,
                "humor": "tenso",
            },
        })
        emotion = parse_emotion_from_llm(raw)
        self.assertIsNotNone(emotion)
        assert emotion is not None
        self.assertAlmostEqual(emotion.aggressiveness, 0.8)
        self.assertAlmostEqual(emotion.stability, 0.3)
        self.assertAlmostEqual(emotion.motivation, 0.9)
        self.assertEqual(emotion.mood_tag, "tenso")

    def test_values_are_clamped(self) -> None:
        raw = json.dumps({
            "pregunta": "Pregunta?",
            "emocion": {
                "agresividad": 1.5,
                "estabilidad": -0.3,
                "motivacion": 2.0,
                "humor": "erratico",
            },
        })
        emotion = parse_emotion_from_llm(raw)
        self.assertIsNotNone(emotion)
        assert emotion is not None
        self.assertAlmostEqual(emotion.aggressiveness, 1.0)
        self.assertAlmostEqual(emotion.stability, 0.0)
        self.assertAlmostEqual(emotion.motivation, 1.0)

    def test_missing_emocion_returns_none(self) -> None:
        raw = json.dumps({"pregunta": "Algo?"})
        self.assertIsNone(parse_emotion_from_llm(raw))

    def test_invalid_json_returns_none(self) -> None:
        self.assertIsNone(parse_emotion_from_llm("No es JSON"))

    def test_empty_string_returns_none(self) -> None:
        self.assertIsNone(parse_emotion_from_llm(""))

    def test_json_wrapped_in_text(self) -> None:
        raw = (
            'Aqui va la respuesta: '
            '{"pregunta": "Vas a ganar?", "emocion": '
            '{"agresividad": 0.6, "estabilidad": 0.7, '
            '"motivacion": 0.5, "humor": "neutral"}}'
            ' y eso es todo.'
        )
        emotion = parse_emotion_from_llm(raw)
        self.assertIsNotNone(emotion)
        assert emotion is not None
        self.assertAlmostEqual(emotion.aggressiveness, 0.6)

    def test_non_numeric_values_return_none(self) -> None:
        raw = json.dumps({
            "pregunta": "Algo?",
            "emocion": {
                "agresividad": "alta",
                "estabilidad": 0.5,
                "motivacion": 0.7,
                "humor": "tenso",
            },
        })
        self.assertIsNone(parse_emotion_from_llm(raw))

    def test_unknown_mood_tag_falls_back_to_neutral(self) -> None:
        raw = json.dumps({
            "pregunta": "Algo?",
            "emocion": {
                "agresividad": 0.5,
                "estabilidad": 0.5,
                "motivacion": 0.5,
                "humor": "confuso",
            },
        })
        emotion = parse_emotion_from_llm(raw)
        self.assertIsNotNone(emotion)
        assert emotion is not None
        self.assertEqual(emotion.mood_tag, "neutral")

    def test_valid_mood_tags_constant(self) -> None:
        expected = {"neutral", "relajado", "tenso", "irritado", "furioso",
                    "deprimido", "aburrido", "euforico", "erratico"}
        self.assertEqual(VALID_MOOD_TAGS, expected)

    def test_defaults_for_missing_fields(self) -> None:
        raw = json.dumps({
            "pregunta": "Algo?",
            "emocion": {"humor": "deprimido"},
        })
        emotion = parse_emotion_from_llm(raw)
        self.assertIsNotNone(emotion)
        assert emotion is not None
        self.assertAlmostEqual(emotion.aggressiveness, 0.5)
        self.assertAlmostEqual(emotion.stability, 0.8)
        self.assertAlmostEqual(emotion.motivation, 0.7)
        self.assertEqual(emotion.mood_tag, "deprimido")


class ParseQuestionFromLLMTests(unittest.TestCase):
    def test_valid_json(self) -> None:
        raw = json.dumps({
            "pregunta": "Te sientes presionado?",
            "emocion": {"agresividad": 0.5},
        })
        question = parse_question_from_llm(raw)
        self.assertEqual(question, "Te sientes presionado?")

    def test_missing_pregunta_returns_none(self) -> None:
        raw = json.dumps({"emocion": {"agresividad": 0.5}})
        self.assertIsNone(parse_question_from_llm(raw))

    def test_empty_pregunta_returns_none(self) -> None:
        raw = json.dumps({"pregunta": "  ", "emocion": {}})
        self.assertIsNone(parse_question_from_llm(raw))

    def test_not_json_returns_none(self) -> None:
        self.assertIsNone(parse_question_from_llm("Pregunta normal?"))

    def test_strips_whitespace(self) -> None:
        raw = json.dumps({"pregunta": "  Hola mundo?  ", "emocion": {}})
        self.assertEqual(parse_question_from_llm(raw), "Hola mundo?")


class GenerateQuestionWithEmotionTests(unittest.TestCase):
    """Prueba que generate_question devuelve (pregunta, emocion)."""

    def setUp(self) -> None:
        from pong.narrator import LocalNarrator

        class _NullLLM:
            enabled = False
            status_message = "Test: no model"
            def chat_completion(self, messages: list[dict[str, str]], **kw: Any) -> dict[str, Any]:
                return {"choices": [{"message": {"content": ""}}]}

        self.narrator = LocalNarrator(_NullLLM())

    def test_llm_returns_valid_json_with_emotion(self) -> None:
        json_response = json.dumps({
            "pregunta": "Sientes que el ritmo del partido esta cambiando?",
            "emocion": {
                "agresividad": 0.7,
                "estabilidad": 0.5,
                "motivacion": 0.8,
                "humor": "tenso",
            },
        })
        fake_model = MagicMock()
        fake_model.chat_completion.return_value = {
            "choices": [{"message": {"content": json_response}}]
        }
        self.narrator.enabled = True
        self.narrator._llm = fake_model

        game_state: dict[str, Any] = {
            "scoreboard": "Sets 0-0, Juegos 0-0, Puntos 1-1",
            "elapsed_seconds": 60,
            "rally_hits": 3,
            "question_count": 2,
            "dialogue_turns": [
                {"question": "Primera pregunta?", "answer": "Si", "elapsed_seconds": 35}
            ],
        }
        question, emotion = self.narrator.generate_question("", game_state)

        self.assertTrue(question.endswith("?"))
        self.assertIn("ritmo", question)
        self.assertIsNotNone(emotion)
        assert emotion is not None
        self.assertAlmostEqual(emotion.aggressiveness, 0.7)
        self.assertEqual(emotion.mood_tag, "tenso")

    def test_llm_returns_plain_text_emotion_is_none(self) -> None:
        fake_model = MagicMock()
        fake_model.chat_completion.return_value = {
            "choices": [{"message": {"content":
                "Crees que puedes remontar este partido con tu estrategia actual?"
            }}]
        }
        self.narrator.enabled = True
        self.narrator._llm = fake_model

        game_state: dict[str, Any] = {
            "scoreboard": "Sets 0-0, Juegos 0-0, Puntos 1-1",
            "elapsed_seconds": 60,
            "rally_hits": 3,
            "question_count": 2,
            "dialogue_turns": [],
        }
        question, emotion = self.narrator.generate_question("", game_state)

        self.assertTrue(question.endswith("?"))
        self.assertIsNone(emotion)

    def test_disabled_narrator_returns_none_emotion(self) -> None:
        self.narrator.enabled = False
        game_state: dict[str, Any] = {
            "scoreboard": "Sets 0-0, Juegos 0-0, Puntos 0-0",
            "elapsed_seconds": 30,
            "rally_hits": 0,
            "question_count": 1,
            "dialogue_turns": [],
            "player_score": 0,
            "computer_score": 0,
            "player_point_streak": 0,
            "computer_point_streak": 0,
        }
        question, emotion = self.narrator.generate_question("", game_state)

        self.assertTrue(question.endswith("?"))
        self.assertIsNone(emotion)


if __name__ == "__main__":
    unittest.main()
