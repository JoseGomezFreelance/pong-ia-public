"""Tests de la jerarquía de excepciones personalizadas (pong/exceptions.py)."""
from __future__ import annotations

import pickle
import unittest

from pong.exceptions import (
    AchievementDefinitionError,
    ImageGenerationError,
    ImageGenError,
    LLMInferenceError,
    ModelDownloadError,
    ModelLoadError,
    NarratorError,
    PipelineLoadError,
    PongError,
)


class HierarchyTests(unittest.TestCase):
    """Verifica que la jerarquía de herencia es correcta."""

    def test_narrator_errors_inherit_from_pong_error(self) -> None:
        self.assertTrue(issubclass(NarratorError, PongError))
        self.assertTrue(issubclass(ModelLoadError, NarratorError))
        self.assertTrue(issubclass(LLMInferenceError, NarratorError))

    def test_imagegen_errors_inherit_from_pong_error(self) -> None:
        self.assertTrue(issubclass(ImageGenError, PongError))
        self.assertTrue(issubclass(PipelineLoadError, ImageGenError))
        self.assertTrue(issubclass(ImageGenerationError, ImageGenError))
        self.assertTrue(issubclass(ModelDownloadError, ImageGenError))

    def test_achievement_error_inherits_from_pong_error(self) -> None:
        self.assertTrue(issubclass(AchievementDefinitionError, PongError))

    def test_all_inherit_from_exception(self) -> None:
        for cls in (
            PongError, NarratorError, ModelLoadError, LLMInferenceError,
            ImageGenError, PipelineLoadError, ImageGenerationError,
            ModelDownloadError, AchievementDefinitionError,
        ):
            with self.subTest(cls=cls.__name__):
                self.assertTrue(issubclass(cls, Exception))

    def test_catch_pong_error_catches_all_custom(self) -> None:
        """except PongError atrapa cualquier excepción personalizada."""
        for cls in (
            ModelLoadError, LLMInferenceError, PipelineLoadError,
            ImageGenerationError, ModelDownloadError, AchievementDefinitionError,
        ):
            with self.subTest(cls=cls.__name__):
                with self.assertRaises(PongError):
                    raise cls("test")


class PickleTests(unittest.TestCase):
    """Las excepciones deben ser serializables (importante para multiprocessing)."""

    def test_all_exceptions_are_picklable(self) -> None:
        for cls in (
            PongError, NarratorError, ModelLoadError, LLMInferenceError,
            ImageGenError, PipelineLoadError, ImageGenerationError,
            ModelDownloadError, AchievementDefinitionError,
        ):
            with self.subTest(cls=cls.__name__):
                original = cls(f"test message for {cls.__name__}")
                restored = pickle.loads(pickle.dumps(original))
                self.assertEqual(str(restored), str(original))
                self.assertIsInstance(restored, cls)


class StrTests(unittest.TestCase):
    """Verifica que __str__ preserva el mensaje."""

    def test_str_preserves_message(self) -> None:
        err = LLMInferenceError("narracion LLM: timeout")
        self.assertEqual(str(err), "narracion LLM: timeout")

    def test_cause_chaining(self) -> None:
        original = RuntimeError("connection refused")
        err = LLMInferenceError("narracion LLM: connection refused")
        err.__cause__ = original
        self.assertIs(err.__cause__, original)


if __name__ == "__main__":
    unittest.main()
