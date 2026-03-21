"""
Generador procedural de iconos de logros estilo ZX Spectrum (24x24).

Cada icono:
- Mide 24x24 pixeles (3x3 bloques de 8x8).
- Se genera localmente en runtime (sin assets externos).
- Usa una paleta restringida ZX.
- Cumple la regla de 2 colores maximo por bloque 8x8.
"""

from __future__ import annotations

import random
from typing import Any

import pygame

# Type aliases for icon drawing functions
_Color = tuple[int, int, int]
_PixelGrid = list[list[_Color]]

from pong.achievements import (
    MOTIF_42_SPIRAL,
    MOTIF_BEAST_TAMER,
    MOTIF_BROKEN_HELMET,
    MOTIF_CASSETTE,
    MOTIF_DIALOG_BUBBLE,
    MOTIF_EUPHORIA_STAR,
    MOTIF_FURY_CLAW,
    MOTIF_GLITCH_CHIP,
    MOTIF_MONO_CRT,
    MOTIF_NIGHT_MOON,
    MOTIF_PADDLE_TROPHY,
    MOTIF_PERFECT_SEAL,
    MOTIF_RALLY_WAVE,
    MOTIF_SAD_DROP,
    MOTIF_SCORE_CHIP,
    MOTIF_SPEED_COMET,
    MOTIF_SPECTRUM_WHEEL,
    MOTIF_STREAK_CHAIN,
    TIER_ADVANCED,
    TIER_HIGH,
    TIER_INTERMEDIATE,
    TIER_LEGENDARY,
)
from pong.config.zx_spectrum import (
    ZX_BLACK,
    ZX_BLUE_BRIGHT,
    ZX_BROWN,
    ZX_GRAY_DARK,
    ZX_GRAY_LIGHT,
    ZX_GREEN_BRIGHT,
    ZX_MAGENTA_BRIGHT,
    ZX_RED_DARK,
    ZX_RED_BRIGHT,
    ZX_WHITE,
    ZX_YELLOW,
)

ICON_SIZE = 24
BLOCK_SIZE = 8

# Paleta restringida usada por los iconos de logros.
# Nota: #AA5500 aparecia repetido en la propuesta original; se deduplica.
ICON_PALETTE = [
    ZX_BLACK,         # #000000
    ZX_GRAY_DARK,     # #555555
    ZX_BROWN,         # #AA5500
    ZX_GREEN_BRIGHT,  # #55FF55
    ZX_BLUE_BRIGHT,   # #5555FF
    ZX_MAGENTA_BRIGHT,  # #FF55FF
    ZX_YELLOW,        # #FFFF55
    ZX_RED_BRIGHT,    # #FF5555
    ZX_RED_DARK,      # #AA0000
    ZX_GRAY_LIGHT,    # #AAAAAA
    ZX_WHITE,         # #FFFFFF
]

TIER_COLORS = {
    TIER_INTERMEDIATE: ZX_GREEN_BRIGHT,    # verde
    TIER_ADVANCED: ZX_BLUE_BRIGHT,         # azul
    TIER_HIGH: ZX_MAGENTA_BRIGHT,          # purpura
    TIER_LEGENDARY: ZX_YELLOW,             # dorado
}

_ICON_CACHE: dict[tuple[str, bool, int, int], pygame.Surface] = {}


def clear_icon_cache() -> None:
    """Limpia cache interna de superficies de iconos."""
    _ICON_CACHE.clear()


def get_tier_color(tier: str) -> tuple[int, int, int]:
    """Devuelve el color principal asociado al tier."""
    return TIER_COLORS.get(tier, ZX_WHITE)


