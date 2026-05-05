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
    _split_base,
    check_models_status,
    delete_llm_model,
    download_diffusion_models,
    download_llm_for_tier,
    download_llm_model,
    find_unused_llm_models,
    is_llm_tier_installed,
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

    _FAKE_LLM_CONFIG = MagicMock(
        filename="test-model.gguf",
        download_url="https://example.com/test-model.gguf",
    )

    @patch("pong.config.models.load_models_config")
    @patch("pong.model_downloader._resolve_models_dir")
    @patch("pong.model_downloader.urllib.request.urlopen")
    def test_successful_download(
        self, mock_urlopen: MagicMock, mock_dir: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        import tempfile
        import os

        mock_config.return_value = (self._FAKE_LLM_CONFIG, MagicMock())

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

    @patch("pong.config.models.load_models_config")
    @patch("pong.model_downloader._resolve_models_dir")
    @patch("pong.model_downloader.urllib.request.urlopen")
    def test_download_without_content_length(
        self, mock_urlopen: MagicMock, mock_dir: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        import tempfile

        mock_config.return_value = (self._FAKE_LLM_CONFIG, MagicMock())

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

    @patch("pong.config.models.load_models_config")
    @patch("pong.model_downloader._resolve_models_dir")
    @patch(
        "pong.model_downloader.urllib.request.urlopen",
        side_effect=OSError("Network down"),
    )
    def test_network_error(
        self, _mock_urlopen: MagicMock, mock_dir: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        import tempfile

        mock_config.return_value = (self._FAKE_LLM_CONFIG, MagicMock())

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


# ============================================================
# _split_base
# ============================================================


class TestSplitBase(unittest.TestCase):
    """Tests para _split_base."""

    def test_single_file(self) -> None:
        self.assertEqual(
            _split_base("qwen2.5-3b-instruct-q4_k_m.gguf"),
            "qwen2.5-3b-instruct-q4_k_m",
        )

    def test_split_part(self) -> None:
        self.assertEqual(
            _split_base("qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf"),
            "qwen2.5-7b-instruct-q4_k_m",
        )

    def test_split_last_part(self) -> None:
        self.assertEqual(
            _split_base("qwen2.5-14b-instruct-q4_k_m-00003-of-00003.gguf"),
            "qwen2.5-14b-instruct-q4_k_m",
        )


# ============================================================
# find_unused_llm_models
# ============================================================


class TestFindUnusedLLMModels(unittest.TestCase):
    """Tests para find_unused_llm_models."""

    @patch("pong.model_downloader._resolve_models_dir")
    def test_finds_unused_single_file(self, mock_dir: MagicMock) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_dir.return_value = Path(tmpdir)
            # Active model
            active = Path(tmpdir) / "qwen2.5-3b-instruct-q4_k_m.gguf"
            active.write_bytes(b"x" * 200_000_000)
            # Unused model
            unused = Path(tmpdir) / "qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf"
            unused.write_bytes(b"x" * 200_000_000)

            result = find_unused_llm_models("qwen2.5-3b-instruct-q4_k_m.gguf")
            self.assertEqual(len(result), 1)
            self.assertIn("qwen2.5-7b", result[0][0])

    @patch("pong.model_downloader._resolve_models_dir")
    def test_no_unused(self, mock_dir: MagicMock) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_dir.return_value = Path(tmpdir)
            active = Path(tmpdir) / "qwen2.5-3b-instruct-q4_k_m.gguf"
            active.write_bytes(b"x" * 200_000_000)

            result = find_unused_llm_models("qwen2.5-3b-instruct-q4_k_m.gguf")
            self.assertEqual(result, [])

    @patch("pong.model_downloader._resolve_models_dir")
    def test_groups_split_files(self, mock_dir: MagicMock) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_dir.return_value = Path(tmpdir)
            # Active single file
            active = Path(tmpdir) / "qwen2.5-3b-instruct-q4_k_m.gguf"
            active.write_bytes(b"x" * 200_000_000)
            # Unused split model (2 parts)
            p1 = Path(tmpdir) / "qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf"
            p2 = Path(tmpdir) / "qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf"
            p1.write_bytes(b"x" * 200_000_000)
            p2.write_bytes(b"x" * 200_000_000)

            result = find_unused_llm_models("qwen2.5-3b-instruct-q4_k_m.gguf")
            self.assertEqual(len(result), 1)
            # Total size should be ~0.4 GB
            self.assertGreater(result[0][1], 0.3)

    @patch("pong.model_downloader._resolve_models_dir")
    def test_empty_dir(self, mock_dir: MagicMock) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_dir.return_value = Path(tmpdir)
            result = find_unused_llm_models("anything.gguf")
            self.assertEqual(result, [])


# ============================================================
# delete_llm_model
# ============================================================


class TestDeleteLLMModel(unittest.TestCase):
    """Tests para delete_llm_model."""

    @patch("pong.model_downloader._resolve_models_dir")
    def test_deletes_single_file(self, mock_dir: MagicMock) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_dir.return_value = Path(tmpdir)
            f = Path(tmpdir) / "qwen2.5-3b-instruct-q4_k_m.gguf"
            f.write_bytes(b"x" * 100)

            result = delete_llm_model("qwen2.5-3b-instruct-q4_k_m.gguf")
            self.assertTrue(result)
            self.assertFalse(f.exists())

    @patch("pong.model_downloader._resolve_models_dir")
    def test_deletes_split_group(self, mock_dir: MagicMock) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_dir.return_value = Path(tmpdir)
            p1 = Path(tmpdir) / "model-00001-of-00002.gguf"
            p2 = Path(tmpdir) / "model-00002-of-00002.gguf"
            p1.write_bytes(b"x" * 100)
            p2.write_bytes(b"x" * 100)

            result = delete_llm_model("model-00001-of-00002.gguf")
            self.assertTrue(result)
            self.assertFalse(p1.exists())
            self.assertFalse(p2.exists())

    @patch("pong.model_downloader._resolve_models_dir")
    def test_nonexistent_returns_false(self, mock_dir: MagicMock) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_dir.return_value = Path(tmpdir)
            result = delete_llm_model("nonexistent.gguf")
            self.assertFalse(result)


# ============================================================
# is_llm_tier_installed
# ============================================================


class TestIsLLMTierInstalled(unittest.TestCase):
    """Tests para is_llm_tier_installed."""

    @patch("pong.model_downloader._is_llm_installed", return_value=True)
    def test_installed(self, _mock: MagicMock) -> None:
        self.assertTrue(is_llm_tier_installed("model.gguf"))

    @patch("pong.model_downloader._is_llm_installed", return_value=False)
    def test_not_installed(self, _mock: MagicMock) -> None:
        self.assertFalse(is_llm_tier_installed("model.gguf"))


# ============================================================
# download_llm_for_tier
# ============================================================


class TestDownloadLLMForTier(unittest.TestCase):
    """Tests para download_llm_for_tier."""

    @patch("pong.model_downloader._resolve_models_dir")
    @patch("pong.model_downloader.urllib.request.urlopen")
    def test_single_file_download(
        self, mock_urlopen: MagicMock, mock_dir: MagicMock,
    ) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_dir.return_value = Path(tmpdir)

            data = b"x" * 512
            mock_response = MagicMock()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_response.headers = {"Content-Length": str(len(data))}
            mock_response.read = MagicMock(side_effect=[data, b""])
            mock_urlopen.return_value = mock_response

            status = ModelStatus(name="Test", model_type="llm")
            lock = threading.Lock()
            result = download_llm_for_tier(
                repo_id="Qwen/test",
                gguf_pattern="test*.gguf",
                filename="test.gguf",
                download_url="https://example.com/test.gguf",
                split=False,
                status=status,
                lock=lock,
            )
            self.assertTrue(result)
            self.assertTrue(status.installed)

    @patch("pong.model_downloader._download_hf_split", return_value=True)
    def test_split_delegates_to_hf(self, mock_hf: MagicMock) -> None:
        status = ModelStatus(name="Test", model_type="llm")
        lock = threading.Lock()
        result = download_llm_for_tier(
            repo_id="Qwen/test",
            gguf_pattern="test*.gguf",
            filename="test-00001-of-00002.gguf",
            download_url="",
            split=True,
            status=status,
            lock=lock,
        )
        self.assertTrue(result)
        mock_hf.assert_called_once()
