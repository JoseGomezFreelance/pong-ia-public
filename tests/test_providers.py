"""Tests para pong/providers.py — protocols, resolve_model_path y discovery."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from pong.providers import (
    ImageGenProviderProtocol,
    LLMProviderProtocol,
    LocalLLMProvider,
    _load_entry_point,
    load_imagegen_provider,
    load_llm_provider,
    resolve_model_path,
)


# ============================================================
# Protocol conformance
# ============================================================


class _DummyLLM:
    """Minimal implementation that satisfies LLMProviderProtocol."""

    @property
    def enabled(self) -> bool:
        return False

    @property
    def status_message(self) -> str:
        return "dummy"

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 64,
        temperature: float = 0.85,
        top_p: float = 0.92,
        repeat_penalty: float = 1.18,
        frequency_penalty: float = 0.0,
        stream: bool = False,
    ) -> Any:
        return {"choices": [{"message": {"content": ""}}]}


class _DummyImageGen:
    """Minimal implementation that satisfies ImageGenProviderProtocol."""

    @property
    def state(self) -> str:
        return "idle"

    @property
    def is_ready(self) -> bool:
        return False

    def set_perf(self, perf: Any) -> None:
        pass

    def set_log_fn(self, fn: Any) -> None:
        pass

    def activate(self) -> None:
        pass

    def request(self, prompt: str, negative_prompt: str = "") -> None:
        pass

    def consume(self) -> Any | None:
        return None

    def shutdown(self) -> None:
        pass


class TestProtocolConformance(unittest.TestCase):

    def test_llm_protocol(self) -> None:
        self.assertIsInstance(_DummyLLM(), LLMProviderProtocol)

    def test_imagegen_protocol(self) -> None:
        self.assertIsInstance(_DummyImageGen(), ImageGenProviderProtocol)

    def test_arbitrary_object_does_not_match_llm(self) -> None:
        self.assertNotIsInstance(object(), LLMProviderProtocol)


# ============================================================
# resolve_model_path
# ============================================================


class TestResolveModelPath(unittest.TestCase):

    def test_returns_path_object(self) -> None:
        result = resolve_model_path(Path("models/nonexistent.gguf"))
        self.assertIsInstance(result, Path)

    def test_env_var_takes_priority(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".gguf") as f:
            with patch.dict(os.environ, {"PONG_IA_MODEL_PATH": f.name}):
                result = resolve_model_path(Path("models/other.gguf"))
                self.assertEqual(str(result), f.name)

    def test_existing_file_found(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".gguf", dir=".") as f:
            rel = Path(f.name).name
            result = resolve_model_path(Path(rel))
            self.assertTrue(result.exists())

    def test_nonexistent_returns_first_candidate(self) -> None:
        result = resolve_model_path(Path("models/does_not_exist_xyz.gguf"))
        self.assertIn("does_not_exist_xyz", str(result))


# ============================================================
# LocalLLMProvider
# ============================================================


class TestLocalLLMProvider(unittest.TestCase):

    def test_no_model_file_disabled(self) -> None:
        from pong.config.models import LLMModelConfig

        config = LLMModelConfig(filename="nonexistent_model_xyz.gguf")
        provider = LocalLLMProvider(config)
        self.assertFalse(provider.enabled)
        self.assertIn("no disponible", provider.status_message.lower())

    def test_default_config(self) -> None:
        provider = LocalLLMProvider()
        self.assertIsInstance(provider, LocalLLMProvider)
        self.assertIsInstance(provider.status_message, str)

    @patch("pong.providers.resolve_model_path")
    def test_loads_model_when_file_exists(self, mock_resolve: MagicMock) -> None:
        fake_path = MagicMock()
        fake_path.exists.return_value = True
        mock_resolve.return_value = fake_path

        fake_llama_mod = MagicMock()
        with patch.dict("sys.modules", {"llama_cpp": fake_llama_mod}):
            provider = LocalLLMProvider()
        self.assertTrue(provider.enabled)
        self.assertIn("activo", provider.status_message.lower())

    @patch("pong.providers.resolve_model_path")
    def test_missing_llama_cpp(self, mock_resolve: MagicMock) -> None:
        fake_path = MagicMock()
        fake_path.exists.return_value = True
        mock_resolve.return_value = fake_path

        # Ensure llama_cpp is not importable
        import sys
        saved = sys.modules.pop("llama_cpp", None)
        try:
            with patch.dict("sys.modules", {"llama_cpp": None}):
                # importlib.import_module will raise ModuleNotFoundError
                # when sys.modules[name] is None
                provider = LocalLLMProvider()
            self.assertFalse(provider.enabled)
            self.assertIn("llama_cpp", provider.status_message)
        finally:
            if saved is not None:
                sys.modules["llama_cpp"] = saved

    @patch("pong.providers.resolve_model_path")
    def test_generic_load_error(self, mock_resolve: MagicMock) -> None:
        fake_path = MagicMock()
        fake_path.exists.return_value = True
        mock_resolve.return_value = fake_path

        fake_llama_mod = MagicMock()
        fake_llama_mod.Llama.side_effect = RuntimeError("boom")
        with patch.dict("sys.modules", {"llama_cpp": fake_llama_mod}):
            provider = LocalLLMProvider()
        self.assertFalse(provider.enabled)
        self.assertIn("boom", provider.status_message)

    @patch("pong.providers.resolve_model_path")
    def test_chat_completion_delegates(self, mock_resolve: MagicMock) -> None:
        fake_path = MagicMock()
        fake_path.exists.return_value = True
        mock_resolve.return_value = fake_path

        fake_model = MagicMock()
        fake_model.create_chat_completion.return_value = {
            "choices": [{"message": {"content": "hola"}}]
        }
        fake_llama_mod = MagicMock()
        fake_llama_mod.Llama.return_value = fake_model
        with patch.dict("sys.modules", {"llama_cpp": fake_llama_mod}):
            provider = LocalLLMProvider()
        result = provider.chat_completion([{"role": "user", "content": "test"}])
        self.assertEqual(result["choices"][0]["message"]["content"], "hola")
        fake_model.create_chat_completion.assert_called_once()


# ============================================================
# _load_entry_point
# ============================================================


class TestLoadEntryPoint(unittest.TestCase):

    def test_nonexistent_group_returns_none(self) -> None:
        result = _load_entry_point("nonexistent_group_xyz", "nonexistent_name")
        self.assertIsNone(result)

    @patch("pong.providers.importlib.metadata.entry_points")
    def test_finds_entry_point(self, mock_eps: MagicMock) -> None:
        fake_ep = MagicMock()
        fake_ep.name = "test_provider"
        fake_ep.load.return_value = _DummyLLM

        mock_eps.return_value = {"pong_ia.llm": [fake_ep]}

        result = _load_entry_point("pong_ia.llm", "test_provider")
        self.assertIs(result, _DummyLLM)

    @patch("pong.providers.importlib.metadata.entry_points", side_effect=Exception("fail"))
    def test_exception_returns_none(self, mock_eps: MagicMock) -> None:
        result = _load_entry_point("pong_ia.llm", "test")
        self.assertIsNone(result)


# ============================================================
# load_llm_provider / load_imagegen_provider
# ============================================================


class TestLoadLLMProvider(unittest.TestCase):

    def test_default_returns_local_provider(self) -> None:
        provider = load_llm_provider()
        self.assertIsInstance(provider, LocalLLMProvider)

    @patch.dict(os.environ, {"PONG_IA_LLM_PROVIDER": "nonexistent_plugin_xyz"})
    def test_unknown_plugin_falls_back_to_local(self) -> None:
        provider = load_llm_provider()
        self.assertIsInstance(provider, LocalLLMProvider)

    @patch("pong.providers._load_entry_point")
    @patch.dict(os.environ, {"PONG_IA_LLM_PROVIDER": "custom"})
    def test_custom_plugin_loaded(self, mock_load_ep: MagicMock) -> None:
        dummy_instance = _DummyLLM()
        mock_load_ep.return_value = lambda config: dummy_instance
        provider = load_llm_provider()
        self.assertIs(provider, dummy_instance)


class TestLoadImagegenProvider(unittest.TestCase):

    def test_default_returns_image_generator(self) -> None:
        from pong.image_generator import ImageGenerator

        provider = load_imagegen_provider()
        self.assertIsInstance(provider, ImageGenerator)

    @patch.dict(os.environ, {"PONG_IA_IMAGEGEN_PROVIDER": "nonexistent_xyz"})
    def test_unknown_plugin_falls_back(self) -> None:
        from pong.image_generator import ImageGenerator

        provider = load_imagegen_provider()
        self.assertIsInstance(provider, ImageGenerator)

    @patch("pong.providers._load_entry_point")
    @patch.dict(os.environ, {"PONG_IA_IMAGEGEN_PROVIDER": "custom"})
    def test_custom_plugin_loaded(self, mock_load_ep: MagicMock) -> None:
        dummy_instance = _DummyImageGen()
        mock_load_ep.return_value = lambda config: dummy_instance
        provider = load_imagegen_provider()
        self.assertIs(provider, dummy_instance)


if __name__ == "__main__":
    unittest.main()