def get_icon(achievement_def: Any, unlocked: bool, scale: int = 1, frame: int = 0) -> pygame.Surface:
    """Genera (o recupera de cache) el icono de un logro.

    Args:
        achievement_def: AchievementDef con id, tier, motif, hidden, icon_seed.
        unlocked:        Si el logro esta desbloqueado.
        scale:           Escala entera opcional (1 => 24x24, 2 => 48x48).
        frame:           Frame opcional para variaciones leves deterministas.

    Returns:
        pygame.Surface con el icono.
    """
    scale = max(1, int(scale))
    frame = int(frame) % 8
    cache_key = (achievement_def.id, bool(unlocked), scale, frame)
    cached = _ICON_CACHE.get(cache_key)
    if cached is not None:
        return cached

    surface = _render_icon_surface(achievement_def, unlocked, frame)
    if scale != 1:
        size = ICON_SIZE * scale
        surface = pygame.transform.scale(surface, (size, size))

    _ICON_CACHE[cache_key] = surface
    return surface


def _render_icon_surface(achievement_def: Any, unlocked: bool, frame: int) -> pygame.Surface:
    """Renderiza superficie 24x24 sin escalado."""
    rng = random.Random(achievement_def.icon_seed + frame * 1009)

    if unlocked:
        primary = get_tier_color(achievement_def.tier)
        secondary = ZX_WHITE
        accent = ZX_GRAY_LIGHT
        motif = achievement_def.motif
    else:
        # Bloqueado visible: silueta gris del mismo motivo.
        # Secreto: icono misterio generico rojo/gris.
        if achievement_def.hidden:
            primary = ZX_RED_DARK
            secondary = ZX_GRAY_DARK
            accent = ZX_GRAY_LIGHT
            motif = "mystery"
        else:
            primary = ZX_GRAY_LIGHT
            secondary = ZX_GRAY_DARK
            accent = ZX_WHITE
            motif = achievement_def.motif

    pixels = [[ZX_BLACK for _x in range(ICON_SIZE)] for _y in range(ICON_SIZE)]

    # Marco base estilo tile retro.
    _draw_rect_outline(pixels, 0, 0, 24, 24, secondary)
    _draw_rect_outline(pixels, 1, 1, 22, 22, primary)

    drawer = _MOTIF_DRAWERS.get(motif, _draw_motif_mystery)
    drawer(pixels, primary, secondary, accent, rng)

    if not unlocked:
        _draw_lock_slash(pixels, secondary)

    pixels = _enforce_palette(pixels, ICON_PALETTE)
    pixels = _enforce_attribute_blocks(pixels)

    surface = pygame.Surface((ICON_SIZE, ICON_SIZE))
    for y in range(ICON_SIZE):
        for x in range(ICON_SIZE):
            surface.set_at((x, y), pixels[y][x])
    return surface


# ---------------------------------------------------------------------------
# Dibujo base
# ---------------------------------------------------------------------------


def _set_px(pixels: _PixelGrid, x: int, y: int, color: _Color) -> None:
    if 0 <= x < ICON_SIZE and 0 <= y < ICON_SIZE:
        pixels[y][x] = color


def _draw_line(pixels: _PixelGrid, x0: int, y0: int, x1: int, y1: int, color: _Color) -> None:
    dx = abs(x1 - x0)
    sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    while True:
        _set_px(pixels, x, y, color)
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy


def _draw_rect(pixels: _PixelGrid, x: int, y: int, w: int, h: int, color: _Color) -> None:
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            _set_px(pixels, xx, yy, color)


def _draw_rect_outline(pixels: _PixelGrid, x: int, y: int, w: int, h: int, color: _Color) -> None:
    for xx in range(x, x + w):
        _set_px(pixels, xx, y, color)
        _set_px(pixels, xx, y + h - 1, color)
    for yy in range(y, y + h):
        _set_px(pixels, x, yy, color)
        _set_px(pixels, x + w - 1, yy, color)


def _draw_circle_fill(pixels: _PixelGrid, cx: int, cy: int, r: int, color: _Color) -> None:
    rr = r * r
    for yy in range(cy - r, cy + r + 1):
        for xx in range(cx - r, cx + r + 1):
            if (xx - cx) * (xx - cx) + (yy - cy) * (yy - cy) <= rr:
                _set_px(pixels, xx, yy, color)


