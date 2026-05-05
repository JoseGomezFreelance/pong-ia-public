"""Tests para el tier -1 ONNX — fallback para CPUs sin AVX2.

Verifica:
- Definicion correcta de TIER_ONNX_FALLBACK
- Que tier -1 NO aparece en LLM_TIERS (es oculto)
- is_onnx_tier_viable con distintos perfiles de hardware
- is_onnx_runtime_available con mocks
- tier_to_llm_config funciona con tier -1
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from pong.config.llm_tiers import (
    LLM_TIERS,
    TIER_0_FALLBACK,
    TIER_ONNX_FALLBACK,
    is_onnx_runtime_available,
    is_onnx_tier_viable,
    tier_to_llm_config,
)
from pong.system_info import SystemInfo


def _make_info(
    ram: float = 8.0,
    disk: float = 50.0,
    has_avx2: bool = False,
) -> SystemInfo:
    """Helper para crear SystemInfo de prueba."""
    return SystemInfo(
        total_ram_gb=ram,
        available_ram_gb=ram * 0.6,
        unified_memory=False,
        gpu_name="Test CPU",
        gpu_type="cpu",
        gpu_vram_gb=0.0,
        disk_free_gb=disk,
        cpu_name="Test CPU",
        cpu_cores=2,
        has_avx=True,
        has_avx2=has_avx2,
    )


# ============================================================
# Definicion de TIER_ONNX_FALLBACK
# ============================================================


class TestOnnxTierDefinition(unittest.TestCase):

    def test_level_is_minus_one(self) -> None:
        self.assertEqual(TIER_ONNX_FALLBACK.level, -1)

    def test_is_single_file(self) -> None:
        self.assertFalse(TIER_ONNX_FALLBACK.split)

    def test_has_download_url(self) -> None:
        self.assertIn("huggingface.co", TIER_ONNX_FALLBACK.download_url)
        self.assertIn("distilgpt2", TIER_ONNX_FALLBACK.download_url)

    def test_smaller_than_tier0(self) -> None:
        self.assertLess(
            TIER_ONNX_FALLBACK.model_size_bytes,
            TIER_0_FALLBACK.model_size_bytes,
        )

    def test_lower_ram_than_tier0(self) -> None:
        self.assertLess(
            TIER_ONNX_FALLBACK.ram_recommended_gb,
            TIER_0_FALLBACK.ram_recommended_gb,
        )

    def test_display_name_contains_onnx(self) -> None:
        self.assertIn("ONNX", TIER_ONNX_FALLBACK.display_name)

    def test_display_name_contains_distilgpt2(self) -> None:
        self.assertIn("DistilGPT-2", TIER_ONNX_FALLBACK.display_name)

    def test_no_gguf_pattern(self) -> None:
        self.assertEqual(TIER_ONNX_FALLBACK.gguf_pattern, "")

    def test_repo_id(self) -> None:
        self.assertEqual(TIER_ONNX_FALLBACK.repo_id, "Xenova/distilgpt2")


# ============================================================
# Tier -1 NO esta en LLM_TIERS
# ============================================================


class TestOnnxTierHidden(unittest.TestCase):

    def test_not_in_llm_tiers(self) -> None:
        levels = [t.level for t in LLM_TIERS]
        self.assertNotIn(-1, levels)

    def test_llm_tiers_still_has_five(self) -> None:
        self.assertEqual(len(LLM_TIERS), 5)


# ============================================================
# is_onnx_tier_viable
# ============================================================


class TestIsOnnxTierViable(unittest.TestCase):

    def test_viable_no_avx2_enough_ram(self) -> None:
        info = _make_info(ram=4.0, has_avx2=False)
        self.assertTrue(is_onnx_tier_viable(info))

    def test_not_viable_with_avx2(self) -> None:
        """Si tiene AVX2, debe usar los tiers normales."""
        info = _make_info(ram=8.0, has_avx2=True)
        self.assertFalse(is_onnx_tier_viable(info))

    def test_not_viable_very_low_ram(self) -> None:
        info = _make_info(ram=0.5, has_avx2=False)
        self.assertFalse(is_onnx_tier_viable(info))

    def test_not_viable_no_disk(self) -> None:
        info = _make_info(ram=4.0, disk=0.1, has_avx2=False)
        self.assertFalse(is_onnx_tier_viable(info))

    def test_viable_minimum_ram(self) -> None:
        info = _make_info(ram=1.0, has_avx2=False)
        self.assertTrue(is_onnx_tier_viable(info))

    def test_viable_minimum_disk(self) -> None:
        info = _make_info(ram=2.0, disk=0.2, has_avx2=False)
        self.assertTrue(is_onnx_tier_viable(info))


# ============================================================
# is_onnx_runtime_available
# ============================================================


class TestIsOnnxRuntimeAvailable(unittest.TestCase):

    @patch.dict("sys.modules", {"onnxruntime": __import__("unittest").mock.MagicMock()})
    def test_available_when_importable(self) -> None:
        self.assertTrue(is_onnx_runtime_available())

    @patch.dict("sys.modules", {"onnxruntime": None})
    def test_not_available_when_not_importable(self) -> None:
        self.assertFalse(is_onnx_runtime_available())


# ============================================================
# tier_to_llm_config con tier -1
# ============================================================


class TestOnnxTierConfig(unittest.TestCase):

    def test_converts_onnx_tier(self) -> None:
        config = tier_to_llm_config(TIER_ONNX_FALLBACK)
        self.assertEqual(config.filename, TIER_ONNX_FALLBACK.filename)
        self.assertEqual(config.context_window, TIER_ONNX_FALLBACK.context_window)
        self.assertEqual(config.threads, TIER_ONNX_FALLBACK.threads)
        self.assertEqual(config.display_name, TIER_ONNX_FALLBACK.display_name)


if __name__ == "__main__":
    unittest.main()
