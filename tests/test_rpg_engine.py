"""Tests para pong/rpg_engine.py — motor RPG puro (sin pygame)."""

from __future__ import annotations

import unittest

from pong.rpg_engine import RPGState


class TestRPGStateCreation(unittest.TestCase):
    """Creacion y serializacion de RPGState."""

    def test_default_state(self) -> None:
        rpg = RPGState()
        self.assertFalse(rpg.rpg_unlocked)
        self.assertEqual(rpg.level, 1)
        self.assertEqual(rpg.total_xp_seconds, 0.0)
        self.assertEqual(rpg.skill_seconds_balance, 0.0)
        self.assertEqual(rpg.purchased_skills, [])
        self.assertEqual(rpg.ascension_count, 0)
        self.assertEqual(rpg.ascension_points_total, 0)
        self.assertEqual(rpg.ascension_points_available, 0)
        self.assertEqual(rpg.purchased_ascension_skills, {})

    def test_from_dict_empty(self) -> None:
        rpg = RPGState.from_dict({})
        self.assertFalse(rpg.rpg_unlocked)
        self.assertEqual(rpg.level, 1)

    def test_from_dict_full(self) -> None:
        data = {
            "rpg_unlocked": True,
            "level": 10,
            "total_xp_seconds": 500.0,
            "skill_seconds_balance": 42.5,
            "purchased_skills": ["spin", "wider_paddle"],
            "ascension_count": 2,
            "ascension_points_total": 30,
            "ascension_points_available": 5,
            "purchased_ascension_skills": {"veteran_start": 3, "legacy_paddle": 1},
        }
        rpg = RPGState.from_dict(data)
        self.assertTrue(rpg.rpg_unlocked)
        self.assertEqual(rpg.level, 10)
        self.assertEqual(rpg.total_xp_seconds, 500.0)
        self.assertEqual(rpg.skill_seconds_balance, 42.5)
        self.assertEqual(rpg.purchased_skills, ["spin", "wider_paddle"])
        self.assertEqual(rpg.ascension_count, 2)
        self.assertEqual(rpg.purchased_ascension_skills, {"veteran_start": 3, "legacy_paddle": 1})

    def test_from_dict_migrates_old_list_format(self) -> None:
        """Formato antiguo: purchased_ascension_skills era una lista."""
        data = {
            "purchased_ascension_skills": ["veteran_start", "hacker"],
        }
        rpg = RPGState.from_dict(data)
        self.assertEqual(rpg.purchased_ascension_skills, {"veteran_start": 1, "hacker": 1})

    def test_to_dict_roundtrip(self) -> None:
        rpg = RPGState(
            rpg_unlocked=True,
            level=5,
            total_xp_seconds=123.456,
            skill_seconds_balance=10.789,
            purchased_skills=["spin"],
            ascension_count=1,
            ascension_points_total=15,
            ascension_points_available=3,
            purchased_ascension_skills={"veteran_start": 2},
        )
        d = rpg.to_dict()
        rpg2 = RPGState.from_dict(d)
        self.assertEqual(rpg2.rpg_unlocked, True)
        self.assertEqual(rpg2.level, 5)
        self.assertAlmostEqual(rpg2.total_xp_seconds, 123.46, places=1)
        self.assertEqual(rpg2.purchased_skills, ["spin"])
        self.assertEqual(rpg2.purchased_ascension_skills, {"veteran_start": 2})


