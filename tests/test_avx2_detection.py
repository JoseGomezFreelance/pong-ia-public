"""Tests para la deteccion de AVX/AVX2 y su efecto en tiers y providers.

Verifica:
- Deteccion de SIMD por plataforma (arm64, x86 con/sin AVX2)
- Fallback seguro si la deteccion falla
- Todos los tiers en rojo si no hay AVX2
- Guard en LocalLLMProvider si no hay AVX2
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from pong.config.llm_tiers import (
    LLM_TIERS,
    TIER_0_FALLBACK,
    TierRecommendation,
    evaluate_all_tiers,
    evaluate_tier,
)
from pong.system_info import SystemInfo, _detect_cpu_simd


def _make_info(
    ram: float = 64.0,
    available_ram: float | None = None,
    gpu_type: str = "cpu",
    gpu_vram: float = 0.0,
    disk: float = 200.0,
    unified: bool = False,
    has_avx: bool = True,
    has_avx2: bool = True,
) -> SystemInfo:
    """Helper para crear SystemInfo de prueba."""
    if available_ram is None:
        available_ram = ram * 0.6
    return SystemInfo(
        total_ram_gb=ram,
        available_ram_gb=available_ram,
        unified_memory=unified,
        gpu_name="Test GPU",
        gpu_type=gpu_type,
        gpu_vram_gb=gpu_vram,
        disk_free_gb=disk,
        cpu_name="Test CPU",
        cpu_cores=4,
        has_avx=has_avx,
        has_avx2=has_avx2,
    )


# ============================================================
# Deteccion de SIMD
# ============================================================


class TestDetectCpuSimd(unittest.TestCase):
    """Verifica _detect_cpu_simd() con distintas plataformas."""

    @patch("pong.system_info.platform.machine", return_value="arm64")
    def test_arm64_always_true(self, _mock: object) -> None:
        """Apple Silicon retorna (True, True) sin leer flags."""
        has_avx, has_avx2 = _detect_cpu_simd()
        self.assertTrue(has_avx)
        self.assertTrue(has_avx2)

    @patch("pong.system_info.platform.machine", return_value="aarch64")
    def test_aarch64_always_true(self, _mock: object) -> None:
        """ARM 64-bit Linux retorna (True, True)."""
        has_avx, has_avx2 = _detect_cpu_simd()
        self.assertTrue(has_avx)
        self.assertTrue(has_avx2)

    @patch("pong.system_info._read_cpu_flags", return_value="sse sse2 avx avx2 fma")
    @patch("pong.system_info.platform.machine", return_value="x86_64")
    def test_x86_with_avx2(self, _m1: object, _m2: object) -> None:
        """x86_64 con AVX2 detectado correctamente."""
        has_avx, has_avx2 = _detect_cpu_simd()
        self.assertTrue(has_avx)
        self.assertTrue(has_avx2)

    @patch("pong.system_info._read_cpu_flags", return_value="sse sse2 avx fma")
    @patch("pong.system_info.platform.machine", return_value="x86_64")
    def test_x86_without_avx2(self, _m1: object, _m2: object) -> None:
        """x86_64 con AVX pero sin AVX2."""
        has_avx, has_avx2 = _detect_cpu_simd()
        self.assertTrue(has_avx)
        self.assertFalse(has_avx2)

    @patch("pong.system_info._read_cpu_flags", return_value="sse sse2 sse3 ssse3 sse4_1 sse4_2")
    @patch("pong.system_info.platform.machine", return_value="x86_64")
    def test_x86_without_avx(self, _m1: object, _m2: object) -> None:
        """x86_64 sin AVX ni AVX2 (CPU muy antigua)."""
        has_avx, has_avx2 = _detect_cpu_simd()
        self.assertFalse(has_avx)
        self.assertFalse(has_avx2)

    @patch("pong.system_info._read_cpu_flags", return_value="FPU VME SSE SSE2 AVX1.0 AVX2")
    @patch("pong.system_info.platform.machine", return_value="x86_64")
    def test_macos_sysctl_uppercase(self, _m1: object, _m2: object) -> None:
        """macOS sysctl retorna flags en mayusculas (AVX1.0 AVX2)."""
        has_avx, has_avx2 = _detect_cpu_simd()
        self.assertTrue(has_avx)
        self.assertTrue(has_avx2)

    @patch("pong.system_info._read_cpu_flags", side_effect=RuntimeError("boom"))
    @patch("pong.system_info.platform.machine", return_value="x86_64")
    def test_detection_failure_defaults_true(self, _m1: object, _m2: object) -> None:
        """Si la deteccion falla, default a (True, True) para no bloquear."""
        has_avx, has_avx2 = _detect_cpu_simd()
        self.assertTrue(has_avx)
        self.assertTrue(has_avx2)

    @patch("pong.system_info._read_cpu_flags", return_value="")
    @patch("pong.system_info.platform.machine", return_value="x86_64")
    def test_empty_flags_defaults_true(self, _m1: object, _m2: object) -> None:
        """Si los flags estan vacios, default a (True, True)."""
        has_avx, has_avx2 = _detect_cpu_simd()
        self.assertTrue(has_avx)
        self.assertTrue(has_avx2)


# ============================================================
# Integracion con tiers
# ============================================================


class TestTiersWithoutAVX2(unittest.TestCase):
    """Verifica que sin AVX2 todos los tiers son NOT_RECOMMENDED."""

    def test_no_avx2_all_tiers_red(self) -> None:
        """Sin AVX2, todos los tiers (incluido tier 0) son rojo."""
        info = _make_info(ram=64.0, disk=200.0, has_avx2=False)
        for tier in LLM_TIERS:
            rec = evaluate_tier(tier, info)
            self.assertEqual(
                rec, TierRecommendation.NOT_RECOMMENDED,
                f"Tier {tier.level} deberia ser rojo sin AVX2",
            )
        # Tier 0 tambien
        rec = evaluate_tier(TIER_0_FALLBACK, info)
        self.assertEqual(rec, TierRecommendation.NOT_RECOMMENDED)

    def test_no_avx2_evaluate_all_all_red(self) -> None:
        """evaluate_all_tiers retorna todo rojo sin AVX2."""
        info = _make_info(ram=64.0, disk=200.0, has_avx2=False)
        evals = evaluate_all_tiers(info)
        for tier, rec in evals:
            self.assertEqual(rec, TierRecommendation.NOT_RECOMMENDED)

    def test_with_avx2_tiers_normal(self) -> None:
        """Con AVX2 y hardware potente, los tiers se evaluan normalmente."""
        info = _make_info(ram=64.0, disk=200.0, has_avx2=True)
        evals = evaluate_all_tiers(info)
        # Con 64GB de RAM, al menos el tier 1 deberia ser verde
        greens = [t for t, r in evals if r == TierRecommendation.RECOMMENDED]
        self.assertTrue(len(greens) > 0, "Deberia haber al menos un tier verde")

    def test_no_avx2_but_has_avx(self) -> None:
        """CPU con AVX pero sin AVX2 (Sandy/Ivy Bridge)."""
        info = _make_info(ram=16.0, has_avx=True, has_avx2=False)
        rec = evaluate_tier(LLM_TIERS[0], info)
        self.assertEqual(rec, TierRecommendation.NOT_RECOMMENDED)


# ============================================================
# SystemInfo dataclass
# ============================================================


class TestSystemInfoAVXFields(unittest.TestCase):
    """Verifica los nuevos campos has_avx/has_avx2 en SystemInfo."""

    def test_default_values_true(self) -> None:
        """Los defaults de has_avx y has_avx2 son True."""
        info = SystemInfo(
            total_ram_gb=16.0,
            available_ram_gb=8.0,
            unified_memory=False,
            gpu_name="Test",
            gpu_type="cpu",
            gpu_vram_gb=0.0,
            disk_free_gb=100.0,
            cpu_name="Test",
            cpu_cores=4,
        )
        self.assertTrue(info.has_avx)
        self.assertTrue(info.has_avx2)

    def test_explicit_false(self) -> None:
        """Se pueden crear con valores False explicitamente."""
        info = _make_info(has_avx=False, has_avx2=False)
        self.assertFalse(info.has_avx)
        self.assertFalse(info.has_avx2)

    def test_frozen(self) -> None:
        """Los campos son inmutables (frozen dataclass)."""
        info = _make_info()
        with self.assertRaises(AttributeError):
            info.has_avx2 = False  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
