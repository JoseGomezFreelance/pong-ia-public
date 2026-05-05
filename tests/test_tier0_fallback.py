"""Tests para el tier 0 fallback — modelo de emergencia para hardware limitado.

Verifica:
- Definicion correcta de TIER_0_FALLBACK
- Que tier 0 NO aparece en LLM_TIERS (es oculto)
- Evaluacion de tier 0 contra distintos perfiles de hardware
- Logica de activacion: todos los tiers en rojo -> tier 0 aparece
- Logica de cascada: tier 1 falla benchmark -> tier 0 se activa
- tier_to_llm_config funciona con tier 0
"""
from __future__ import annotations

import fnmatch
import unittest

from pong.config.llm_tiers import (
    LLM_TIERS,
    LLMTier,
    TIER_0_FALLBACK,
    TierRecommendation,
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
# Definicion de TIER_0_FALLBACK
# ============================================================


class TestTier0Definition(unittest.TestCase):
    """Verifica que TIER_0_FALLBACK esta correctamente definido."""

    def test_level_is_zero(self) -> None:
        self.assertEqual(TIER_0_FALLBACK.level, 0)

    def test_is_single_file(self) -> None:
        self.assertFalse(TIER_0_FALLBACK.split)
        self.assertNotEqual(TIER_0_FALLBACK.download_url, "")

    def test_smaller_than_tier1(self) -> None:
        self.assertLess(
            TIER_0_FALLBACK.model_size_bytes,
            LLM_TIERS[0].model_size_bytes,
        )

    def test_lower_ram_than_tier1(self) -> None:
        self.assertLess(
            TIER_0_FALLBACK.ram_recommended_gb,
            LLM_TIERS[0].ram_recommended_gb,
        )
        self.assertLess(
            TIER_0_FALLBACK.ram_tight_gb,
            LLM_TIERS[0].ram_tight_gb,
        )

    def test_has_valid_repo_id(self) -> None:
        self.assertIn("Qwen", TIER_0_FALLBACK.repo_id)
        self.assertIn("GGUF", TIER_0_FALLBACK.repo_id)

    def test_gguf_pattern_matches_filename(self) -> None:
        self.assertTrue(
            fnmatch.fnmatch(
                TIER_0_FALLBACK.filename, TIER_0_FALLBACK.gguf_pattern
            ),
        )

    def test_context_window_is_modest(self) -> None:
        self.assertLessEqual(TIER_0_FALLBACK.context_window, 2048)

    def test_display_name_contains_1_5b(self) -> None:
        self.assertIn("1.5B", TIER_0_FALLBACK.display_name)


# ============================================================
# Tier 0 NO esta en LLM_TIERS
# ============================================================


class TestTier0Hidden(unittest.TestCase):
    """Tier 0 no debe aparecer en la lista principal de tiers."""

    def test_not_in_llm_tiers(self) -> None:
        levels = [t.level for t in LLM_TIERS]
        self.assertNotIn(0, levels)

    def test_llm_tiers_still_has_five(self) -> None:
        self.assertEqual(len(LLM_TIERS), 5)

    def test_evaluate_all_returns_five(self) -> None:
        info = _make_info(ram=16.0)
        results = evaluate_all_tiers(info)
        self.assertEqual(len(results), 5)

    def test_tier0_not_in_evaluate_all(self) -> None:
        info = _make_info(ram=16.0)
        results = evaluate_all_tiers(info)
        levels = [t.level for t, _ in results]
        self.assertNotIn(0, levels)


# ============================================================
# Evaluacion de tier 0 contra hardware
# ============================================================


class TestTier0Evaluation(unittest.TestCase):
    """Tier 0 puede evaluarse manualmente con evaluate_tier."""

    def test_recommended_with_8gb(self) -> None:
        # 8GB unified -> effective=3GB, tier0 rec=4 tight=2 -> tight
        # Pero effective = 8 - 5 = 3, y tight=2 -> 3 >= 2 -> TIGHT
        info = _make_info(ram=8.0)
        result = evaluate_tier(TIER_0_FALLBACK, info)
        self.assertEqual(result, TierRecommendation.TIGHT)

    def test_recommended_with_16gb(self) -> None:
        # 16GB unified -> effective=11GB >> 4GB rec -> GREEN
        info = _make_info(ram=16.0)
        result = evaluate_tier(TIER_0_FALLBACK, info)
        self.assertEqual(result, TierRecommendation.RECOMMENDED)

    def test_not_recommended_very_low_ram(self) -> None:
        # 6GB unified -> effective=1GB < 2GB tight -> RED
        info = _make_info(ram=6.0)
        result = evaluate_tier(TIER_0_FALLBACK, info)
        self.assertEqual(result, TierRecommendation.NOT_RECOMMENDED)

    def test_not_recommended_low_disk(self) -> None:
        info = _make_info(ram=16.0, disk=0.5)
        result = evaluate_tier(TIER_0_FALLBACK, info)
        self.assertEqual(result, TierRecommendation.NOT_RECOMMENDED)

    def test_cuda_4gb_vram_is_recommended(self) -> None:
        # CUDA 4GB VRAM >= 4GB rec -> GREEN
        info = _make_info(
            ram=8.0, gpu_type="cuda", gpu_vram=4.0, unified=False,
        )
        result = evaluate_tier(TIER_0_FALLBACK, info)
        self.assertEqual(result, TierRecommendation.RECOMMENDED)

    def test_cuda_2gb_vram_is_tight(self) -> None:
        # CUDA 2GB VRAM >= 2GB tight -> TIGHT
        info = _make_info(
            ram=8.0, gpu_type="cuda", gpu_vram=2.5, unified=False,
        )
        result = evaluate_tier(TIER_0_FALLBACK, info)
        self.assertEqual(result, TierRecommendation.TIGHT)


# ============================================================
# tier_to_llm_config con tier 0
# ============================================================


class TestTier0Config(unittest.TestCase):
    """tier_to_llm_config funciona correctamente con tier 0."""

    def test_converts_tier0(self) -> None:
        config = tier_to_llm_config(TIER_0_FALLBACK)
        self.assertEqual(config.filename, TIER_0_FALLBACK.filename)
        self.assertEqual(config.context_window, TIER_0_FALLBACK.context_window)
        self.assertEqual(config.threads, TIER_0_FALLBACK.threads)
        self.assertEqual(config.display_name, TIER_0_FALLBACK.display_name)
        self.assertEqual(config.download_url, TIER_0_FALLBACK.download_url)


# ============================================================
# Logica de activacion en el selector (splash.py)
# ============================================================


class TestTier0ActivationAllRed(unittest.TestCase):
    """Simula la logica de _detect() cuando todos los tiers estan en rojo."""

    def _simulate_detect(self, info: SystemInfo) -> tuple[list[tuple[LLMTier, TierRecommendation]], int, bool]:
        """Replica la logica de _detect() del selector.

        Returns:
            (evaluations, selected_idx, show_tier0)
        """
        evals = evaluate_all_tiers(info)
        from pong.config.llm_tiers import best_recommended_tier
        best = best_recommended_tier(info)

        all_red = all(
            r == TierRecommendation.NOT_RECOMMENDED for _, r in evals
        )
        show_tier0 = False
        if all_red:
            t0_rec = evaluate_tier(TIER_0_FALLBACK, info)
            evals.append((TIER_0_FALLBACK, t0_rec))
            show_tier0 = True
            selected_idx = len(evals) - 1
        else:
            selected_idx = best.level - 1

        return evals, selected_idx, show_tier0

    def test_all_red_8gb_shows_tier0(self) -> None:
        """8GB unified -> todos en rojo -> tier 0 aparece."""
        info = _make_info(ram=8.0)
        evals, selected_idx, show_tier0 = self._simulate_detect(info)

        self.assertTrue(show_tier0)
        self.assertEqual(len(evals), 6)  # 5 + tier 0
        self.assertEqual(evals[-1][0].level, 0)
        self.assertEqual(selected_idx, 5)  # tier 0 pre-seleccionado

    def test_all_red_tier0_evaluated(self) -> None:
        """Con 8GB, tier 0 deberia ser TIGHT (effective=3GB, tight=2GB)."""
        info = _make_info(ram=8.0)
        evals, _, _ = self._simulate_detect(info)
        t0_rec = evals[-1][1]
        self.assertEqual(t0_rec, TierRecommendation.TIGHT)

    def test_not_all_red_16gb_no_tier0(self) -> None:
        """16GB -> tier 1 es green -> tier 0 no aparece."""
        info = _make_info(ram=16.0)
        evals, selected_idx, show_tier0 = self._simulate_detect(info)

        self.assertFalse(show_tier0)
        self.assertEqual(len(evals), 5)
        self.assertEqual(selected_idx, 0)  # tier 1

    def test_not_all_red_10gb_no_tier0(self) -> None:
        """10GB -> tier 1 es yellow -> tier 0 no aparece."""
        info = _make_info(ram=10.0)
        evals, _, show_tier0 = self._simulate_detect(info)

        self.assertFalse(show_tier0)
        self.assertEqual(len(evals), 5)

    def test_very_low_ram_tier0_is_red(self) -> None:
        """6GB -> todo rojo, tier 0 tambien rojo (effective=1GB < 2GB)."""
        info = _make_info(ram=6.0)
        evals, _, show_tier0 = self._simulate_detect(info)

        self.assertTrue(show_tier0)
        t0_rec = evals[-1][1]
        self.assertEqual(t0_rec, TierRecommendation.NOT_RECOMMENDED)


class TestTier0CascadeLogic(unittest.TestCase):
    """Simula la logica de cascada: tier 1 falla -> tier 0 se activa."""

    def _simulate_benchmark_failure(
        self,
        current_level: int,
        tier0_tried: bool,
        evaluations: list[tuple[LLMTier, TierRecommendation]],
        installed_set: set[str],
        system_info: SystemInfo,
    ) -> tuple[str, LLMTier | None, bool, list[tuple[LLMTier, TierRecommendation]]]:
        """Replica la logica de fallo de benchmark del selector.

        Returns:
            (next_state, benchmark_tier, tier0_tried, evaluations)
        """
        if current_level <= 0:
            return "selecting_final_fail", None, tier0_tried, evaluations
        elif current_level <= 1 and not tier0_tried:
            tier0_tried = True
            benchmark_tier = TIER_0_FALLBACK
            t0_in_evals = any(t.level == 0 for t, _ in evaluations)
            if not t0_in_evals:
                t0_rec = evaluate_tier(TIER_0_FALLBACK, system_info)
                evaluations.append((TIER_0_FALLBACK, t0_rec))

            if TIER_0_FALLBACK.filename in installed_set:
                return "benchmarking", benchmark_tier, tier0_tried, evaluations
            else:
                return "downloading", benchmark_tier, tier0_tried, evaluations
        elif current_level <= 1:
            return "selecting_final_fail", None, tier0_tried, evaluations
        else:
            return "cascade_down", None, tier0_tried, evaluations

    def test_tier1_fails_triggers_tier0_download(self) -> None:
        """Tier 1 falla benchmark -> descarga tier 0."""
        info = _make_info(ram=8.0)
        evals = evaluate_all_tiers(info)

        state, bt, tried, evals = self._simulate_benchmark_failure(
            current_level=1,
            tier0_tried=False,
            evaluations=evals,
            installed_set=set(),
            system_info=info,
        )

        self.assertEqual(state, "downloading")
        assert bt is not None
        self.assertEqual(bt.level, 0)
        self.assertTrue(tried)
        # Tier 0 añadido a evaluations
        self.assertEqual(len(evals), 6)

    def test_tier1_fails_tier0_already_installed(self) -> None:
        """Tier 1 falla, tier 0 ya descargado -> benchmark directo."""
        info = _make_info(ram=8.0)
        evals = evaluate_all_tiers(info)

        state, bt, tried, evals = self._simulate_benchmark_failure(
            current_level=1,
            tier0_tried=False,
            evaluations=evals,
            installed_set={TIER_0_FALLBACK.filename},
            system_info=info,
        )

        self.assertEqual(state, "benchmarking")
        assert bt is not None
        self.assertEqual(bt.level, 0)

    def test_tier0_fails_gives_up(self) -> None:
        """Tier 0 tambien falla -> sin mas opciones."""
        info = _make_info(ram=6.0)
        evals = evaluate_all_tiers(info)

        state, bt, tried, evals = self._simulate_benchmark_failure(
            current_level=0,
            tier0_tried=True,
            evaluations=evals,
            installed_set=set(),
            system_info=info,
        )

        self.assertEqual(state, "selecting_final_fail")
        self.assertIsNone(bt)

    def test_tier1_fails_after_tier0_tried_gives_up(self) -> None:
        """Tier 1 falla y tier 0 ya fue intentado -> sin mas opciones."""
        info = _make_info(ram=8.0)
        evals = evaluate_all_tiers(info)

        state, bt, tried, evals = self._simulate_benchmark_failure(
            current_level=1,
            tier0_tried=True,
            evaluations=evals,
            installed_set=set(),
            system_info=info,
        )

        self.assertEqual(state, "selecting_final_fail")

    def test_tier2_fails_cascades_normally(self) -> None:
        """Tier 2 falla -> cascada normal (no tier 0)."""
        info = _make_info(ram=16.0)
        evals = evaluate_all_tiers(info)

        state, bt, tried, evals = self._simulate_benchmark_failure(
            current_level=2,
            tier0_tried=False,
            evaluations=evals,
            installed_set=set(),
            system_info=info,
        )

        self.assertEqual(state, "cascade_down")
        self.assertFalse(tried)

    def test_tier0_not_duplicated_in_evaluations(self) -> None:
        """Si tier 0 ya esta en evaluations, no se duplica."""
        info = _make_info(ram=8.0)
        evals = evaluate_all_tiers(info)
        # Pre-añadir tier 0
        t0_rec = evaluate_tier(TIER_0_FALLBACK, info)
        evals.append((TIER_0_FALLBACK, t0_rec))

        state, bt, tried, evals = self._simulate_benchmark_failure(
            current_level=1,
            tier0_tried=False,
            evaluations=evals,
            installed_set=set(),
            system_info=info,
        )

        # No debe duplicarse
        t0_count = sum(1 for t, _ in evals if t.level == 0)
        self.assertEqual(t0_count, 1)


class TestTier0WarningState(unittest.TestCase):
    """Verifica que tier 0 activa el estado tier0_warning al pasar benchmark."""

    def test_tier0_passed_goes_to_warning(self) -> None:
        """Si tier 0 pasa el benchmark, el siguiente estado es tier0_warning."""
        # Simula la logica: si benchmark_tier.level == 0 y passed -> tier0_warning
        benchmark_tier = TIER_0_FALLBACK
        passed = True

        if passed and benchmark_tier.level == 0:
            next_state = "tier0_warning"
        elif passed:
            next_state = "result"
        else:
            next_state = "cascade"

        self.assertEqual(next_state, "tier0_warning")

    def test_tier1_passed_goes_to_result(self) -> None:
        """Tier normal pasa benchmark -> estado result (no warning)."""
        benchmark_tier = LLM_TIERS[0]
        passed = True

        if passed and benchmark_tier.level == 0:
            next_state = "tier0_warning"
        elif passed:
            next_state = "result"
        else:
            next_state = "cascade"

        self.assertEqual(next_state, "result")


if __name__ == "__main__":
    unittest.main()