class TestXPAndLevels(unittest.TestCase):
    """XP, niveles y multiplicadores."""

    def test_tick_xp_basic(self) -> None:
        rpg = RPGState(rpg_unlocked=True)
        levels = rpg.tick_xp(5.0)
        self.assertEqual(rpg.total_xp_seconds, 5.0)
        self.assertEqual(rpg.skill_seconds_balance, 5.0)
        self.assertEqual(levels, 0)  # No llega a nivel 2 (10s)

    def test_tick_xp_level_up(self) -> None:
        rpg = RPGState(rpg_unlocked=True)
        rpg.tick_xp(11.0)  # > 10s = nivel 2
        self.assertEqual(rpg.level, 2)

    def test_tick_xp_multiple_levels(self) -> None:
        rpg = RPGState(rpg_unlocked=True)
        levels = rpg.tick_xp(200.0)  # Deberia subir varios niveles
        self.assertGreater(rpg.level, 2)
        self.assertGreater(levels, 1)

    def test_xp_multiplier_default(self) -> None:
        rpg = RPGState()
        self.assertEqual(rpg.get_xp_multiplier(), 1.0)

    def test_xp_multiplier_with_xp_bonus_skill(self) -> None:
        rpg = RPGState(purchased_skills=["xp_bonus"])
        self.assertAlmostEqual(rpg.get_xp_multiplier(), 1.5)

    def test_xp_multiplier_with_veteran_start(self) -> None:
        rpg = RPGState(purchased_ascension_skills={"veteran_start": 3})
        self.assertAlmostEqual(rpg.get_xp_multiplier(), 1.3)

    def test_xp_multiplier_stacks(self) -> None:
        rpg = RPGState(
            purchased_skills=["xp_bonus"],
            purchased_ascension_skills={"veteran_start": 2},
        )
        expected = 1.5 * 1.2  # xp_bonus * veteran_start Nv2
        self.assertAlmostEqual(rpg.get_xp_multiplier(), expected)

    def test_tick_xp_applies_multiplier(self) -> None:
        rpg = RPGState(purchased_skills=["xp_bonus"])
        rpg.tick_xp(10.0)
        self.assertAlmostEqual(rpg.total_xp_seconds, 15.0)

    def test_get_level_progress(self) -> None:
        rpg = RPGState(rpg_unlocked=True)
        rpg.tick_xp(15.0)  # Nivel 2 (10s), 5s into level 2
        level, xp_in, xp_needed = rpg.get_level_progress()
        self.assertEqual(level, 2)
        self.assertAlmostEqual(xp_in, 5.0)
        # Nivel 3 at 30s, so needed = 30 - 10 = 20
        self.assertAlmostEqual(xp_needed, 20.0)

    def test_get_level_progress_max(self) -> None:
        rpg = RPGState(rpg_unlocked=True, total_xp_seconds=999999)
        rpg._recalculate_level()
        level, xp_in, xp_needed = rpg.get_level_progress()
        self.assertEqual(level, 50)
        self.assertEqual(xp_in, 1.0)
        self.assertEqual(xp_needed, 1.0)

    def test_get_ascension_level_default(self) -> None:
        rpg = RPGState()
        self.assertEqual(rpg.get_ascension_level("veteran_start"), 0)
        self.assertEqual(rpg.get_ascension_level("nonexistent"), 0)

    def test_get_ascension_level_with_data(self) -> None:
        rpg = RPGState(purchased_ascension_skills={"veteran_start": 5})
        self.assertEqual(rpg.get_ascension_level("veteran_start"), 5)


class TestNormalSkills(unittest.TestCase):
    """Habilidades normales: desbloqueo, compra, activacion."""

    def test_skill_not_unlocked_at_low_level(self) -> None:
        rpg = RPGState(rpg_unlocked=True, level=1)
        self.assertFalse(rpg.is_skill_unlocked("spin"))  # Requiere nivel 2

    def test_skill_unlocked_at_level(self) -> None:
        rpg = RPGState(rpg_unlocked=True, level=2)
        self.assertTrue(rpg.is_skill_unlocked("spin"))

    def test_cannot_buy_locked_skill(self) -> None:
        rpg = RPGState(rpg_unlocked=True, level=1, skill_seconds_balance=100)
        self.assertFalse(rpg.can_buy_skill("spin"))

    def test_cannot_buy_without_balance(self) -> None:
        rpg = RPGState(rpg_unlocked=True, level=2, skill_seconds_balance=0)
        self.assertFalse(rpg.can_buy_skill("spin"))

    def test_can_buy_skill(self) -> None:
        rpg = RPGState(rpg_unlocked=True, level=2, skill_seconds_balance=5)
        self.assertTrue(rpg.can_buy_skill("spin"))

    def test_buy_skill_success(self) -> None:
        rpg = RPGState(rpg_unlocked=True, level=2, skill_seconds_balance=5)
        result = rpg.buy_skill("spin")
        self.assertTrue(result)
        self.assertIn("spin", rpg.purchased_skills)
        self.assertAlmostEqual(rpg.skill_seconds_balance, 4.0)  # 5 - 1 (cost)

    def test_buy_skill_already_purchased(self) -> None:
        rpg = RPGState(
            rpg_unlocked=True, level=2,
            skill_seconds_balance=5, purchased_skills=["spin"],
        )
        self.assertFalse(rpg.can_buy_skill("spin"))
        self.assertFalse(rpg.buy_skill("spin"))

    def test_buy_skill_unknown(self) -> None:
        rpg = RPGState(rpg_unlocked=True, level=50, skill_seconds_balance=999)
        self.assertFalse(rpg.buy_skill("nonexistent"))

    def test_is_skill_active(self) -> None:
        rpg = RPGState(purchased_skills=["spin"])
        self.assertTrue(rpg.is_skill_active("spin"))
        self.assertFalse(rpg.is_skill_active("wider_paddle"))