def _draw_diamond_fill(pixels: _PixelGrid, cx: int, cy: int, r: int, color: _Color) -> None:
    for yy in range(cy - r, cy + r + 1):
        for xx in range(cx - r, cx + r + 1):
            if abs(xx - cx) + abs(yy - cy) <= r:
                _set_px(pixels, xx, yy, color)


def _sprinkles(pixels: _PixelGrid, rng: random.Random, color: _Color, count: int) -> None:
    for _ in range(count):
        x = rng.randint(3, 20)
        y = rng.randint(3, 20)
        _set_px(pixels, x, y, color)


def _draw_lock_slash(pixels: _PixelGrid, color: _Color) -> None:
    """Marca visual de bloqueado (diagonal tenue)."""
    _draw_line(pixels, 4, 20, 20, 4, color)


# ---------------------------------------------------------------------------
# Motivos
# ---------------------------------------------------------------------------


def _draw_motif_cassette(pixels: _PixelGrid, primary: _Color, secondary: _Color, accent: _Color, _rng: random.Random) -> None:
    _draw_rect(pixels, 5, 7, 14, 10, primary)
    _draw_rect_outline(pixels, 5, 7, 14, 10, secondary)
    _draw_rect(pixels, 8, 9, 8, 4, accent)
    _draw_circle_fill(pixels, 9, 14, 1, secondary)
    _draw_circle_fill(pixels, 14, 14, 1, secondary)
    _draw_rect(pixels, 8, 16, 8, 1, secondary)


def _draw_motif_paddle_trophy(pixels: _PixelGrid, primary: _Color, secondary: _Color, _accent: _Color, _rng: random.Random) -> None:
    _draw_rect(pixels, 8, 6, 8, 2, secondary)
    _draw_rect(pixels, 7, 8, 10, 5, primary)
    _draw_rect_outline(pixels, 7, 8, 10, 5, secondary)
    _draw_rect(pixels, 10, 13, 4, 3, primary)
    _draw_rect(pixels, 8, 16, 8, 3, secondary)
    _draw_rect(pixels, 6, 9, 1, 3, secondary)
    _draw_rect(pixels, 17, 9, 1, 3, secondary)


def _draw_motif_score_chip(pixels: _PixelGrid, primary: _Color, secondary: _Color, accent: _Color, _rng: random.Random) -> None:
    _draw_rect(pixels, 6, 6, 12, 12, primary)
    _draw_rect_outline(pixels, 6, 6, 12, 12, secondary)
    _draw_rect(pixels, 9, 9, 6, 6, accent)
    for pos in range(6, 18, 2):
        _set_px(pixels, pos, 5, secondary)
        _set_px(pixels, pos, 18, secondary)
        _set_px(pixels, 5, pos, secondary)
        _set_px(pixels, 18, pos, secondary)


def _draw_motif_rally_wave(pixels: _PixelGrid, primary: _Color, secondary: _Color, accent: _Color, _rng: random.Random) -> None:
    points = [(3, 16), (7, 10), (11, 14), (15, 8), (20, 12)]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        _draw_line(pixels, x0, y0, x1, y1, primary)
    _draw_circle_fill(pixels, 3, 16, 1, secondary)
    _draw_circle_fill(pixels, 20, 12, 1, secondary)
    _draw_line(pixels, 4, 19, 19, 19, accent)


def _draw_motif_streak_chain(pixels: _PixelGrid, primary: _Color, secondary: _Color, _accent: _Color, _rng: random.Random) -> None:
    _draw_circle_fill(pixels, 7, 12, 3, primary)
    _draw_circle_fill(pixels, 12, 12, 3, secondary)
    _draw_circle_fill(pixels, 17, 12, 3, primary)
    _draw_circle_fill(pixels, 7, 12, 1, ZX_BLACK)
    _draw_circle_fill(pixels, 12, 12, 1, ZX_BLACK)
    _draw_circle_fill(pixels, 17, 12, 1, ZX_BLACK)


