"""Tests para pong/onnx_provider.py — proveedor ONNX para CPUs sin AVX2.

Verifica:
- Conformidad con LLMProviderProtocol
- Flatten de mensajes chat a texto plano
- Comportamiento sin modelo (disabled)
- Generacion con modelo mockeado
- Formato de respuesta compatible con el narrador
- Desactivacion de telemetria en Windows
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

# numpy es opcional (no esta en CI)
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

if not HAS_NUMPY:
    # Crear mock de numpy para que el modulo pong.onnx_provider importe
    _np_mock = MagicMock()
    _np_mock.int64 = "int64"
    _np_mock.float32 = "float32"
    sys.modules["numpy"] = _np_mock
    np = _np_mock

from pong.onnx_provider import (
    OnnxLLMProvider,
    _flatten_messages,
)
from pong.providers import LLMProviderProtocol


# ============================================================
# _flatten_messages
# ============================================================


class TestFlattenMessages(unittest.TestCase):

    def test_system_and_user(self) -> None:
        msgs = [
            {"role": "system", "content": "Eres un narrador."},
            {"role": "user", "content": "Describe la escena."},
        ]
        result = _flatten_messages(msgs)
        self.assertIn("Eres un narrador.", result)
        self.assertIn("Describe la escena.", result)

    def test_empty_messages(self) -> None:
        result = _flatten_messages([])
        self.assertEqual(result, "\n")

    def test_skips_empty_content(self) -> None:
        msgs = [
            {"role": "system", "content": ""},
            {"role": "user", "content": "Hola"},
        ]
        result = _flatten_messages(msgs)
        self.assertNotIn("\n\n", result.strip())
        self.assertIn("Hola", result)

    def test_all_roles_included(self) -> None:
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "usr"},
            {"role": "assistant", "content": "asst"},
        ]
        result = _flatten_messages(msgs)
        self.assertIn("sys", result)
        self.assertIn("usr", result)
        self.assertIn("asst", result)


# ============================================================
# OnnxLLMProvider — sin modelo
# ============================================================


class TestOnnxProviderNoModel(unittest.TestCase):

    def test_disabled_without_model(self) -> None:
        provider = OnnxLLMProvider()
        self.assertFalse(provider.enabled)

    def test_status_message_without_model(self) -> None:
        provider = OnnxLLMProvider()
        self.assertIn("no disponible", provider.status_message.lower())

    def test_has_required_attributes(self) -> None:
        """Verifica que tiene las propiedades del protocolo."""
        provider = OnnxLLMProvider()
        self.assertIsInstance(provider.enabled, bool)
        self.assertIsInstance(provider.status_message, str)
        self.assertTrue(callable(provider.chat_completion))


# ============================================================
# OnnxLLMProvider — con modelo mockeado
# ============================================================


def _create_mock_onnx_env(tmp_path: Path) -> Path:
    """Crea archivos minimos para que el provider cargue."""
    from pong.bpe_tokenizer import _bytes_to_unicode

    onnx_dir = tmp_path / "models" / "onnx"
    onnx_dir.mkdir(parents=True)

    # Crear model_quantized.onnx vacio (el mock de ort lo ignora)
    (onnx_dir / "model_quantized.onnx").write_bytes(b"fake_onnx")

    # Crear vocab.json y merges.txt minimos
    b2u = _bytes_to_unicode()
    vocab = {b2u[b]: b for b in range(256)}
    vocab["<|endoftext|>"] = 50256

    (onnx_dir / "vocab.json").write_text(
        json.dumps(vocab, ensure_ascii=False), encoding="utf-8"
    )
    (onnx_dir / "merges.txt").write_text("#version: 0.2\n", encoding="utf-8")

    return onnx_dir


@unittest.skipUnless(HAS_NUMPY, "numpy no disponible")
class TestOnnxProviderWithMock(unittest.TestCase):

    def _make_provider(self, tmp_path: Path) -> OnnxLLMProvider:
        """Crea un provider con ONNX Runtime mockeado."""
        onnx_dir = _create_mock_onnx_env(tmp_path)
        model_path = onnx_dir / "model_quantized.onnx"

        # Mock de InferenceSession que devuelve logits aleatorios
        mock_session = MagicMock()
        # Generar logits que favorezcan el EOS token para terminar rapido
        vocab_size = 50257
        logits = np.full((1, 1, vocab_size), -10.0, dtype=np.float32)
        logits[0, 0, 50256] = 10.0  # EOS token con probabilidad alta
        mock_session.run.return_value = [logits]

        mock_ort = MagicMock()
        mock_ort.InferenceSession.return_value = mock_session
        mock_ort.GraphOptimizationLevel.ORT_ENABLE_ALL = 99
        mock_ort.SessionOptions.return_value = MagicMock()

        with (
            patch("pong.onnx_provider._resolve_onnx_model_path", return_value=model_path),
            patch.dict("sys.modules", {"onnxruntime": mock_ort}),
        ):
            provider = OnnxLLMProvider()

        # Inyectar session mock para generate
        provider._session = mock_session
        return provider

    def test_enabled_with_mock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            provider = self._make_provider(Path(tmp))
            self.assertTrue(provider.enabled)

    def test_status_message_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            provider = self._make_provider(Path(tmp))
            self.assertIn("activo", provider.status_message.lower())
            self.assertIn("ONNX", provider.status_message)

    def test_chat_completion_format(self) -> None:
        """La respuesta tiene el formato esperado por el narrador."""
        with tempfile.TemporaryDirectory() as tmp:
            provider = self._make_provider(Path(tmp))
            result = provider.chat_completion(
                [{"role": "user", "content": "test"}],
                max_tokens=5,
            )
            self.assertIn("choices", result)
            self.assertIsInstance(result["choices"], list)
            self.assertIn("message", result["choices"][0])
            self.assertIn("content", result["choices"][0]["message"])
            self.assertIsInstance(result["choices"][0]["message"]["content"], str)

    def test_chat_completion_with_system_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            provider = self._make_provider(Path(tmp))
            result = provider.chat_completion(
                [
                    {"role": "system", "content": "Narrador deportivo"},
                    {"role": "user", "content": "Describe el punto"},
                ],
                max_tokens=3,
            )
            self.assertIn("choices", result)


# ============================================================
# Protocol compliance
# ============================================================


class TestOnnxProtocolCompliance(unittest.TestCase):

    def test_implements_protocol(self) -> None:
        """OnnxLLMProvider cumple LLMProviderProtocol."""
        provider = OnnxLLMProvider()
        self.assertIsInstance(provider, LLMProviderProtocol)


# ============================================================
# Reload
# ============================================================


class TestOnnxProviderReload(unittest.TestCase):

    def test_reload_when_disabled(self) -> None:
        provider = OnnxLLMProvider()
        self.assertFalse(provider.enabled)
        # Reload sin modelo no debe crashear
        provider.reload()
        self.assertFalse(provider.enabled)

    def test_reload_does_not_reload_when_enabled(self) -> None:
        """Si ya esta enabled, reload no hace nada."""
        provider = OnnxLLMProvider()
        provider._enabled = True
        provider._session = MagicMock()
        provider.reload()
        # Session no se reseteo
        self.assertIsNotNone(provider._session)


# ============================================================
# Telemetria
# ============================================================


class TestDisableTelemetry(unittest.TestCase):

    @patch("pong.onnx_provider.sys")
    def test_only_on_windows(self, mock_sys: MagicMock) -> None:
        from pong.onnx_provider import _disable_ort_telemetry

        mock_sys.platform = "darwin"
        # No debe intentar importar onnxruntime
        _disable_ort_telemetry()

    @patch("pong.onnx_provider.sys")
    def test_calls_disable_on_windows(self, mock_sys: MagicMock) -> None:
        from pong.onnx_provider import _disable_ort_telemetry

        mock_sys.platform = "win32"
        mock_ort = MagicMock()
        with patch.dict("sys.modules", {"onnxruntime": mock_ort}):
            _disable_ort_telemetry()
        mock_ort.disable_telemetry_events.assert_called_once()


if __name__ == "__main__":
    unittest.main()
