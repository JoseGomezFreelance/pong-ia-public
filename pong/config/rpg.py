"""Configuracion del sistema RPG: niveles, habilidades y ascension."""

from __future__ import annotations

__all__ = [
    "RPG_UNLOCK_TOTAL_SECONDS",
    "RPG_LEVEL_XP_TABLE",
    "RPG_MAX_LEVEL",
    "RPG_SKILLS",
    "RPG_ASCENSION_SKILLS",
    "ASCENSION_MIN_POINTS",
    "ASCENSION_SKILL_MAX_LEVEL",
    "XP_BAR_HEIGHT",
    "XP_BAR_COLOR",
    "XP_BAR_BG_COLOR",
    "XP_BAR_BORDER_COLOR",
    "XP_LEVEL_COLOR",
    "XP_TEXT_FONT_SIZE",
]


# ============================================================
# DESBLOQUEO DE FASE RPG
# ============================================================
RPG_UNLOCK_TOTAL_SECONDS = 600  # 10 minutos de juego acumulado


# ============================================================
# TABLA DE NIVELES (50 niveles, curva cuadratica clasica)
# ============================================================
# Formula: xp(n) = round(5 * n^2 + 5 * n) donde n = nivel - 1
# XP se mide en segundos de juego contra el ordenador.
RPG_MAX_LEVEL = 50

RPG_LEVEL_XP_TABLE: tuple[int, ...] = tuple(
    round(5 * n * n + 5 * n) for n in range(RPG_MAX_LEVEL)
)
# Nivel  1:     0s  (inicio)
# Nivel  2:    10s
# Nivel  5:   100s  (~1.5 min)
# Nivel 10:   450s  (~7.5 min)
# Nivel 15:  1050s  (~17.5 min)
# Nivel 20:  1900s  (~31 min)
# Nivel 25:  3000s  (~50 min)
# Nivel 30:  4350s  (~72 min)
# Nivel 40:  7800s  (~130 min)
# Nivel 50: 12250s  (~204 min)


# ============================================================
# HABILIDADES RPG (10 normales)
# ============================================================
# Se desbloquean para compra al alcanzar el nivel indicado.
# Coste en "segundos de habilidad" (moneda acumulada con el juego).

RPG_SKILLS: list[dict[str, object]] = [
    {
        "id": "spin",
        "name": "Efecto en la pelota",
        "cost": 1,
        "unlock_level": 2,
        "description": "La pelota sale con efecto tras golpearla, "
                       "alterando ligeramente su trayectoria.",
    },
    {
        "id": "directional",
        "name": "Control direccional",
        "cost": 1,
        "unlock_level": 4,
        "description": "La direccion del rebote depende del movimiento "
                       "de la pala en el momento del impacto.",
    },
    {
        "id": "wider_paddle",
        "name": "Pala ampliada",
        "cost": 1,
        "unlock_level": 6,
        "description": "La pala del jugador aumenta ligeramente de tamano.",
    },
    {
        "id": "fast_reaction",
        "name": "Reaccion veloz",
        "cost": 2,
        "unlock_level": 9,
        "description": "Aumenta la velocidad de movimiento de la pala.",
    },
    {
        "id": "tense_shot",
        "name": "Golpe tenso",
        "cost": 2,
        "unlock_level": 12,
        "description": "Los golpes devuelven la pelota con mayor velocidad.",
    },
    {
        "id": "auto_reflex",
        "name": "Reflejo automatico",
        "cost": 2,
        "unlock_level": 16,
        "description": "Un impulso automatico al golpear cerca del borde "
                       "de la pala, devolviendo con mas velocidad.",
    },
    {
        "id": "xp_bonus",
        "name": "Bonificacion de experiencia",
        "cost": 2,
        "unlock_level": 20,
        "description": "Cada segundo de juego cuenta como 1.5 para la "
                       "progresion de nivel y compra de habilidades.",
    },
    {
        "id": "curved_shot",
        "name": "Disparo curvo",
        "cost": 3,
        "unlock_level": 25,
        "description": "Los golpes producen trayectorias curvas "
                       "(se suma al efecto en la pelota).",
    },
    {
        "id": "double_impulse",
        "name": "Doble impulso",
        "cost": 3,
        "unlock_level": 32,
        "description": "Tras anotar un punto, el siguiente golpe "
                       "genera un impulso adicional de velocidad.",
    },
    {
        "id": "dual_instinct",
        "name": "Instinto de combate dual",
        "cost": 5,
        "unlock_level": 40,
        "description": "Probabilidad de duplicar la pelota al golpear, "
                       "dificultando la defensa del ordenador.",
    },
]