def _draw_motif_perfect_seal(pixels: _PixelGrid, primary: _Color, secondary: _Color, accent: _Color, _rng: random.Random) -> None:
    _draw_diamond_fill(pixels, 12, 12, 7, primary)
    _draw_diamond_fill(pixels, 12, 12, 5, secondary)
    _draw_line(pixels, 12, 7, 12, 17, accent)
    _draw_line(pixels, 7, 12, 17, 12, accent)
    _draw_line(pixels, 9, 9, 15, 15, accent)
    _draw_line(pixels, 15, 9, 9, 15, accent)


def _draw_motif_speed_comet(pixels: _PixelGrid, primary: _Color, secondary: _Color, accent: _Color, _rng: random.Random) -> None:
    _draw_circle_fill(pixels, 17, 8, 3, primary)
    _draw_circle_fill(pixels, 17, 8, 1, secondary)
    _draw_line(pixels, 14, 10, 6, 15, accent)
    _draw_line(pixels, 13, 11, 5, 18, accent)
    _draw_line(pixels, 12, 12, 4, 20, secondary)


def _draw_motif_42_spiral(pixels: _PixelGrid, primary: _Color, secondary: _Color, accent: _Color, _rng: random.Random) -> None:
    _draw_rect_outline(pixels, 6, 6, 12, 12, primary)
    _draw_rect_outline(pixels, 8, 8, 8, 8, secondary)
    _draw_rect_outline(pixels, 10, 10, 4, 4, accent)
    # "42" ultracompacto
    _draw_line(pixels, 6, 18, 10, 18, secondary)
    _draw_line(pixels, 8, 15, 8, 20, secondary)
    _draw_line(pixels, 14, 16, 17, 16, accent)
    _draw_line(pixels, 17, 16, 14, 20, accent)
    _draw_line(pixels, 14, 20, 17, 20, accent)


def _draw_motif_dialog_bubble(pixels: _PixelGrid, primary: _Color, secondary: _Color, accent: _Color, _rng: random.Random) -> None:
    _draw_rect(pixels, 5, 6, 14, 10, primary)
    _draw_rect_outline(pixels, 5, 6, 14, 10, secondary)
    _draw_rect(pixels, 9, 16, 3, 3, primary)
    _draw_rect_outline(pixels, 9, 16, 3, 3, secondary)
    _draw_rect(pixels, 8, 9, 2, 2, accent)
    _draw_rect(pixels, 12, 9, 2, 2, accent)
    _draw_rect(pixels, 16, 9, 2, 2, accent)


def _draw_motif_broken_helmet(pixels: _PixelGrid, primary: _Color, secondary: _Color, accent: _Color, _rng: random.Random) -> None:
    _draw_circle_fill(pixels, 12, 11, 6, primary)
    _draw_rect(pixels, 6, 11, 12, 6, primary)
    _draw_rect_outline(pixels, 6, 8, 12, 9, secondary)
    _draw_line(pixels, 12, 8, 10, 12, accent)
    _draw_line(pixels, 10, 12, 14, 16, accent)


def _draw_motif_mono_crt(pixels: _PixelGrid, primary: _Color, secondary: _Color, accent: _Color, _rng: random.Random) -> None:
    _draw_rect(pixels, 5, 5, 14, 10, primary)
    _draw_rect_outline(pixels, 5, 5, 14, 10, secondary)
    _draw_rect(pixels, 7, 7, 10, 6, accent)
    _draw_rect(pixels, 10, 15, 4, 2, primary)
    _draw_rect(pixels, 8, 17, 8, 2, secondary)


def _draw_motif_fury_claw(pixels: _PixelGrid, primary: _Color, secondary: _Color, accent: _Color, rng: random.Random) -> None:
    _draw_line(pixels, 7, 18, 11, 6, primary)
    _draw_line(pixels, 11, 18, 15, 6, primary)
    _draw_line(pixels, 15, 18, 19, 6, primary)
    _draw_circle_fill(pixels, 6, 6, 1, secondary)
    _sprinkles(pixels, rng, accent, 5)


