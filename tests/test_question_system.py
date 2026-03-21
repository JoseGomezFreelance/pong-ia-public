"""Tests del sistema de preguntas (pong/question_system.py)."""
from __future__ import annotations

import time
import unittest

from pong.config.gameplay import PADDLE_HEIGHT
from pong.config.layout import GAME_AREA_HEIGHT
from pong.config.narrator import (
    ANSWER_THRESHOLD_PX,
    BULLET_TIME_DURATION_SECONDS,
    BULLET_TIME_SPEED_MULTIPLIER,
    QUESTION_FIRST_DELAY_SECONDS,
)
from pong.question_system import DialogueEntry, QuestionSystem


class TestDialogueEntry(unittest.TestCase):

    def test_fields(self) -> None:
        e = DialogueEntry("Pregunta?", "Si", 30.5)
        self.assertEqual(e.question, "Pregunta?")
        self.assertEqual(e.answer, "Si")
        self.assertAlmostEqual(e.elapsed_seconds, 30.5)


class TestQuestionSystemInit(unittest.TestCase):

    def test_defaults(self) -> None:
        t = time.monotonic()
        qs = QuestionSystem(t)
        self.assertEqual(qs.dialogue_history, [])
        self.assertFalse(qs.question_active)
        self.assertEqual(qs.current_question, "")
        self.assertEqual(qs.current_answer, "Duda")
        self.assertIsNone(qs.pending_question)
        self.assertFalse(qs.first_question_ready)

    def test_initial_question_selected(self) -> None:
        qs = QuestionSystem(time.monotonic())
        self.assertIsInstance(qs.selected_initial_question, str)
        self.assertGreater(len(qs.selected_initial_question), 0)

    def test_next_question_time(self) -> None:
        t = time.monotonic()
        qs = QuestionSystem(t)
        self.assertAlmostEqual(
            qs.next_question_time, t + QUESTION_FIRST_DELAY_SECONDS, delta=0.1,
        )


