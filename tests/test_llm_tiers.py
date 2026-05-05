"""Tests para pong/config/llm_tiers.py — niveles de modelo LLM y recomendaciones."""
from __future__ import annotations

import unittest

from pong.config.llm_tiers import (
    LLM_TIERS,
    LLMTier,
    TierRecommendation,
    best_recommended_tier,
    evaluate_all_tiers,
    evaluate_tier,
    tier_to_llm_config,
)
from pong.system_info import SystemInfo


def _make_info(
    ram: float = 16.0,
    available_ram: float | None = None,
    gpu_type: str = "mps",
    gpu_vram: float = 0.0,
    disk: float = 100.0,
    unified: bool = True,
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
    )


# ============================================================
# Constantes de tiers
# ============================================================


class TestLLMTiers(unittest.TestCase):
    """Verifica la estructura de los 5 niveles."""

    def test_five_tiers(self) -> None:
        self.assertEqual(len(LLM_TIERS), 5)

    def test_levels_sequential(self) -> None:
        levels = [t.level for t in LLM_TIERS]
        self.assertEqual(levels, [1, 2, 3, 4, 5])

    def test_sizes_increasing(self) -> None:
        sizes = [t.model_size_bytes for t in LLM_TIERS]
        for i in range(1, len(sizes)):
            self.assertGreater(sizes[i], sizes[i - 1])

    def test_ram_thresholds_increasing(self) -> None:
        for i in range(1, len(LLM_TIERS)):
            self.assertGreater(
                LLM_TIERS[i].ram_recommended_gb,
                LLM_TIERS[i - 1].ram_recommended_gb,
            )

    def test_tier_1_is_single_file(self) -> None:
        self.assertFalse(LLM_TIERS[0].split)
        self.assertNotEqual(LLM_TIERS[0].download_url, "")

    def test_tiers_2_to_5_are_split(self) -> None:
        for tier in LLM_TIERS[1:]:
            self.assertTrue(tier.split, f"Tier {tier.level} should be split")
            self.assertEqual(tier.download_url, "")

    def test_all_have_repo_id(self) -> None:
        for tier in LLM_TIERS:
            self.assertIn("Qwen", tier.repo_id)
            self.assertIn("GGUF", tier.repo_id)

    def test_gguf_pattern_matches_filename(self) -> None:
        import fnmatch

        for tier in LLM_TIERS:
            self.assertTrue(
                fnmatch.fnmatch(tier.filename, tier.gguf_pattern),
                f"Tier {tier.level}: {tier.filename!r} no matchea {tier.gguf_pattern!r}",
            )


# ============================================================
# evaluate_tier
# ============================================================


class TestEvaluateTier(unittest.TestCase):
    """Tests para evaluate_tier y _effective_memory_gb."""

    def test_recommended_with_plenty_ram(self) -> None:
        # 32GB unified -> effective=27GB >> 8GB rec for 3B
        info = _make_info(ram=32.0)
        result = evaluate_tier(LLM_TIERS[0], info)  # 3B, necesita 8GB
        self.assertEqual(result, TierRecommendation.RECOMMENDED)

    def test_tight_with_marginal_ram(self) -> None:
        # 12GB unified -> effective=7GB, 3B: rec=8, tight=4 -> tight
        info = _make_info(ram=12.0)
        result = evaluate_tier(LLM_TIERS[0], info)  # 3B: rec=8, tight=4
        self.assertEqual(result, TierRecommendation.TIGHT)

    def test_not_recommended_low_ram(self) -> None:
        # 6GB unified -> effective=1GB, 3B: tight=4GB -> red
        info = _make_info(ram=6.0)
        result = evaluate_tier(LLM_TIERS[0], info)  # 3B: tight=4GB
        self.assertEqual(result, TierRecommendation.NOT_RECOMMENDED)

    def test_not_recommended_low_disk(self) -> None:
        info = _make_info(ram=64.0, disk=1.0)
        result = evaluate_tier(LLM_TIERS[0], info)  # ~2GB modelo + 1GB
        self.assertEqual(result, TierRecommendation.NOT_RECOMMENDED)

    def test_cuda_uses_vram(self) -> None:
        # CUDA con 12GB VRAM -> usa VRAM, no RAM
        info = _make_info(
            ram=64.0, gpu_type="cuda", gpu_vram=12.0, unified=False,
        )
        # Tier 3 (14B): rec=16GB -> 12GB VRAM < 16 -> tight
        result = evaluate_tier(LLM_TIERS[2], info)
        self.assertEqual(result, TierRecommendation.TIGHT)

    def test_mps_16gb_rejects_14b(self) -> None:
        # MPS 16GB unified -> effective=11GB
        # Tier 3 (14B): tight=12 -> 11 < 12 -> NOT_RECOMMENDED
        info = _make_info(ram=16.0, gpu_type="mps", unified=True)
        result = evaluate_tier(LLM_TIERS[2], info)
        self.assertEqual(result, TierRecommendation.NOT_RECOMMENDED)

    def test_mps_32gb_accepts_14b(self) -> None:
        # MPS 32GB unified -> effective=27GB
        # Tier 3 (14B): rec=16 -> 27 >= 16 -> RECOMMENDED
        info = _make_info(ram=32.0, gpu_type="mps", unified=True)
        result = evaluate_tier(LLM_TIERS[2], info)
        self.assertEqual(result, TierRecommendation.RECOMMENDED)

    def test_cpu_uses_total_ram(self) -> None:
        info = _make_info(ram=16.0, gpu_type="cpu", unified=False)
        result = evaluate_tier(LLM_TIERS[2], info)
        self.assertEqual(result, TierRecommendation.RECOMMENDED)


# ============================================================
# evaluate_all_tiers
# ============================================================


