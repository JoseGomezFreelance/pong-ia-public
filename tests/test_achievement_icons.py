"""Tests del generador procedural de iconos de logros."""
from __future__ import annotations

import unittest
from typing import Any

import pygame

from pong.achievement_icons import (
    BLOCK_SIZE,
    ICON_PALETTE,
    ICON_SIZE,
    clear_icon_cache,
    get_icon,
    get_tier_color,
)
from pong.achievements import ACHIEVEMENT_DEFS


def _surface_rgb_pixels(surface: pygame.Surface) -> list[tuple[int, ...]]:
    """Devuelve lista plana de pixeles RGB de una surface."""
    w, h = surface.get_size()
    return [surface.get_at((x, y))[:3] for y in range(h) for x in range(w)]


def _iter_block_colors(surface: pygame.Surface) -> Any:
    """Itera conjuntos de colores por bloque 8x8."""
    w, h = surface.get_size()
    for by in range(0, h, BLOCK_SIZE):
        for bx in range(0, w, BLOCK_SIZE):
            colors: set[tuple[int, ...]] = set()
            for y in range(by, by + BLOCK_SIZE):
                for x in range(bx, bx + BLOCK_SIZE):
                    colors.add(surface.get_at((x, y))[:3])
            yield colors


class AchievementIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def setUp(self) -> None:
        clear_icon_cache()

    def test_icon_base_size_is_24x24(self) -> None:
        adef = ACHIEVEMENT_DEFS["career_matches_1"]
        icon = get_icon(adef, unlocked=True)
        self.assertEqual((ICON_SIZE, ICON_SIZE), icon.get_size())

    def test_icon_scale_2_is_48x48(self) -> None:
        adef = ACHIEVEMENT_DEFS["career_matches_1"]
        icon = get_icon(adef, unlocked=True, scale=2)
        self.assertEqual((ICON_SIZE * 2, ICON_SIZE * 2), icon.get_size())

    def test_icon_generation_is_deterministic_for_same_params(self) -> None:
        adef = ACHIEVEMENT_DEFS["perfect_match"]
        icon_a = get_icon(adef, unlocked=True, scale=1, frame=0)
        icon_b = get_icon(adef, unlocked=True, scale=1, frame=0)
        self.assertIs(icon_a, icon_b)  # cache hit exacto
        self.assertEqual(
            pygame.image.tostring(icon_a, "RGB"),
            pygame.image.tostring(icon_b, "RGB"),
        )

    def test_all_icons_use_only_allowed_palette(self) -> None:
        palette = set(ICON_PALETTE)
        for aid, adef in ACHIEVEMENT_DEFS.items():
            for unlocked in (False, True):
                with self.subTest(aid=aid, unlocked=unlocked):
                    icon = get_icon(adef, unlocked=unlocked)
                    for px in _surface_rgb_pixels(icon):
                        self.assertIn(px, palette)

    def test_each_8x8_block_has_at_most_two_colors(self) -> None:
        for aid, adef in ACHIEVEMENT_DEFS.items():
            for unlocked in (False, True):
                with self.subTest(aid=aid, unlocked=unlocked):
                    icon = get_icon(adef, unlocked=unlocked)
                    for block_colors in _iter_block_colors(icon):
                        self.assertLessEqual(len(block_colors), 2)

    def test_unlocked_icon_contains_tier_color(self) -> None:
        for aid, adef in ACHIEVEMENT_DEFS.items():
            with self.subTest(aid=aid):
                icon = get_icon(adef, unlocked=True)
                self.assertIn(get_tier_color(adef.tier), _surface_rgb_pixels(icon))

    def test_locked_and_unlocked_icons_are_different(self) -> None:
        adef = ACHIEVEMENT_DEFS["rally_50"]
        unlocked = get_icon(adef, unlocked=True)
        locked = get_icon(adef, unlocked=False)
        self.assertNotEqual(
            pygame.image.tostring(unlocked, "RGB"),
            pygame.image.tostring(locked, "RGB"),
        )


if __name__ == "__main__":
    unittest.main()