def _draw_motif_sad_drop(pixels: _PixelGrid, primary: _Color, secondary: _Color, accent: _Color, _rng: random.Random) -> None:
    _draw_circle_fill(pixels, 12, 10, 5, primary)
    for yy in range(10, 19):
        width = max(1, 9 - (yy - 10))
        _draw_rect(pixels, 12 - width // 2, yy, width, 1, primary)
    _draw_circle_fill(pixels, 10, 10, 1, secondary)
    _draw_circle_fill(pixels, 14, 10, 1, secondary)
    _draw_rect(pixels, 10, 13, 4, 1, accent)


def _draw_motif_euphoria_star(pixels: _PixelGrid, primary: _Color, secondary: _Color, accent: _Color, rng: random.Random) -> None:
    _draw_line(pixels, 12, 5, 12, 19, primary)
    _draw_line(pixels, 5, 12, 19, 12, primary)
    _draw_line(pixels, 7, 7, 17, 17, secondary)
    _draw_line(pixels, 17, 7, 7, 17, secondary)
    _draw_circle_fill(pixels, 12, 12, 2, accent)
    _sprinkles(pixels, rng, secondary, 6)


def _draw_motif_glitch_chip(pixels: _PixelGrid, primary: _Color, secondary: _Color, accent: _Color, _rng: random.Random) -> None:
    _draw_rect(pixels, 7, 7, 10, 10, primary)
    _draw_rect_outline(pixels, 7, 7, 10, 10, secondary)
    _draw_rect(pixels, 10, 10, 6, 4, accent)
    _draw_rect(pixels, 5, 9, 3, 2, secondary)
    _draw_rect(pixels, 16, 13, 3, 2, secondary)
    _draw_rect(pixels, 9, 5, 2, 3, secondary)
    _draw_rect(pixels, 13, 16, 2, 3, secondary)


def _draw_motif_spectrum_wheel(pixels: _PixelGrid, primary: _Color, secondary: _Color, accent: _Color, _rng: random.Random) -> None:
    wheel_colors = [
        ZX_GREEN_BRIGHT,
        ZX_BLUE_BRIGHT,
        ZX_MAGENTA_BRIGHT,
        ZX_YELLOW,
        ZX_RED_BRIGHT,
        ZX_BROWN,
        ZX_GRAY_LIGHT,
        ZX_WHITE,
    ]
    for i, color in enumerate(wheel_colors):
        angle = i * 45
        dx = 6 if angle in (0, 180) else 4
        dy = 6 if angle in (90, 270) else 4
        x = 12 + (dx if angle < 180 else -dx)
        y = 12 + (dy if 0 < angle < 180 else -dy)
        _draw_circle_fill(pixels, x, y, 2, color)
    _draw_circle_fill(pixels, 12, 12, 3, primary)
    _draw_circle_fill(pixels, 12, 12, 1, accent)
    _draw_rect_outline(pixels, 5, 5, 14, 14, secondary)


def _draw_motif_beast_tamer(pixels: _PixelGrid, primary: _Color, secondary: _Color, accent: _Color, _rng: random.Random) -> None:
    # "domador": paleta + lazo/cadena
    _draw_rect(pixels, 6, 6, 3, 12, primary)
    _draw_rect(pixels, 9, 10, 7, 3, secondary)
    _draw_circle_fill(pixels, 17, 12, 3, accent)
    _draw_circle_fill(pixels, 17, 12, 1, ZX_BLACK)
    _draw_line(pixels, 9, 11, 14, 11, secondary)


def _draw_motif_night_moon(pixels: _PixelGrid, primary: _Color, secondary: _Color, accent: _Color, rng: random.Random) -> None:
    _draw_circle_fill(pixels, 12, 12, 6, primary)
    _draw_circle_fill(pixels, 14, 10, 5, ZX_BLACK)
    _sprinkles(pixels, rng, secondary, 4)
    _draw_circle_fill(pixels, 6, 6, 1, accent)


def _draw_motif_mystery(pixels: _PixelGrid, primary: _Color, secondary: _Color, accent: _Color, _rng: random.Random) -> None:
    _draw_rect_outline(pixels, 6, 5, 12, 14, primary)
    _draw_line(pixels, 9, 9, 12, 7, secondary)
    _draw_line(pixels, 12, 7, 15, 9, secondary)
    _draw_line(pixels, 15, 9, 12, 12, secondary)
    _draw_line(pixels, 12, 12, 12, 14, secondary)
    _draw_circle_fill(pixels, 12, 17, 1, accent)


_MOTIF_DRAWERS = {
    MOTIF_CASSETTE: _draw_motif_cassette,
    MOTIF_PADDLE_TROPHY: _draw_motif_paddle_trophy,
    MOTIF_SCORE_CHIP: _draw_motif_score_chip,
    MOTIF_RALLY_WAVE: _draw_motif_rally_wave,
    MOTIF_STREAK_CHAIN: _draw_motif_streak_chain,
    MOTIF_PERFECT_SEAL: _draw_motif_perfect_seal,
    MOTIF_SPEED_COMET: _draw_motif_speed_comet,
    MOTIF_42_SPIRAL: _draw_motif_42_spiral,
    MOTIF_DIALOG_BUBBLE: _draw_motif_dialog_bubble,
    MOTIF_BROKEN_HELMET: _draw_motif_broken_helmet,
    MOTIF_MONO_CRT: _draw_motif_mono_crt,
    MOTIF_FURY_CLAW: _draw_motif_fury_claw,
    MOTIF_SAD_DROP: _draw_motif_sad_drop,
    MOTIF_EUPHORIA_STAR: _draw_motif_euphoria_star,
    MOTIF_GLITCH_CHIP: _draw_motif_glitch_chip,
    MOTIF_SPECTRUM_WHEEL: _draw_motif_spectrum_wheel,
    MOTIF_BEAST_TAMER: _draw_motif_beast_tamer,
    MOTIF_NIGHT_MOON: _draw_motif_night_moon,
    "mystery": _draw_motif_mystery,
}


# ---------------------------------------------------------------------------
# Validacion / normalizacion de paleta y atributos 8x8
# ---------------------------------------------------------------------------


def _enforce_palette(pixels: list[list[tuple[int, int, int]]], palette: list[tuple[int, int, int]]) -> list[list[tuple[int, int, int]]]:
    out = []
    for row in pixels:
        out_row = []
        for color in row:
            out_row.append(_nearest_color(color, palette))
        out.append(out_row)
    return out


def _enforce_attribute_blocks(pixels: list[list[tuple[int, int, int]]]) -> list[list[tuple[int, int, int]]]:
    """Impone maximo de 2 colores por cada bloque de 8x8."""
    out = [row[:] for row in pixels]

    for by in range(0, ICON_SIZE, BLOCK_SIZE):
        for bx in range(0, ICON_SIZE, BLOCK_SIZE):
            counts: dict[tuple[int, int, int], int] = {}
            for yy in range(by, by + BLOCK_SIZE):
                for xx in range(bx, bx + BLOCK_SIZE):
                    c = out[yy][xx]
                    counts[c] = counts.get(c, 0) + 1

            if len(counts) <= 2:
                continue

            kept = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:2]
            allowed = [kept[0][0], kept[1][0]]

            for yy in range(by, by + BLOCK_SIZE):
                for xx in range(bx, bx + BLOCK_SIZE):
                    c = out[yy][xx]
                    if c not in allowed:
                        out[yy][xx] = _nearest_color(c, allowed)

    return out


def _nearest_color(color: tuple[int, int, int], candidates: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    best = candidates[0]
    best_dist = _rgb_dist_sq(color, best)
    for cand in candidates[1:]:
        dist = _rgb_dist_sq(color, cand)
        if dist < best_dist:
            best_dist = dist
            best = cand
    return best


def _rgb_dist_sq(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    return (
        (a[0] - b[0]) * (a[0] - b[0])
        + (a[1] - b[1]) * (a[1] - b[1])
        + (a[2] - b[2]) * (a[2] - b[2])
    )