class TestBulletTime(unittest.TestCase):

    def test_not_bullet_time_when_inactive(self) -> None:
        qs = QuestionSystem(time.monotonic())
        self.assertFalse(qs.is_bullet_time())
        self.assertEqual(qs.get_speed_multiplier(), 1.0)

    def test_bullet_time_when_active(self) -> None:
        qs = QuestionSystem(time.monotonic())
        qs.start_question("Test?", time.monotonic())
        self.assertTrue(qs.is_bullet_time())
        self.assertEqual(qs.get_speed_multiplier(), BULLET_TIME_SPEED_MULTIPLIER)

    def test_bullet_time_expires(self) -> None:
        qs = QuestionSystem(time.monotonic())
        qs.start_question("Test?", time.monotonic())
        # Simulate enough time passing
        qs.update(BULLET_TIME_DURATION_SECONDS + 0.1, GAME_AREA_HEIGHT // 2)
        self.assertFalse(qs.is_bullet_time())
        self.assertFalse(qs.question_active)


class TestShouldAskQuestion(unittest.TestCase):

    def test_no_question_when_active(self) -> None:
        qs = QuestionSystem(time.monotonic())
        qs.question_active = True
        qs.pending_question = "Next?"
        self.assertFalse(qs.should_ask_question(time.monotonic() + 9999))

    def test_no_question_before_time(self) -> None:
        t = time.monotonic()
        qs = QuestionSystem(t)
        qs.pending_question = "Next?"
        # Before QUESTION_FIRST_DELAY_SECONDS
        self.assertFalse(qs.should_ask_question(t))

    def test_no_question_without_pending(self) -> None:
        t = time.monotonic()
        qs = QuestionSystem(t)
        # After delay, but no pending question
        self.assertFalse(
            qs.should_ask_question(t + QUESTION_FIRST_DELAY_SECONDS + 1)
        )

    def test_ask_when_ready(self) -> None:
        t = time.monotonic()
        qs = QuestionSystem(t)
        qs.pending_question = "Next?"
        self.assertTrue(
            qs.should_ask_question(t + QUESTION_FIRST_DELAY_SECONDS + 1)
        )


class TestStartQuestion(unittest.TestCase):

    def test_activates_question(self) -> None:
        qs = QuestionSystem(time.monotonic())
        qs.start_question("Crees que puedes ganar?", time.monotonic())
        self.assertTrue(qs.question_active)
        self.assertEqual(qs.current_question, "Crees que puedes ganar?")
        self.assertAlmostEqual(
            qs.bullet_time_remaining, BULLET_TIME_DURATION_SECONDS, delta=0.01,
        )
        self.assertEqual(qs.current_answer, "Duda")


class TestDetermineAnswer(unittest.TestCase):

    def test_si_at_top(self) -> None:
        qs = QuestionSystem(time.monotonic())
        answer = qs._determine_answer(0)
        self.assertEqual(answer, "Si")

    def test_si_within_threshold(self) -> None:
        qs = QuestionSystem(time.monotonic())
        answer = qs._determine_answer(ANSWER_THRESHOLD_PX)
        self.assertEqual(answer, "Si")

    def test_no_at_bottom(self) -> None:
        qs = QuestionSystem(time.monotonic())
        max_top = GAME_AREA_HEIGHT - PADDLE_HEIGHT
        answer = qs._determine_answer(max_top)
        self.assertEqual(answer, "No")

    def test_duda_in_middle(self) -> None:
        qs = QuestionSystem(time.monotonic())
        answer = qs._determine_answer(GAME_AREA_HEIGHT // 2)
        self.assertEqual(answer, "Duda")


class TestUpdate(unittest.TestCase):

    def test_updates_answer_from_paddle(self) -> None:
        qs = QuestionSystem(time.monotonic())
        qs.start_question("Test?", time.monotonic())
        qs.update(0.016, 0)  # paddle at top = Si
        self.assertEqual(qs.current_answer, "Si")

    def test_no_update_when_inactive(self) -> None:
        qs = QuestionSystem(time.monotonic())
        qs.update(0.016, 0)
        self.assertEqual(qs.current_answer, "Duda")  # unchanged

    def test_finalizes_when_time_expires(self) -> None:
        qs = QuestionSystem(time.monotonic())
        qs.start_question("Test?", time.monotonic())
        qs.update(BULLET_TIME_DURATION_SECONDS + 1, 0)
        self.assertFalse(qs.question_active)
        self.assertEqual(len(qs.dialogue_history), 1)
        self.assertEqual(qs.dialogue_history[0].answer, "Si")


class TestSetPendingQuestion(unittest.TestCase):

    def test_stores_question(self) -> None:
        qs = QuestionSystem(time.monotonic())
        qs.set_pending_question("Nueva pregunta?")
        self.assertEqual(qs.pending_question, "Nueva pregunta?")


class TestGetDialogueSummary(unittest.TestCase):

    def test_empty(self) -> None:
        qs = QuestionSystem(time.monotonic())
        self.assertEqual(qs.get_dialogue_summary(), "(sin dialogo previo)")

    def test_with_entries(self) -> None:
        qs = QuestionSystem(time.monotonic())
        qs.dialogue_history = [
            DialogueEntry("Pregunta uno?", "Si", 30),
            DialogueEntry("Pregunta dos?", "No", 60),
        ]
        summary = qs.get_dialogue_summary()
        self.assertIn("1. Pregunta: Pregunta uno?", summary)
        self.assertIn("Si", summary)
        self.assertIn("2. Pregunta: Pregunta dos?", summary)


class TestGetDialogueEssence(unittest.TestCase):

    def test_empty(self) -> None:
        qs = QuestionSystem(time.monotonic())
        self.assertEqual(qs.get_dialogue_essence(), "")

    def test_confiado(self) -> None:
        qs = QuestionSystem(time.monotonic())
        qs.dialogue_history = [
            DialogueEntry("Pregunta?", "Si", 30),
            DialogueEntry("Otra pregunta?", "Si", 60),
        ]
        essence = qs.get_dialogue_essence()
        self.assertIn("confiado", essence)
        self.assertIn("Ultima respuesta: Si", essence)

    def test_esceptico(self) -> None:
        qs = QuestionSystem(time.monotonic())
        qs.dialogue_history = [
            DialogueEntry("Pregunta?", "No", 30),
            DialogueEntry("Otra?", "No", 60),
        ]
        essence = qs.get_dialogue_essence()
        self.assertIn("esceptico", essence)

    def test_indeciso(self) -> None:
        qs = QuestionSystem(time.monotonic())
        qs.dialogue_history = [
            DialogueEntry("Pregunta?", "Si", 30),
            DialogueEntry("Otra?", "No", 60),
        ]
        essence = qs.get_dialogue_essence()
        self.assertIn("indeciso", essence)


class TestGetRecentDialogueContext(unittest.TestCase):

    def test_empty(self) -> None:
        qs = QuestionSystem(time.monotonic())
        self.assertEqual(qs.get_recent_dialogue_context(), [])

    def test_returns_structured_turns(self) -> None:
        qs = QuestionSystem(time.monotonic())
        qs.dialogue_history = [
            DialogueEntry("Q1?", "Si", 30),
            DialogueEntry("Q2?", "No", 60),
            DialogueEntry("Q3?", "Duda", 90),
        ]
        turns = qs.get_recent_dialogue_context(limit=2)
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0]["question"], "Q2?")
        self.assertEqual(turns[1]["answer"], "Duda")

    def test_limit_zero(self) -> None:
        qs = QuestionSystem(time.monotonic())
        qs.dialogue_history = [DialogueEntry("Q?", "Si", 10)]
        self.assertEqual(qs.get_recent_dialogue_context(limit=0), [])


if __name__ == "__main__":
    unittest.main()