# ============================================================
# HABILIDADES DE ASCENSION (10 permanentes, hasta 10 niveles)
# ============================================================
# Coste en puntos de ascension (AP = puntos anotados al ordenador).
# Cada habilidad se puede mejorar hasta max_level (10).
# Coste del nivel N: base_cost * N.

ASCENSION_MIN_POINTS = 10  # Puntos minimos para poder ascender
ASCENSION_SKILL_MAX_LEVEL = 10

RPG_ASCENSION_SKILLS: list[dict[str, object]] = [
    {
        "id": "veteran_start",
        "name": "Inicio veterano",
        "base_cost": 1,
        "max_level": 10,
        "description": "XP por segundo x{mult:.1f}.",
        "per_level": 0.1,  # mult = 1.0 + 0.1 * level
    },
    {
        "id": "persistent_memory",
        "name": "Memoria persistente",
        "base_cost": 1,
        "max_level": 10,
        "description": "+{val:.0f}s de XP bonus al anotar punto.",
        "per_level": 3.0,  # val = 3 * level
    },
    {
        "id": "legacy_paddle",
        "name": "Pala de legado",
        "base_cost": 2,
        "max_level": 10,
        "description": "+{val:.0f}px tamano de pala permanente.",
        "per_level": 8,  # val = 8 * level
    },
    {
        "id": "rival_reading",
        "name": "Lectura del rival",
        "base_cost": 2,
        "max_level": 10,
        "description": "Trayectoria visible ({val:.0f}px).",
        "per_level": 40.0,  # max_distance = 40 * level
    },
    {
        "id": "master_spin",
        "name": "Efecto maestro",
        "base_cost": 2,
        "max_level": 10,
        "description": "Efectos de pelota x{mult:.1f}.",
        "per_level": 0.2,  # mult = 1.0 + 0.2 * level
    },
    {
        "id": "superior_reflex",
        "name": "Reflejo superior",
        "base_cost": 3,
        "max_level": 10,
        "description": "+{val:.0f} velocidad maxima de pala.",
        "per_level": 1,  # val = 1 * level
    },
    {
        "id": "hacker",
        "name": "Hacker",
        "base_cost": 3,
        "max_level": 10,
        "description": "IA falla {pct:.0f}% ({val:.0f}-{val2:.0f}px).",
        "per_level_chance": 0.03,  # chance = 0.10 + 0.03 * level
        "per_level_offset": 3,  # offset_max = 10 + 3 * level
    },
    {
        "id": "critical_hit",
        "name": "Golpe critico",
        "base_cost": 3,
        "max_level": 10,
        "description": "{pct:.0f}% prob. de golpe a x{mult:.1f}.",
        "per_level_chance": 0.03,  # chance = 0.10 + 0.03 * level
        "per_level_mult": 0.1,  # mult = 1.5 + 0.1 * level
    },
    {
        "id": "victory_echo",
        "name": "Eco de victoria",
        "base_cost": 4,
        "max_level": 10,
        "description": "+{val:.0f}s de habilidad al anotar.",
        "per_level": 5.0,  # val = 5 * level
    },
    {
        "id": "sovereign",
        "name": "Ascension soberana",
        "base_cost": 5,
        "max_level": 10,
        "description": "Conservar {xp:.0f}% XP y {sec:.0f}% segundos.",
        "per_level_xp": 0.05,  # xp_ratio = 0.05 * level (5%..50%)
        "per_level_sec": 0.08,  # sec_ratio = 0.08 * level (8%..80%)
    },
]


# ============================================================
# BARRA DE XP (visual)
# ============================================================
XP_BAR_HEIGHT = 22
XP_BAR_COLOR = (85, 85, 255)       # ZX_BLUE_BRIGHT
XP_BAR_BG_COLOR = (20, 20, 60)     # Fondo oscuro azulado
XP_BAR_BORDER_COLOR = (85, 85, 85)  # ZX_GRAY_DARK
XP_LEVEL_COLOR = (85, 255, 85)     # ZX_GREEN_BRIGHT
XP_TEXT_FONT_SIZE = 18
