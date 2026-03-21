"""Pruebas del sistema de generacion de preguntas del narrador."""
from __future__ import annotations

import time
from typing import Any
from unittest.mock import patch
import unittest

from pong.narrator import LocalNarrator
from pong.question_system import DialogueEntry, QuestionSystem


class _NullLLMProvider:
    """Provider LLM nulo para tests (no carga modelo)."""

    enabled = False
    status_message = "Test: no model"

    def chat_completion(self, messages: list[dict[str, str]], **_kwargs: Any) -> dict[str, Any]:
        return {"choices": [{"message": {"content": ""}}]}


class _FakeQuestionModel:
    """Provider LLM fake para controlar salidas y capturar prompts."""

    enabled = True
    status_message = "Test: fake model"

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls = 0
        self.last_messages: list[dict[str, str]] | None = None

    def chat_completion(self, messages: list[dict[str, str]], **_kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        self.last_messages = messages
        index = min(self.calls - 1, len(self.responses) - 1)
        content = self.responses[index]
        return {"choices": [{"message": {"content": content}}]}


def _base_game_state(**overrides: Any) -> dict[str, Any]:
    """Estado minimo comun para probar generacion de preguntas."""
    state: dict[str, Any] = {
        "scoreboard": "Sets 0-0, Juegos 1-1, Puntos 2-2",
        "last_play": "El ordenador devolvio la pelota",
        "elapsed_seconds": 92,
        "rally_hits": 5,
        "question_count": 1,
        "player_score": 2,
        "computer_score": 2,
        "player_games": 1,
        "computer_games": 1,
        "player_point_streak": 0,
        "computer_point_streak": 1,
        "dialogue_turns": [],
    }
    state.update(overrides)
    return state


class NarratorQuestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.narrator = LocalNarrator(_NullLLMProvider())

    def test_generate_question_retries_when_first_attempt_repeats(self) -> None:
        old_question = "Crees que este punto puede definir el juego?"
        fake_model = _FakeQuestionModel(
            [
                old_question,
                "Te conviene variar la devolucion para cortar el ritmo rival?",
            ]
        )
        self.narrator.enabled = True
        self.narrator._llm = fake_model

        game_state = _base_game_state(
            question_count=2,
            dialogue_turns=[
                {"question": old_question, "answer": "Si", "elapsed_seconds": 35}
            ],
        )

        generated, _emotion = self.narrator.generate_question("(sin dialogo previo)", game_state)

        self.assertEqual(
            generated,
            "Te conviene variar la devolucion para cortar el ritmo rival?",
        )
        self.assertEqual(fake_model.calls, 2)

    def test_generate_question_uses_structured_dialogue_in_prompt(self) -> None:
        fake_model = _FakeQuestionModel(
            ["Crees que debes presionar mas con tu siguiente devolucion?"]
        )
        self.narrator.enabled = True
        self.narrator._llm = fake_model

        game_state = _base_game_state(
            question_count=5,
            dialogue_turns=[
                {
                    "question": "Pregunta estructurada clave?",
                    "answer": "No",
                    "elapsed_seconds": 48,
                }
            ],
        )
        summary = "1. Pregunta: Pregunta vieja?\n   Respuesta del jugador: Si"

        generated, _emotion = self.narrator.generate_question(summary, game_state)
        assert fake_model.last_messages is not None
        user_prompt = fake_model.last_messages[1]["content"]

        self.assertTrue(generated.endswith("?"))
        self.assertIn("acaba de responder: No", user_prompt)
        self.assertIn("Pregunta estructurada clave?", user_prompt)
        self.assertIn("TEMA OBLIGATORIO", user_prompt)

    def test_contextual_fallback_avoids_repeating_recent_questions(self) -> None:
        self.narrator.enabled = False
        game_state = _base_game_state(
            question_count=4,
            dialogue_turns=[
                {
                    "question": (
                        "Ves necesario ajustar tu posicion para leer mejor el "
                        "siguiente saque?"
                    ),
                    "answer": "Si",
                    "elapsed_seconds": 10,
                },
                {
                    "question": (
                        "Crees que conviene arriesgar mas con el primer golpe "
                        "de este rally?"
                    ),
                    "answer": "No",
                    "elapsed_seconds": 40,
                },
                {
                    "question": (
                        "Sientes que tu plan actual te da ventaja en este tramo "
                        "del partido?"
                    ),
                    "answer": "Duda",
                    "elapsed_seconds": 70,
                },
            ],
            player_score=2,
            computer_score=2,
        )

        with patch("pong.narrator.random.shuffle", lambda seq: None):
            generated, _emotion = self.narrator.generate_question("(sin dialogo previo)", game_state)

        self.assertEqual(
            generated,
            "Con el marcador tan parejo, crees que el proximo punto marcara el ritmo?",
        )


class DialogueEssenceTests(unittest.TestCase):
    """Pruebas para QuestionSystem.get_dialogue_essence()."""

    def _make_system(self) -> QuestionSystem:
        return QuestionSystem(time.monotonic())

    def test_empty_history_returns_empty(self) -> None:
        qs = self._make_system()
        self.assertEqual(qs.get_dialogue_essence(), "")

    def test_mostly_yes_is_confiado(self) -> None:
        qs = self._make_system()
        qs.dialogue_history = [
            DialogueEntry("Estas contento con tu juego?", "Si", 30),
            DialogueEntry("Crees que dominas el partido?", "Si", 60),
            DialogueEntry("Cambias de estrategia?", "No", 90),
        ]
        essence = qs.get_dialogue_essence()
        self.assertIn("confiado", essence)
        self.assertIn("No", essence)  # ultima respuesta

    def test_mostly_no_is_esceptico(self) -> None:
        qs = self._make_system()
        qs.dialogue_history = [
            DialogueEntry("Te sientes bien?", "No", 30),
            DialogueEntry("Dominas la situacion?", "No", 60),
        ]
        essence = qs.get_dialogue_essence()
        self.assertIn("esceptico", essence)

    def test_mixed_is_indeciso(self) -> None:
        qs = self._make_system()
        qs.dialogue_history = [
            DialogueEntry("Pregunta uno larga?", "Si", 30),
            DialogueEntry("Pregunta dos larga?", "No", 60),
        ]
        essence = qs.get_dialogue_essence()
        self.assertIn("indeciso", essence)

    def test_includes_topic_from_last_question(self) -> None:
        qs = self._make_system()
        qs.dialogue_history = [
            DialogueEntry("Crees que la estrategia defensiva funciona?", "Si", 30),
        ]
        essence = qs.get_dialogue_essence()
        self.assertIn("estrategia", essence)


class ConversationArcTests(unittest.TestCase):
    """Pruebas para _conversation_arc_hint()."""

    def setUp(self) -> None:
        self.narrator = LocalNarrator(_NullLLMProvider())

    def test_arc_1_returns_from_bucket_1(self) -> None:
        hint = self.narrator._conversation_arc_hint(1)
        self.assertIn(hint, self.narrator._CONVERSATION_ARCS[1])

    def test_arc_2_returns_from_bucket_2(self) -> None:
        hint = self.narrator._conversation_arc_hint(2)
        self.assertIn(hint, self.narrator._CONVERSATION_ARCS[2])

    def test_arc_3_returns_from_bucket_3(self) -> None:
        hint = self.narrator._conversation_arc_hint(3)
        self.assertIn(hint, self.narrator._CONVERSATION_ARCS[3])

    def test_arc_late_for_high_counts(self) -> None:
        for count in [4, 5, 10]:
            hint = self.narrator._conversation_arc_hint(count)
            self.assertIn(hint, self.narrator._CONVERSATION_ARCS["late"])


class StructuralBanTests(unittest.TestCase):
    """Pruebas para bans estructurales en _is_question_too_similar()."""

    def setUp(self) -> None:
        self.narrator = LocalNarrator(_NullLLMProvider())

    def test_structural_ban_blocks_repeated_phrase(self) -> None:
        old = ["Crees que el punto ganado cambia las cosas?"]
        candidate = "Ese punto ganado te da mas confianza?"
        self.assertTrue(self.narrator._is_question_too_similar(candidate, old))

    def test_no_structural_ban_for_different_phrases(self) -> None:
        old = ["Te sientes presionado por el marcador?"]
        candidate = "Cambiarias tu estrategia ahora mismo?"
        self.assertFalse(self.narrator._is_question_too_similar(candidate, old))


class CommentateDialogueTests(unittest.TestCase):
    """Pruebas para que commentate() use dialogue_essence."""

    def setUp(self) -> None:
        self.narrator = LocalNarrator(_NullLLMProvider())

    def test_commentate_includes_dialogue_in_prompt(self) -> None:
        fake_model = _FakeQuestionModel(
            ["El jugador confiado mantiene el ritmo alto!"]
        )
        self.narrator.enabled = True
        self.narrator._llm = fake_model

        game_state: dict[str, Any] = {
            "event_label": "juego en curso",
            "last_play": "El jugador devolvio la pelota",
            "scoreboard": "Sets 0-0, Juegos 0-0, Puntos 1-1",
            "rally_hits": 4,
            "elapsed_seconds": 45,
            "dialogue_essence": "Jugador confiado. Tema reciente: estrategia. Ultima respuesta: Si.",
        }

        self.narrator.commentate(game_state)
        assert fake_model.last_messages is not None
        user_prompt = fake_model.last_messages[1]["content"]
        system_prompt = fake_model.last_messages[0]["content"]

        self.assertIn("Dialogo con jugador:", user_prompt)
        self.assertIn("confiado", user_prompt)
        self.assertIn("dialogo con el jugador", system_prompt)

    def test_commentate_no_dialogue_when_empty(self) -> None:
        fake_model = _FakeQuestionModel(
            ["Rally intenso de 3 toques!"]
        )
        self.narrator.enabled = True
        self.narrator._llm = fake_model

        game_state: dict[str, Any] = {
            "event_label": "juego en curso",
            "last_play": "El jugador devolvio la pelota",
            "scoreboard": "Sets 0-0, Juegos 0-0, Puntos 0-0",
            "rally_hits": 3,
            "elapsed_seconds": 10,
        }

        self.narrator.commentate(game_state)
        assert fake_model.last_messages is not None
        user_prompt = fake_model.last_messages[1]["content"]
        system_prompt = fake_model.last_messages[0]["content"]

        self.assertNotIn("Dialogo con jugador:", user_prompt)
        self.assertNotIn("dialogo con el jugador", system_prompt)


if __name__ == "__main__":
    unittest.main()