class TestAscensionSkills(unittest.TestCase):
    """Habilidades de ascension multinivel."""

    def test_can_buy_first_level(self) -> None:
        rpg = RPGState(ascension_points_available=1)
        self.assertTrue(rpg.can_buy_ascension_skill("veteran_start"))  # base_cost=1

    def test_cannot_buy_without_ap(self) -> None:
        rpg = RPGState(ascension_points_available=0)
        self.assertFalse(rpg.can_buy_ascension_skill("veteran_start"))

    def test_buy_ascension_skill_success(self) -> None:
        rpg = RPGState(ascension_points_available=1)
        result = rpg.buy_ascension_skill("veteran_start")
        self.assertTrue(result)
        self.assertEqual(rpg.get_ascension_level("veteran_start"), 1)
        self.assertEqual(rpg.ascension_points_available, 0)

    def test_cost_scales_with_level(self) -> None:
        rpg = RPGState(purchased_ascension_skills={"veteran_start": 2})
        # Nivel 3 cuesta base_cost(1) * 3 = 3
        self.assertEqual(rpg.get_ascension_skill_cost("veteran_start"), 3)

    def test_buy_multiple_levels(self) -> None:
        rpg = RPGState(ascension_points_available=100)
        for i in range(1, 6):
            cost_before = rpg.ascension_points_available
            result = rpg.buy_ascension_skill("veteran_start")
            self.assertTrue(result, f"Fallo al comprar nivel {i}")
            self.assertEqual(rpg.get_ascension_level("veteran_start"), i)

    def test_cannot_exceed_max_level(self) -> None:
        rpg = RPGState(
            ascension_points_available=9999,
            purchased_ascension_skills={"veteran_start": 10},
        )
        self.assertFalse(rpg.can_buy_ascension_skill("veteran_start"))
        self.assertFalse(rpg.buy_ascension_skill("veteran_start"))

    def test_buy_unknown_ascension_skill(self) -> None:
        rpg = RPGState(ascension_points_available=999)
        self.assertFalse(rpg.buy_ascension_skill("nonexistent"))

    def test_get_ascension_skill_cost_unknown(self) -> None:
        rpg = RPGState()
        self.assertEqual(rpg.get_ascension_skill_cost("nonexistent"), 999)


