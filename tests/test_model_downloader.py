"""Tests para pong/model_downloader.py — comprobacion y descarga de modelos."""
from __future__ import annotations

import http.server
import io
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from pong.model_downloader import (
    ModelStatus,
    _is_diffusion_installed,
    _is_llm_installed,
    _resolve_models_dir,
    check_models_status,
    download_diffusion_models,
    download_llm_model,
    run_downloads,
)


# ============================================================
# ModelStatus dataclass
# ============================================================


class TestModelStatus(unittest.TestCase):
    """Tests para el dataclass ModelStatus."""

    def test_defaults(self) -> None:
        s = ModelStatus(name="Test", model_type="llm")
        self.assertFalse(s.installed)
        self.assertEqual(s.progress, 0.0)
        self.assertEqual(s.status_text, "Pendiente")
        self.assertEqual(s.error, "")

    def test_is_downloading_true(self) -> None:
        s = ModelStatus(name="X", model_type="llm", status_text="Descargando 50/100 MB")
        self.assertTrue(s.is_downloading)

    def test_is_downloading_false(self) -> None:
        s = ModelStatus(name="X", model_type="llm", status_text="Pendiente")
        self.assertFalse(s.is_downloading)

    def test_is_done_installed(self) -> None:
        s = ModelStatus(name="X", model_type="llm", installed=True)
        self.assertTrue(s.is_done)

    def test_is_done_error(self) -> None:
        s = ModelStatus(name="X", model_type="llm", error="fail")
        self.assertTrue(s.is_done)

    def test_is_done_pending(self) -> None:
        s = ModelStatus(name="X", model_type="llm")
        self.assertFalse(s.is_done)


# ============================================================
# check_models_status
# ============================================================


class TestCheckModelsStatus(unittest.TestCase):
    """Tests para check_models_status."""

    @patch("pong.model_downloader._is_diffusion_installed", return_value=False)
    @patch("pong.model_downloader._is_llm_installed", return_value=False)
    def test_returns_two_statuses(self, _mock_llm: MagicMock, _mock_diff: MagicMock) -> None:
        statuses = check_models_status()
        self.assertEqual(len(statuses), 2)
        self.assertEqual(statuses[0].model_type, "llm")
        self.assertEqual(statuses[1].model_type, "diffusion")

    @patch("pong.model_downloader._is_diffusion_installed", return_value=False)
    @patch("pong.model_downloader._is_llm_installed", return_value=True)
    def test_llm_installed(self, _mock_llm: MagicMock, _mock_diff: MagicMock) -> None:
        statuses = check_models_status()
        self.assertTrue(statuses[0].installed)
        self.assertEqual(statuses[0].status_text, "Instalado")
        self.assertFalse(statuses[1].installed)
        self.assertEqual(statuses[1].status_text, "Pendiente")

    @patch("pong.model_downloader._is_diffusion_installed", return_value=True)
    @patch("pong.model_downloader._is_llm_installed", return_value=False)
    def test_diffusion_installed(self, _mock_llm: MagicMock, _mock_diff: MagicMock) -> None:
        statuses = check_models_status()
        self.assertFalse(statuses[0].installed)
        self.assertTrue(statuses[1].installed)


# ============================================================
# _is_llm_installed
# ============================================================


class TestIsLLMInstalled(unittest.TestCase):
    """Tests para _is_llm_installed."""

    @patch("pong.providers.resolve_model_path")
    def test_not_exists(self, mock_resolve: MagicMock) -> None:
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = False
        mock_resolve.return_value = mock_path
        self.assertFalse(_is_llm_installed("model.gguf"))

    @patch("pong.providers.resolve_model_path")
    def test_too_small(self, mock_resolve: MagicMock) -> None:
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_stat = MagicMock()
        mock_stat.st_size = 1000  # demasiado pequeno
        mock_path.stat.return_value = mock_stat
        mock_resolve.return_value = mock_path
        self.assertFalse(_is_llm_installed("model.gguf"))

    @patch("pong.providers.resolve_model_path")
    def test_large_enough(self, mock_resolve: MagicMock) -> None:
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_stat = MagicMock()
        mock_stat.st_size = 200_000_000
        mock_path.stat.return_value = mock_stat
        mock_resolve.return_value = mock_path
        self.assertTrue(_is_llm_installed("model.gguf"))

    @patch("pong.providers.resolve_model_path")
    def test_oserror_returns_false(self, mock_resolve: MagicMock) -> None:
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.stat.side_effect = OSError("nope")
        mock_resolve.return_value = mock_path
        self.assertFalse(_is_llm_installed("model.gguf"))


# ============================================================
# _is_diffusion_installed
# ============================================================


class TestIsDiffusionInstalled(unittest.TestCase):
    """Tests para _is_diffusion_installed."""

    @patch("pong.image_generator.is_model_cached", return_value=True)
    def test_cached(self, _mock: MagicMock) -> None:
        self.assertTrue(_is_diffusion_installed())

    @patch("pong.image_generator.is_model_cached", return_value=False)
    def test_not_cached(self, _mock: MagicMock) -> None:
        self.assertFalse(_is_diffusion_installed())

    @patch("pong.image_generator.is_model_cached", side_effect=ImportError)
    def test_import_error(self, _mock: MagicMock) -> None:
        self.assertFalse(_is_diffusion_installed())


# ============================================================
# _resolve_models_dir
# ============================================================


class TestResolveModelsDir(unittest.TestCase):
    """Tests para _resolve_models_dir."""

    def test_returns_path(self) -> None:
        result = _resolve_models_dir()
        self.assertIsInstance(result, Path)
        self.assertEqual(result.name, "models")


# ============================================================
# download_llm_model
# ============================================================


