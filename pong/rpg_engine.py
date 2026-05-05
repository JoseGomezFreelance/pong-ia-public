"""
Motor del sistema RPG: niveles, habilidades y ascension.

Gestiona el estado RPG del jugador (XP, nivel, habilidades compradas,
puntos de ascension) y expone metodos para consultar modificadores
de gameplay activos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pong.config.rpg import (
    ASCENSION_MIN_POINTS,
    ASCENSION_SKILL_MAX_LEVEL,
    RPG_ASCENSION_SKILLS,
    RPG_LEVEL_XP_TABLE,
    RPG_MAX_LEVEL,
    RPG_SKILLS,
)


@dataclass
class RPGState:
    """Estado persistente del sistema RPG."""

    rpg_unlocked: bool = False
    level: int = 1
    total_xp_seconds: float = 0.0
    skill_seconds_balance: float = 0.0
    purchased_skills: list[str] = field(default_factory=list)
    ascension_count: int = 0
    ascension_points_total: int = 0
    ascension_points_available: int = 0
    purchased_ascension_skills: dict[str, int] = field(default_factory=dict)

    # --- Persistencia ---

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RPGState:
        """Carga el estado RPG desde un dict (game_history.json)."""
        # Migrar formato antiguo (list) a nuevo (dict con niveles)
        raw_asc = data.get("purchased_ascension_skills", {})
        if isinstance(raw_asc, list):
            raw_asc = {sid: 1 for sid in raw_asc}
        return cls(
            rpg_unlocked=data.get("rpg_unlocked", False),
            level=data.get("level", 1),
            total_xp_seconds=data.get("total_xp_seconds", 0.0),
            skill_seconds_balance=data.get("skill_seconds_balance", 0.0),
            purchased_skills=list(data.get("purchased_skills", [])),
            ascension_count=data.get("ascension_count", 0),
            ascension_points_total=data.get("ascension_points_total", 0),
            ascension_points_available=data.get("ascension_points_available", 0),
            purchased_ascension_skills=dict(raw_asc),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serializa el estado RPG para persistencia."""
        return {
            "rpg_unlocked": self.rpg_unlocked,
            "level": self.level,
            "total_xp_seconds": round(self.total_xp_seconds, 2),
            "skill_seconds_balance": round(self.skill_seconds_balance, 2),
            "purchased_skills": list(self.purchased_skills),
            "ascension_count": self.ascension_count,
            "ascension_points_total": self.ascension_points_total,
            "ascension_points_available": self.ascension_points_available,
            "purchased_ascension_skills": dict(self.purchased_ascension_skills),
        }

    # --- XP y niveles ---

    def get_ascension_level(self, skill_id: str) -> int:
        """Devuelve el nivel actual de una habilidad de ascension (0 si no comprada)."""
        return self.purchased_ascension_skills.get(skill_id, 0)

    def get_xp_multiplier(self) -> float:
        """Multiplicador total de XP (habilidades normales + ascension)."""
        mult = 1.0
        if "xp_bonus" in self.purchased_skills:
            mult *= 1.5
        lvl = self.get_ascension_level("veteran_start")
        if lvl > 0:
            mult *= 1.0 + 0.1 * lvl
        return mult

    def tick_xp(self, dt: float) -> int:
        """
        Acumula XP por tiempo de juego.

        Args:
            dt: Segundos transcurridos desde el ultimo frame.

        Returns:
            Numero de niveles ganados en este tick (0 o mas).
        """
        effective_dt = dt * self.get_xp_multiplier()
        self.total_xp_seconds += effective_dt
        self.skill_seconds_balance += effective_dt

        old_level = self.level
        self._recalculate_level()
        return self.level - old_level

    def _recalculate_level(self) -> None:
        """Recalcula el nivel basado en la XP total acumulada."""
        for lvl in range(RPG_MAX_LEVEL, 0, -1):
            if self.total_xp_seconds >= RPG_LEVEL_XP_TABLE[lvl - 1]:
                self.level = lvl
                return
        self.level = 1

    def get_level_progress(self) -> tuple[int, float, float]:
        """
        Progreso del nivel actual.

        Returns:
            (nivel, xp_en_nivel_actual, xp_necesaria_para_siguiente).
            Si esta en nivel max, xp_necesaria = xp_en_nivel (barra llena).
        """
        if self.level >= RPG_MAX_LEVEL:
            xp_current_base = RPG_LEVEL_XP_TABLE[RPG_MAX_LEVEL - 1]
            return self.level, 1.0, 1.0

        xp_current_base = RPG_LEVEL_XP_TABLE[self.level - 1]
        xp_next_base = RPG_LEVEL_XP_TABLE[self.level]
        xp_in_level = self.total_xp_seconds - xp_current_base
        xp_needed = xp_next_base - xp_current_base
        return self.level, xp_in_level, xp_needed

    # --- Habilidades normales ---

    def _find_skill(self, skill_id: str) -> dict[str, object] | None:
        """Busca una habilidad normal por ID."""
        for skill in RPG_SKILLS:
            if skill["id"] == skill_id:
                return skill
        return None

    def is_skill_unlocked(self, skill_id: str) -> bool:
        """True si el nivel del jugador permite ver/comprar esta habilidad."""
        skill = self._find_skill(skill_id)
        if skill is None:
            return False
        return self.level >= skill["unlock_level"]  # type: ignore[operator]

    def can_buy_skill(self, skill_id: str) -> bool:
        """True si el jugador puede comprar esta habilidad ahora."""
        if skill_id in self.purchased_skills:
            return False
        skill = self._find_skill(skill_id)
        if skill is None:
            return False
        if not self.is_skill_unlocked(skill_id):
            return False
        return self.skill_seconds_balance >= skill["cost"]  # type: ignore[operator]

    def buy_skill(self, skill_id: str) -> bool:
        """Compra una habilidad. Devuelve True si se compro correctamente."""
        if not self.can_buy_skill(skill_id):
            return False
        skill = self._find_skill(skill_id)
        assert skill is not None
        self.skill_seconds_balance -= skill["cost"]  # type: ignore[operator]
        self.purchased_skills.append(skill_id)
        return True

    def is_skill_active(self, skill_id: str) -> bool:
        """True si la habilidad esta comprada y activa."""
        return skill_id in self.purchased_skills

    # --- Habilidades de ascension ---

    def _find_ascension_skill(self, skill_id: str) -> dict[str, object] | None:
        """Busca una habilidad de ascension por ID."""
        for skill in RPG_ASCENSION_SKILLS:
            if skill["id"] == skill_id:
                return skill
        return None

    def get_ascension_skill_cost(self, skill_id: str) -> int:
        """Coste para el siguiente nivel de una habilidad de ascension."""
        skill = self._find_ascension_skill(skill_id)
        if skill is None:
            return 999
        base_cost: int = skill["base_cost"]  # type: ignore[assignment]
        next_level = self.get_ascension_level(skill_id) + 1
        return base_cost * next_level

    def can_buy_ascension_skill(self, skill_id: str) -> bool:
        """True si se puede comprar/mejorar esta habilidad de ascension."""
        skill = self._find_ascension_skill(skill_id)
        if skill is None:
            return False
        current = self.get_ascension_level(skill_id)
        max_lvl: int = skill.get("max_level", ASCENSION_SKILL_MAX_LEVEL)  # type: ignore[assignment]
        if current >= max_lvl:
            return False
        cost = self.get_ascension_skill_cost(skill_id)
        return self.ascension_points_available >= cost

    def buy_ascension_skill(self, skill_id: str) -> bool:
        """Compra/mejora una habilidad de ascension."""
        if not self.can_buy_ascension_skill(skill_id):
            return False
        cost = self.get_ascension_skill_cost(skill_id)
        self.ascension_points_available -= cost
        current = self.get_ascension_level(skill_id)
        self.purchased_ascension_skills[skill_id] = current + 1
        return True

    # --- Ascension ---

    def can_ascend(self) -> bool:
        """True si el jugador cumple los requisitos para ascender."""
        return (
            self.rpg_unlocked
            and self.ascension_points_total >= ASCENSION_MIN_POINTS
        )

    def perform_ascension(self) -> None:
        """
        Ejecuta la ascension: resetea nivel/XP/habilidades normales,
        otorga 1 AP extra y aplica sovereign si esta activo.
        """
        # Bonificacion sovereign: conservar parte del progreso
        sov_lvl = self.get_ascension_level("sovereign")
        keep_xp_ratio = 0.05 * sov_lvl  # 0% sin sovereign, 5% por nivel
        keep_seconds_ratio = 0.08 * sov_lvl  # 0% sin sovereign, 8% por nivel

        self.level = 1
        self.total_xp_seconds = self.total_xp_seconds * keep_xp_ratio
        self.skill_seconds_balance = self.skill_seconds_balance * keep_seconds_ratio
        self.purchased_skills.clear()
        self.ascension_count += 1
        self.ascension_points_available += 1

        self._recalculate_level()

    def add_ascension_points(self, points: int) -> None:
        """Anade puntos de ascension (al anotar puntos vs ordenador)."""
        self.ascension_points_total += points
        self.ascension_points_available += points

    # --- Modificadores de gameplay ---

    def get_paddle_height_bonus(self) -> int:
        """Bonus de altura de pala (pixeles)."""
        bonus = 0
        if "wider_paddle" in self.purchased_skills:
            bonus += 12
        bonus += 8 * self.get_ascension_level("legacy_paddle")
        return bonus

    def get_paddle_speed_bonus(self) -> int:
        """Bonus de velocidad de pala (pixeles/frame)."""
        bonus = 0
        if "fast_reaction" in self.purchased_skills:
            bonus += 2
        bonus += 1 * self.get_ascension_level("superior_reflex")
        return bonus

    def get_ball_speed_multiplier(self) -> float:
        """Multiplicador de velocidad de pelota tras golpe del jugador."""
        mult = 1.0
        if "tense_shot" in self.purchased_skills:
            mult *= 1.25
        return mult

    def get_spin_strength(self) -> float:
        """Fuerza del efecto/spin (0.0 = sin efecto)."""
        if "spin" not in self.purchased_skills:
            return 0.0
        strength = 1.0
        ms_lvl = self.get_ascension_level("master_spin")
        if ms_lvl > 0:
            strength *= 1.0 + 0.2 * ms_lvl
        return strength

    def has_directional_control(self) -> bool:
        return "directional" in self.purchased_skills

    def has_auto_reflex(self) -> bool:
        return "auto_reflex" in self.purchased_skills

    def has_curved_shot(self) -> bool:
        return "curved_shot" in self.purchased_skills

    def get_curve_strength(self) -> float:
        """Fuerza de la curva (0.0 = sin curva)."""
        if not self.has_curved_shot():
            return 0.0
        strength = 1.0
        ms_lvl = self.get_ascension_level("master_spin")
        if ms_lvl > 0:
            strength *= 1.0 + 0.2 * ms_lvl
        return strength

    def has_double_impulse(self) -> bool:
        return "double_impulse" in self.purchased_skills

    def has_dual_instinct(self) -> bool:
        return "dual_instinct" in self.purchased_skills

    def has_trajectory_prediction(self) -> bool:
        return self.get_ascension_level("rival_reading") > 0

    def get_trajectory_distance(self) -> float:
        """Distancia de prediccion de trayectoria en pixeles."""
        return 40.0 * self.get_ascension_level("rival_reading")

    def get_ai_error_rate(self) -> float:
        """Probabilidad de error de la IA por frame (0.0 a 1.0)."""
        lvl = self.get_ascension_level("hacker")
        if lvl > 0:
            return 0.10 + 0.03 * lvl
        return 0.0

    def get_ai_error_offset(self) -> tuple[int, int]:
        """Rango de offset de error de la IA (min, max pixeles)."""
        lvl = self.get_ascension_level("hacker")
        if lvl > 0:
            return (5, 10 + 3 * lvl)
        return (0, 0)

    def get_critical_hit_chance(self) -> float:
        """Probabilidad de golpe critico (0.0 a 1.0)."""
        lvl = self.get_ascension_level("critical_hit")
        if lvl > 0:
            return 0.10 + 0.03 * lvl
        return 0.0

    def get_critical_hit_multiplier(self) -> float:
        """Multiplicador de velocidad en golpe critico."""
        lvl = self.get_ascension_level("critical_hit")
        return 1.5 + 0.1 * max(lvl, 1)

    def get_point_scored_xp_bonus(self) -> float:
        """Segundos de XP bonus al anotar un punto."""
        return 3.0 * self.get_ascension_level("persistent_memory")

    def get_point_scored_seconds_bonus(self) -> float:
        """Segundos de habilidad bonus al anotar un punto."""
        return 5.0 * self.get_ascension_level("victory_echo")

    def get_dual_instinct_chance(self) -> float:
        """Probabilidad de duplicar pelota al golpear."""
        if self.has_dual_instinct():
            return 0.15
        return 0.0