class TestAscension(unittest.TestCase):
    """Mecanica de ascension."""

    def test_can_ascend_requires_unlock(self) -> None:
        rpg = RPGState(rpg_unlocked=False, ascension_points_total=100)
        self.assertFalse(rpg.can_ascend())

    def test_can_ascend_requires_points(self) -> None:
        rpg = RPGState(rpg_unlocked=True, ascension_points_total=5)
        self.assertFalse(rpg.can_ascend())

    def test_can_ascend_ok(self) -> None:
        rpg = RPGState(rpg_unlocked=True, ascension_points_total=10)
        self.assertTrue(rpg.can_ascend())

    def test_perform_ascension_resets(self) -> None:
        rpg = RPGState(
            rpg_unlocked=True,
            level=20,
            total_xp_seconds=5000.0,
            skill_seconds_balance=200.0,
            purchased_skills=["spin", "wider_paddle"],
            ascension_count=0,
            ascension_points_total=20,
            ascension_points_available=5,
        )
        rpg.perform_ascension()
        self.assertEqual(rpg.level, 1)
        self.assertEqual(rpg.total_xp_seconds, 0.0)
        self.assertEqual(rpg.skill_seconds_balance, 0.0)
        self.assertEqual(rpg.purchased_skills, [])
        self.assertEqual(rpg.ascension_count, 1)
        self.assertEqual(rpg.ascension_points_available, 6)  # 5 + 1

    def test_perform_ascension_with_sovereign(self) -> None:
        rpg = RPGState(
            rpg_unlocked=True,
            level=20,
            total_xp_seconds=1000.0,
            skill_seconds_balance=200.0,
            purchased_skills=["spin"],
            ascension_count=0,
            ascension_points_total=20,
            ascension_points_available=0,
            purchased_ascension_skills={"sovereign": 5},
        )
        rpg.perform_ascension()
        # sovereign Nv5: 25% XP, 40% seconds
        self.assertAlmostEqual(rpg.total_xp_seconds, 250.0)
        self.assertAlmostEqual(rpg.skill_seconds_balance, 80.0)
        self.assertEqual(rpg.purchased_skills, [])
        # Ascension skills preserved
        self.assertEqual(rpg.get_ascension_level("sovereign"), 5)

    def test_add_ascension_points(self) -> None:
        rpg = RPGState()
        rpg.add_ascension_points(3)
        self.assertEqual(rpg.ascension_points_total, 3)
        self.assertEqual(rpg.ascension_points_available, 3)
        rpg.add_ascension_points(2)
        self.assertEqual(rpg.ascension_points_total, 5)
        self.assertEqual(rpg.ascension_points_available, 5)