class TestDownloadLLMModel(unittest.TestCase):
    """Tests para download_llm_model."""

    @patch("pong.model_downloader._resolve_models_dir")
    @patch("pong.model_downloader.urllib.request.urlopen")
    def test_successful_download(
        self, mock_urlopen: MagicMock, mock_dir: MagicMock,
    ) -> None:
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_dir.return_value = Path(tmpdir)

            # Simular respuesta HTTP con datos
            data = b"x" * 1024
            mock_response = MagicMock()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_response.headers = {"Content-Length": str(len(data))}
            mock_response.read = MagicMock(side_effect=[data, b""])
            mock_urlopen.return_value = mock_response

            status = ModelStatus(name="Test LLM", model_type="llm")
            lock = threading.Lock()
            result = download_llm_model(status, lock)

            self.assertTrue(result)
            self.assertTrue(status.installed)
            self.assertEqual(status.progress, 1.0)
            self.assertEqual(status.status_text, "Instalado")

    @patch("pong.model_downloader._resolve_models_dir")
    @patch("pong.model_downloader.urllib.request.urlopen")
    def test_download_without_content_length(
        self, mock_urlopen: MagicMock, mock_dir: MagicMock,
    ) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_dir.return_value = Path(tmpdir)

            data = b"x" * 512
            mock_response = MagicMock()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_response.headers = {"Content-Length": "0"}
            mock_response.read = MagicMock(side_effect=[data, b""])
            mock_urlopen.return_value = mock_response

            status = ModelStatus(name="Test LLM", model_type="llm")
            lock = threading.Lock()
            result = download_llm_model(status, lock)

            self.assertTrue(result)
            self.assertTrue(status.installed)

    @patch("pong.model_downloader._resolve_models_dir")
    @patch(
        "pong.model_downloader.urllib.request.urlopen",
        side_effect=OSError("Network down"),
    )
    def test_network_error(
        self, _mock_urlopen: MagicMock, mock_dir: MagicMock,
    ) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_dir.return_value = Path(tmpdir)

            status = ModelStatus(name="Test LLM", model_type="llm")
            lock = threading.Lock()
            result = download_llm_model(status, lock)

            self.assertFalse(result)
            self.assertFalse(status.installed)
            self.assertIn("Network down", status.error)
            self.assertIn("Error", status.status_text)


# ============================================================
# download_diffusion_models
# ============================================================


class TestDownloadDiffusionModels(unittest.TestCase):
    """Tests para download_diffusion_models."""

    @patch("pong.image_generator.ensure_models_downloaded", return_value=True)
    def test_successful(self, _mock: MagicMock) -> None:
        status = ModelStatus(name="Diffusion", model_type="diffusion")
        lock = threading.Lock()
        result = download_diffusion_models(status, lock)

        self.assertTrue(result)
        self.assertTrue(status.installed)
        self.assertEqual(status.progress, 1.0)

    @patch("pong.image_generator.ensure_models_downloaded", return_value=False)
    def test_returns_false(self, _mock: MagicMock) -> None:
        status = ModelStatus(name="Diffusion", model_type="diffusion")
        lock = threading.Lock()
        result = download_diffusion_models(status, lock)

        self.assertFalse(result)
        self.assertFalse(status.installed)
        self.assertIn("Error", status.status_text)

    @patch(
        "pong.image_generator.ensure_models_downloaded",
        side_effect=RuntimeError("boom"),
    )
    def test_exception(self, _mock: MagicMock) -> None:
        status = ModelStatus(name="Diffusion", model_type="diffusion")
        lock = threading.Lock()
        result = download_diffusion_models(status, lock)

        self.assertFalse(result)
        self.assertIn("boom", status.error)


# ============================================================
# run_downloads
# ============================================================


class TestRunDownloads(unittest.TestCase):
    """Tests para run_downloads."""

    @patch("pong.model_downloader.download_diffusion_models")
    @patch("pong.model_downloader.download_llm_model")
    def test_skips_installed(
        self, mock_llm: MagicMock, mock_diff: MagicMock,
    ) -> None:
        statuses = [
            ModelStatus(name="LLM", model_type="llm", installed=True),
            ModelStatus(name="Diff", model_type="diffusion", installed=True),
        ]
        lock = threading.Lock()
        run_downloads(statuses, lock)

        mock_llm.assert_not_called()
        mock_diff.assert_not_called()

    @patch("pong.model_downloader.download_diffusion_models")
    @patch("pong.model_downloader.download_llm_model")
    def test_downloads_pending(
        self, mock_llm: MagicMock, mock_diff: MagicMock,
    ) -> None:
        statuses = [
            ModelStatus(name="LLM", model_type="llm", installed=False),
            ModelStatus(name="Diff", model_type="diffusion", installed=False),
        ]
        lock = threading.Lock()
        run_downloads(statuses, lock)

        mock_llm.assert_called_once()
        mock_diff.assert_called_once()

    @patch("pong.model_downloader.download_llm_model")
    def test_on_complete_callback(self, mock_llm: MagicMock) -> None:
        statuses = [
            ModelStatus(name="LLM", model_type="llm", installed=True),
        ]
        lock = threading.Lock()
        callback = MagicMock()
        run_downloads(statuses, lock, on_complete=callback)

        callback.assert_called_once()

    @patch("pong.model_downloader.download_diffusion_models")
    @patch("pong.model_downloader.download_llm_model")
    def test_mixed_installed_and_pending(
        self, mock_llm: MagicMock, mock_diff: MagicMock,
    ) -> None:
        statuses = [
            ModelStatus(name="LLM", model_type="llm", installed=True),
            ModelStatus(name="Diff", model_type="diffusion", installed=False),
        ]
        lock = threading.Lock()
        run_downloads(statuses, lock)

        mock_llm.assert_not_called()
        mock_diff.assert_called_once()