class TestEvaluateAllTiers(unittest.TestCase):
    """Tests para evaluate_all_tiers."""

    def test_returns_all_five(self) -> None:
        info = _make_info(ram=16.0)
        results = evaluate_all_tiers(info)
        self.assertEqual(len(results), 5)

    def test_16gb_unified_system(self) -> None:
        # 16GB unified -> effective=11GB
        # 3B(rec=8)=green, 7B(rec=12,tight=8)=tight, 14B(tight=12)=red
        info = _make_info(ram=16.0)
        results = evaluate_all_tiers(info)
        recs = [r for _, r in results]
        self.assertEqual(recs[0], TierRecommendation.RECOMMENDED)
        self.assertEqual(recs[1], TierRecommendation.TIGHT)
        self.assertEqual(recs[2], TierRecommendation.NOT_RECOMMENDED)
        self.assertEqual(recs[3], TierRecommendation.NOT_RECOMMENDED)
        self.assertEqual(recs[4], TierRecommendation.NOT_RECOMMENDED)

    def test_32gb_unified_system(self) -> None:
        # 32GB unified -> effective=27GB
        # 3B=green, 7B=green, 14B(16)=green, 32B(rec=32,tight=24)=tight, 72B=red
        info = _make_info(ram=32.0)
        results = evaluate_all_tiers(info)
        recs = [r for _, r in results]
        self.assertEqual(recs[0], TierRecommendation.RECOMMENDED)
        self.assertEqual(recs[1], TierRecommendation.RECOMMENDED)
        self.assertEqual(recs[2], TierRecommendation.RECOMMENDED)
        self.assertEqual(recs[3], TierRecommendation.TIGHT)
        self.assertEqual(recs[4], TierRecommendation.NOT_RECOMMENDED)

    def test_8gb_unified_system(self) -> None:
        # 8GB unified -> effective=3GB
        # 3B(tight=4)=red, rest=red
        info = _make_info(ram=8.0)
        results = evaluate_all_tiers(info)
        recs = [r for _, r in results]
        self.assertEqual(recs[0], TierRecommendation.NOT_RECOMMENDED)
        self.assertEqual(recs[1], TierRecommendation.NOT_RECOMMENDED)
        self.assertEqual(recs[2], TierRecommendation.NOT_RECOMMENDED)

    def test_10gb_unified_system(self) -> None:
        # 10GB unified -> effective=5GB
        # 3B(rec=8,tight=4)=tight, rest=red
        info = _make_info(ram=10.0)
        results = evaluate_all_tiers(info)
        recs = [r for _, r in results]
        self.assertEqual(recs[0], TierRecommendation.TIGHT)
        self.assertEqual(recs[1], TierRecommendation.NOT_RECOMMENDED)


# ============================================================
# best_recommended_tier
# ============================================================


class TestBestRecommendedTier(unittest.TestCase):
    """Tests para best_recommended_tier."""

    def test_16gb_unified_gets_tier1(self) -> None:
        # 16GB unified -> effective=11GB
        # 3B(8)=green, 7B(12)=tight -> best green = tier1
        info = _make_info(ram=16.0)
        best = best_recommended_tier(info)
        self.assertEqual(best.level, 1)

    def test_24gb_unified_gets_tier2(self) -> None:
        # 24GB unified -> effective=19GB
        # 3B(8)=green, 7B(12)=green, 14B(16)=green -> best green = tier3
        info = _make_info(ram=24.0)
        best = best_recommended_tier(info)
        self.assertEqual(best.level, 3)

    def test_72gb_gets_tier5(self) -> None:
        # 72GB unified -> effective=67GB >= 64 rec for tier5
        info = _make_info(ram=72.0)
        best = best_recommended_tier(info)
        self.assertEqual(best.level, 5)

    def test_64gb_unified_gets_tier4(self) -> None:
        # 64GB unified -> effective=59GB < 64 rec for tier5
        # tier5(rec=64)=tight, best green=tier4
        info = _make_info(ram=64.0)
        best = best_recommended_tier(info)
        self.assertEqual(best.level, 4)

    def test_8gb_unified_fallback_tier1(self) -> None:
        # 8GB unified -> effective=3GB -> all red -> fallback tier1
        info = _make_info(ram=8.0)
        best = best_recommended_tier(info)
        self.assertEqual(best.level, 1)

    def test_10gb_unified_gets_tier1(self) -> None:
        # 10GB unified -> effective=5GB
        # 3B(rec=8,tight=4)=tight -> best yellow = tier1
        info = _make_info(ram=10.0)
        best = best_recommended_tier(info)
        self.assertEqual(best.level, 1)

    def test_32gb_unified_gets_tier3(self) -> None:
        # 32GB unified -> effective=27GB
        # 3B=green, 7B=green, 14B(16)=green, 32B(32,tight=24)=tight
        # best green = tier3
        info = _make_info(ram=32.0)
        best = best_recommended_tier(info)
        self.assertEqual(best.level, 3)


# ============================================================
# tier_to_llm_config
# ============================================================


class TestTierToLLMConfig(unittest.TestCase):
    """Tests para tier_to_llm_config."""

    def test_converts_tier1(self) -> None:
        config = tier_to_llm_config(LLM_TIERS[0])
        self.assertEqual(config.filename, LLM_TIERS[0].filename)
        self.assertEqual(config.context_window, LLM_TIERS[0].context_window)
        self.assertEqual(config.threads, LLM_TIERS[0].threads)
        self.assertEqual(config.display_name, LLM_TIERS[0].display_name)

    def test_converts_all_tiers(self) -> None:
        for tier in LLM_TIERS:
            config = tier_to_llm_config(tier)
            self.assertEqual(config.filename, tier.filename)
            self.assertEqual(config.download_url, tier.download_url)