class TestGameplayModifiers(unittest.TestCase):
    """Getters de modificadores de gameplay."""

    def test_paddle_height_bonus_default(self) -> None:
        rpg = RPGState()
        self.assertEqual(rpg.get_paddle_height_bonus(), 0)

    def test_paddle_height_bonus_with_skills(self) -> None:
        rpg = RPGState(
            purchased_skills=["wider_paddle"],
            purchased_ascension_skills={"legacy_paddle": 3},
        )
        self.assertEqual(rpg.get_paddle_height_bonus(), 12 + 24)

    def test_paddle_speed_bonus(self) -> None:
        rpg = RPGState(
            purchased_skills=["fast_reaction"],
            purchased_ascension_skills={"superior_reflex": 2},
        )
        self.assertEqual(rpg.get_paddle_speed_bonus(), 2 + 2)

    def test_ball_speed_multiplier(self) -> None:
        rpg = RPGState()
        self.assertEqual(rpg.get_ball_speed_multiplier(), 1.0)
        rpg.purchased_skills.append("tense_shot")
        self.assertAlmostEqual(rpg.get_ball_speed_multiplier(), 1.25)

    def test_spin_strength_no_skill(self) -> None:
        rpg = RPGState()
        self.assertEqual(rpg.get_spin_strength(), 0.0)

    def test_spin_strength_basic(self) -> None:
        rpg = RPGState(purchased_skills=["spin"])
        self.assertEqual(rpg.get_spin_strength(), 1.0)

    def test_spin_strength_with_master(self) -> None:
        rpg = RPGState(
            purchased_skills=["spin"],
            purchased_ascension_skills={"master_spin": 3},
        )
        self.assertAlmostEqual(rpg.get_spin_strength(), 1.6)  # 1.0 * (1+0.6)

    def test_directional_control(self) -> None:
        rpg = RPGState()
        self.assertFalse(rpg.has_directional_control())
        rpg.purchased_skills.append("directional")
        self.assertTrue(rpg.has_directional_control())

    def test_auto_reflex(self) -> None:
        rpg = RPGState()
        self.assertFalse(rpg.has_auto_reflex())
        rpg.purchased_skills.append("auto_reflex")
        self.assertTrue(rpg.has_auto_reflex())

    def test_curved_shot_and_strength(self) -> None:
        rpg = RPGState()
        self.assertFalse(rpg.has_curved_shot())
        self.assertEqual(rpg.get_curve_strength(), 0.0)
        rpg.purchased_skills.append("curved_shot")
        self.assertTrue(rpg.has_curved_shot())
        self.assertEqual(rpg.get_curve_strength(), 1.0)

    def test_curve_strength_with_master(self) -> None:
        rpg = RPGState(
            purchased_skills=["curved_shot"],
            purchased_ascension_skills={"master_spin": 2},
        )
        self.assertAlmostEqual(rpg.get_curve_strength(), 1.4)

    def test_double_impulse(self) -> None:
        rpg = RPGState()
        self.assertFalse(rpg.has_double_impulse())
        rpg.purchased_skills.append("double_impulse")
        self.assertTrue(rpg.has_double_impulse())

    def test_dual_instinct(self) -> None:
        rpg = RPGState()
        self.assertFalse(rpg.has_dual_instinct())
        self.assertEqual(rpg.get_dual_instinct_chance(), 0.0)
        rpg.purchased_skills.append("dual_instinct")
        self.assertTrue(rpg.has_dual_instinct())
        self.assertAlmostEqual(rpg.get_dual_instinct_chance(), 0.15)

    def test_trajectory_prediction(self) -> None:
        rpg = RPGState()
        self.assertFalse(rpg.has_trajectory_prediction())
        self.assertEqual(rpg.get_trajectory_distance(), 0.0)
        rpg.purchased_ascension_skills["rival_reading"] = 3
        self.assertTrue(rpg.has_trajectory_prediction())
        self.assertAlmostEqual(rpg.get_trajectory_distance(), 120.0)

    def test_ai_error_rate_default(self) -> None:
        rpg = RPGState()
        self.assertEqual(rpg.get_ai_error_rate(), 0.0)
        self.assertEqual(rpg.get_ai_error_offset(), (0, 0))

    def test_ai_error_rate_with_hacker(self) -> None:
        rpg = RPGState(purchased_ascension_skills={"hacker": 5})
        self.assertAlmostEqual(rpg.get_ai_error_rate(), 0.25)
        self.assertEqual(rpg.get_ai_error_offset(), (5, 25))

    def test_critical_hit_default(self) -> None:
        rpg = RPGState()
        self.assertEqual(rpg.get_critical_hit_chance(), 0.0)

    def test_critical_hit_with_skill(self) -> None:
        rpg = RPGState(purchased_ascension_skills={"critical_hit": 4})
        self.assertAlmostEqual(rpg.get_critical_hit_chance(), 0.22)
        self.assertAlmostEqual(rpg.get_critical_hit_multiplier(), 1.9)

    def test_critical_hit_multiplier_default(self) -> None:
        rpg = RPGState()
        # Sin skill, usa max(0, 1) = 1
        self.assertAlmostEqual(rpg.get_critical_hit_multiplier(), 1.6)

    def test_point_scored_xp_bonus(self) -> None:
        rpg = RPGState()
        self.assertEqual(rpg.get_point_scored_xp_bonus(), 0.0)
        rpg.purchased_ascension_skills["persistent_memory"] = 4
        self.assertAlmostEqual(rpg.get_point_scored_xp_bonus(), 12.0)

    def test_point_scored_seconds_bonus(self) -> None:
        rpg = RPGState()
        self.assertEqual(rpg.get_point_scored_seconds_bonus(), 0.0)
        rpg.purchased_ascension_skills["victory_echo"] = 2
        self.assertAlmostEqual(rpg.get_point_scored_seconds_bonus(), 10.0)


class TestFindSkillEdgeCases(unittest.TestCase):
    """Edge cases en busqueda de habilidades."""

    def test_find_skill_none(self) -> None:
        rpg = RPGState()
        self.assertIsNone(rpg._find_skill("nonexistent"))

    def test_find_ascension_skill_none(self) -> None:
        rpg = RPGState()
        self.assertIsNone(rpg._find_ascension_skill("nonexistent"))

    def test_is_skill_unlocked_unknown(self) -> None:
        rpg = RPGState(level=50)
        self.assertFalse(rpg.is_skill_unlocked("nonexistent"))

    def test_can_buy_skill_unknown(self) -> None:
        rpg = RPGState(level=50, skill_seconds_balance=999)
        self.assertFalse(rpg.can_buy_skill("nonexistent"))

    def test_can_buy_ascension_unknown(self) -> None:
        rpg = RPGState(ascension_points_available=999)
        self.assertFalse(rpg.can_buy_ascension_skill("nonexistent"))


if __name__ == "__main__":
    unittest.main()
