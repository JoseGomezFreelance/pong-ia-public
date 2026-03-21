"""Tests de funciones helper puras de narrator_questions.py."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any


def _make_questions_stub() -> Any:
    """Crea un stub con el mixin de preguntas."""
    from pong.narrator_questions import NarratorQuestionsMixin

    stub = SimpleNamespace(enabled=False, _llm=None)

    # Copy class-level attributes (sets, lists, dicts)
    stub._QUESTION_STOPWORDS = NarratorQuestionsMixin._QUESTION_STOPWORDS
    stub._STRUCTURAL_BANS = NarratorQuestionsMixin._STRUCTURAL_BANS
    stub._CONVERSATION_ARCS = NarratorQuestionsMixin._CONVERSATION_ARCS

    # Bind all helper methods
    methods = [
        "_normalize_answer", "_answer_profile", "_conversation_arc_hint",
        "_reaction_hint", "_format_recent_dialogue_for_prompt",
        "_question_keywords", "_question_tokens", "_normalize_question_text",
        "_is_question_too_similar", "_polish_question", "_fallback_question",
        "_parse_dialogue_summary", "_extract_recent_dialogue",
    ]
    for name in methods:
        method = getattr(NarratorQuestionsMixin, name)
        setattr(stub, name, method.__get__(stub))

    # _truncate_words (provided by LocalNarrator)
    def _truncate_words(text: str, max_words: int) -> str:
        words = text.split()
        return " ".join(words[:max_words])
    stub._truncate_words = _truncate_words

    return stub


class TestNormalizeAnswer(unittest.TestCase):

    def setUp(self) -> None:
        self.stub = _make_questions_stub()

    def test_si(self) -> None:
        self.assertEqual(self.stub._normalize_answer("Si"), "Si")
        self.assertEqual(self.stub._normalize_answer("si"), "Si")
        self.assertEqual(self.stub._normalize_answer("sí"), "Si")

    def test_no(self) -> None:
        self.assertEqual(self.stub._normalize_answer("No"), "No")
        self.assertEqual(self.stub._normalize_answer("no"), "No")
        self.assertEqual(self.stub._normalize_answer("nah"), "No")

    def test_duda(self) -> None:
        self.assertEqual(self.stub._normalize_answer("Duda"), "Duda")
        self.assertEqual(self.stub._normalize_answer(""), "Duda")
        self.assertEqual(self.stub._normalize_answer(None), "Duda")

    def test_unexpected_values(self) -> None:
        self.assertEqual(self.stub._normalize_answer("quizas"), "Duda")
        self.assertEqual(self.stub._normalize_answer(42), "Duda")


class TestAnswerProfile(unittest.TestCase):

    def setUp(self) -> None:
        self.stub = _make_questions_stub()

    def test_empty(self) -> None:
        result = self.stub._answer_profile([])
        self.assertEqual(result, "sin respuestas previas")

    def test_mixed_answers(self) -> None:
        turns = [
            {"question": "Q1", "answer": "Si"},
            {"question": "Q2", "answer": "No"},
            {"question": "Q3", "answer": "Duda"},
        ]
        result = self.stub._answer_profile(turns)
        self.assertIn("Si=1/3", result)
        self.assertIn("No=1/3", result)
        self.assertIn("Duda=1/3", result)
        self.assertIn("ultima=Duda", result)


class TestConversationArcHint(unittest.TestCase):

    def setUp(self) -> None:
        self.stub = _make_questions_stub()

    def test_first_question(self) -> None:
        hint = self.stub._conversation_arc_hint(1)
        self.assertIsInstance(hint, str)
        self.assertGreater(len(hint), 0)

    def test_late_question(self) -> None:
        hint = self.stub._conversation_arc_hint(10)
        self.assertIsInstance(hint, str)


class TestReactionHint(unittest.TestCase):

    def setUp(self) -> None:
        self.stub = _make_questions_stub()

    def test_si(self) -> None:
        hint = self.stub._reaction_hint("Si")
        self.assertIn("profundiza", hint)

    def test_no(self) -> None:
        hint = self.stub._reaction_hint("No")
        self.assertIn("hipotesis", hint)

    def test_duda(self) -> None:
        hint = self.stub._reaction_hint("Duda")
        self.assertIn("claridad", hint)


class TestFormatRecentDialogue(unittest.TestCase):

    def setUp(self) -> None:
        self.stub = _make_questions_stub()

    def test_empty(self) -> None:
        result = self.stub._format_recent_dialogue_for_prompt([])
        self.assertEqual(result, "(sin dialogo previo)")

    def test_formats_turns(self) -> None:
        turns = [
            {"question": "Te gusta?", "answer": "Si", "elapsed_seconds": 30},
        ]
        result = self.stub._format_recent_dialogue_for_prompt(turns)
        self.assertIn("1)", result)
        self.assertIn("[30s]", result)
        self.assertIn("Te gusta?", result)


class TestQuestionKeywords(unittest.TestCase):

    def setUp(self) -> None:
        self.stub = _make_questions_stub()

    def test_empty(self) -> None:
        self.assertEqual(self.stub._question_keywords([]), [])

    def test_extracts_relevant_words(self) -> None:
        questions = [
            "Crees que la estrategia defensiva funciona mejor?",
            "La estrategia ofensiva podria cambiar el resultado?",
        ]
        keywords = self.stub._question_keywords(questions)
        self.assertIsInstance(keywords, list)
        # "estrategia" appears twice, should be in keywords
        self.assertIn("estrategia", keywords)

    def test_filters_stopwords(self) -> None:
        questions = ["Este punto del partido es importante?"]
        keywords = self.stub._question_keywords(questions)
        # "este", "punto", "partido" are stopwords
        for stopword in ["este", "punto", "partido"]:
            self.assertNotIn(stopword, keywords)


class TestQuestionTokens(unittest.TestCase):

    def setUp(self) -> None:
        self.stub = _make_questions_stub()

    def test_tokenizes(self) -> None:
        tokens = self.stub._question_tokens("La estrategia defensiva funciona?")
        self.assertIn("estrategia", tokens)
        self.assertIn("defensiva", tokens)
        self.assertIn("funciona", tokens)

    def test_excludes_short_tokens(self) -> None:
        tokens = self.stub._question_tokens("Si o no es bueno?")
        for t in tokens:
            self.assertGreaterEqual(len(t), 4)


class TestIsQuestionTooSimilar(unittest.TestCase):

    def setUp(self) -> None:
        self.stub = _make_questions_stub()

    def test_empty_recent_not_similar(self) -> None:
        self.assertFalse(self.stub._is_question_too_similar("Nueva pregunta?", []))

    def test_exact_duplicate(self) -> None:
        self.assertTrue(
            self.stub._is_question_too_similar(
                "Crees que puedes ganar?",
                ["Crees que puedes ganar?"],
            )
        )

    def test_very_different_not_similar(self) -> None:
        self.assertFalse(
            self.stub._is_question_too_similar(
                "Te gusta la musica clasica mientras juegas?",
                ["Crees que el marcador refleja tu nivel?"],
            )
        )


class TestPolishQuestion(unittest.TestCase):

    def setUp(self) -> None:
        self.stub = _make_questions_stub()

    def test_adds_question_mark(self) -> None:
        result = self.stub._polish_question(
            "Crees que necesitas cambiar tu estrategia para ganar este juego",
            "fallback?",
        )
        self.assertTrue(result.endswith("?"))

    def test_strips_prefix(self) -> None:
        result = self.stub._polish_question(
            "Pregunta: Crees que necesitas cambiar tu estrategia para ganar?",
            "fallback?",
        )
        self.assertFalse(result.lower().startswith("pregunta"))

    def test_too_short_returns_fallback(self) -> None:
        result = self.stub._polish_question("Hola?", "fallback question here for real?")
        # "Hola?" is < 8 words, so fallback
        self.assertIn("fallback", result)

    def test_empty_returns_fallback(self) -> None:
        result = self.stub._polish_question("", "fallback?")
        self.assertEqual(result, "fallback?")

    def test_truncates_long_question(self) -> None:
        long_q = " ".join(["palabra"] * 25) + "?"
        result = self.stub._polish_question(long_q, "fallback?")
        words = result.replace("?", "").split()
        self.assertLessEqual(len(words), 20)


class TestFallbackQuestion(unittest.TestCase):

    def setUp(self) -> None:
        self.stub = _make_questions_stub()

    def test_returns_valid_question(self) -> None:
        game_state: dict[str, Any] = {
            "player_score": 2, "computer_score": 1,
            "player_point_streak": 0, "computer_point_streak": 0,
            "rally_hits": 3,
        }
        result = self.stub._fallback_question(game_state, [])
        self.assertTrue(result.endswith("?"))
        self.assertGreater(len(result.split()), 5)

    def test_avoids_recent_questions(self) -> None:
        game_state: dict[str, Any] = {
            "player_score": 0, "computer_score": 0,
            "player_point_streak": 0, "computer_point_streak": 0,
            "rally_hits": 0,
        }
        # Even with many recent questions, should always return something
        recent = [
            {"question": f"Pregunta generica numero {i} sobre el partido actual?", "answer": "Si"}
            for i in range(10)
        ]
        result = self.stub._fallback_question(game_state, recent)
        self.assertTrue(result.endswith("?"))


class TestParseDialogueSummary(unittest.TestCase):

    def setUp(self) -> None:
        self.stub = _make_questions_stub()

    def test_empty(self) -> None:
        self.assertEqual(self.stub._parse_dialogue_summary(""), [])
        self.assertEqual(
            self.stub._parse_dialogue_summary("(sin dialogo previo)"), []
        )

    def test_parses_formatted_dialogue(self) -> None:
        text = (
            "1. Pregunta: Te gusta el pong?\n"
            "Respuesta del jugador: Si\n"
            "2. Pregunta: Crees que puedes ganar?\n"
            "Respuesta del jugador: No\n"
        )
        turns = self.stub._parse_dialogue_summary(text)
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0]["question"], "Te gusta el pong?")
        self.assertEqual(turns[0]["answer"], "Si")
        self.assertEqual(turns[1]["answer"], "No")


if __name__ == "__main__":
    unittest.main()
