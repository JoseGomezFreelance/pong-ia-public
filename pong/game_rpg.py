"""
pong/game_rpg.py -- Mixin RPG para el Game.

Integra el motor RPG en el bucle de juego: tick de XP, aplicacion
de modificadores de habilidades, hooks de colision y multi-ball.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Any

from pong.config.gameplay import PADDLE_HEIGHT, PADDLE_SPEED
from pong.rpg_engine import RPGState
from pong.save_manager import load_history

if TYPE_CHECKING:
    from pong.entities import Ball, Paddle
    from pong.game_state import MatchState, UIState
    from pong.renderer import Renderer


class GameRPGMixin:
    """Mixin: sistema RPG integrado en el game loop."""

    # -- Atributos de Game visibles aquí --
    match: MatchState
    ui: UIState
    player: Paddle
    computer: Paddle
    ball: Ball
    renderer: Renderer
    game_start_time: float

    def _log(self, category: str, message: str) -> None:
        raise NotImplementedError

    def _init_rpg(self) -> None:
        """Inicializa el estado RPG desde el historial persistente."""
        history = load_history()
        rpg_data = history.get("rpg", {})
        self.rpg: RPGState = RPGState.from_dict(rpg_data)

        # Comprobar si la fase RPG ya esta desbloqueada
        if "rpg" in history.get("phases_unlocked", {}):
            self.rpg.rpg_unlocked = True

        # Estado de habilidades de gameplay
        self._rpg_double_impulse_active: bool = False
        self._rpg_curve_active: bool = False
        self._rpg_curve_timer: float = 0.0
        self._rpg_extra_balls: list[Any] = []  # Ball instances
        self._rpg_player_prev_y: int = 0

        # Aplicar modificadores iniciales
        self._rpg_apply_modifiers()

    def _rpg_apply_modifiers(self) -> None:
        """Aplica los modificadores de habilidades RPG a las entidades."""
        if not self.rpg.rpg_unlocked:
            return

        # Pala ampliada + pala de legado
        height_bonus = self.rpg.get_paddle_height_bonus()
        base_height = PADDLE_HEIGHT
        new_height = base_height + height_bonus
        try:
            if self.player.rect.height != new_height:
                old_center = self.player.rect.centery
                self.player.rect.height = new_height
                self.player.rect.centery = old_center
        except AttributeError:
            pass  # Stub en tests headless

        # Reaccion veloz + reflejo superior
        speed_bonus = self.rpg.get_paddle_speed_bonus()
        if hasattr(self.player, 'speed'):
            self.player.speed = PADDLE_SPEED + speed_bonus

    def _rpg_update(self, dt: float) -> None:
        """Llamar cada frame durante gameplay (no en pausa ni end screen)."""
        if not self.rpg.rpg_unlocked:
            return

        # Guardar posicion anterior del jugador para control direccional
        self._rpg_player_prev_y = self.player.rect.centery

        # Tick XP (cada segundo de juego)
        levels_gained = self.rpg.tick_xp(dt)
        if levels_gained > 0:
            self._log("RPG", f"Subida de nivel! Ahora nivel {self.rpg.level}")

        # Actualizar curva (disparo curvo)
        if self._rpg_curve_active and self._rpg_curve_timer > 0:
            curve_strength = self.rpg.get_curve_strength()
            # Aplicar drift sinusoidal
            elapsed_curve = 2.0 - self._rpg_curve_timer
            drift = math.sin(elapsed_curve * 3.0) * 0.3 * curve_strength
            self.ball.speed_y = int(self.ball.speed_y + drift)
            self._rpg_curve_timer -= dt
            if self._rpg_curve_timer <= 0:
                self._rpg_curve_active = False

        # Actualizar bolas extra (dual instinct)
        self._rpg_update_extra_balls(dt)

    def _rpg_on_player_collision(self) -> None:
        """Hook tras colision de la pelota con la pala del jugador."""
        if not self.rpg.rpg_unlocked:
            return

        # Efecto/spin
        spin = self.rpg.get_spin_strength()
        if spin > 0:
            # El spin depende de donde golpea la pala
            relative_hit = (
                (self.ball.rect.centery - self.player.rect.centery)
                / (self.player.rect.height / 2)
            )
            self.ball.speed_y = int(self.ball.speed_y + relative_hit * spin * 1.5)

        # Control direccional
        if self.rpg.has_directional_control():
            dy = self.player.rect.centery - self._rpg_player_prev_y
            self.ball.speed_y = int(self.ball.speed_y + dy * 0.3)

        # Golpe tenso
        speed_mult = self.rpg.get_ball_speed_multiplier()
        if speed_mult > 1.0:
            self.ball.speed_x = int(self.ball.speed_x * speed_mult)

        # Reflejo automatico (borde de la pala)
        if self.rpg.has_auto_reflex():
            relative_hit = abs(
                (self.ball.rect.centery - self.player.rect.centery)
                / (self.player.rect.height / 2)
            )
            if relative_hit > 0.8:
                self.ball.speed_x = int(self.ball.speed_x * 1.2)

        # Golpe critico
        crit_chance = self.rpg.get_critical_hit_chance()
        if crit_chance > 0 and random.random() < crit_chance:
            self.ball.speed_x = int(self.ball.speed_x * self.rpg.get_critical_hit_multiplier())
            self._log("RPG", "Golpe critico!")

        # Doble impulso (activado tras anotar punto)
        if self._rpg_double_impulse_active:
            self.ball.speed_x = int(self.ball.speed_x * 1.3)
            self._rpg_double_impulse_active = False

        # Efecto maestro (amplifica todo) — ya aplicado via get_spin_strength
        # y get_curve_strength (usan get_ascension_level internamente)

        # Disparo curvo (activar timer)
        if self.rpg.has_curved_shot():
            self._rpg_curve_active = True
            self._rpg_curve_timer = 2.0

        # Dual instinct (probabilidad de duplicar)
        chance = self.rpg.get_dual_instinct_chance()
        if chance > 0 and random.random() < chance:
            self._rpg_spawn_extra_ball()

    def _rpg_on_point_scored(self, winner: str) -> None:
        """Hook cuando se anota un punto."""
        if not self.rpg.rpg_unlocked:
            return

        if winner == "player":
            # Doble impulso: activar para el siguiente golpe
            if self.rpg.has_double_impulse():
                self._rpg_double_impulse_active = True

            # Puntos de ascension (cada punto vs ordenador)
            self.rpg.add_ascension_points(1)

            # XP bonus al anotar
            xp_bonus = self.rpg.get_point_scored_xp_bonus()
            if xp_bonus > 0:
                self.rpg.total_xp_seconds += xp_bonus
                self.rpg.skill_seconds_balance += xp_bonus

            # Segundos de habilidad bonus al anotar
            seconds_bonus = self.rpg.get_point_scored_seconds_bonus()
            if seconds_bonus > 0:
                self.rpg.skill_seconds_balance += seconds_bonus

        # Limpiar bolas extra al anotar
        self._rpg_extra_balls.clear()

    def _rpg_get_ai_error(self) -> float:
        """Devuelve el offset de error de la IA (habilidad hacker)."""
        if not self.rpg.rpg_unlocked:
            return 0.0
        error_rate = self.rpg.get_ai_error_rate()
        if error_rate > 0 and random.random() < error_rate:
            min_off, max_off = self.rpg.get_ai_error_offset()
            return random.uniform(min_off, max_off) * random.choice([-1, 1])
        return 0.0

    # --- Multi-ball (dual instinct) ---

    def _rpg_spawn_extra_ball(self) -> None:
        """Crea una bola extra en la posicion actual."""
        from pong.entities import Ball
        extra = Ball()
        # Posicionar en la posicion actual de la pelota principal
        extra.rect.x = self.ball.rect.x
        extra.rect.y = self.ball.rect.y
        # Velocidad similar pero con angulo diferente
        extra.speed_x = self.ball.speed_x
        extra.speed_y = int(self.ball.speed_y + random.uniform(-3, 3))
        self._rpg_extra_balls.append(extra)
        self._log("RPG", f"Pelota duplicada! ({len(self._rpg_extra_balls)} extra)")

    def _rpg_update_extra_balls(self, dt: float) -> None:
        """Actualiza bolas extra y detecta sus colisiones."""
        if not self._rpg_extra_balls:
            return

        from pong.config.layout import WINDOW_WIDTH

        to_remove = []
        for i, eb in enumerate(self._rpg_extra_balls):
            eb.update(self._speed_mult if hasattr(self, '_speed_mult') else 1.0)

            # Colisiones con paletas
            if eb.check_paddle_collision(self.player):
                pass  # Solo rebota
            elif eb.check_paddle_collision(self.computer):
                pass  # Solo rebota

            # Si sale del campo, registrar punto y eliminar
            if eb.rect.left <= 0:
                to_remove.append(i)
            elif eb.rect.right >= WINDOW_WIDTH:
                to_remove.append(i)

        for i in sorted(to_remove, reverse=True):
            self._rpg_extra_balls.pop(i)

    def _rpg_get_save_data(self) -> dict[str, Any]:
        """Devuelve el estado RPG serializado para persistencia."""
        return self.rpg.to_dict()

    def _rpg_persist_now(self) -> None:
        """Persiste el estado RPG a disco inmediatamente."""
        from pong.save_manager import load_history, _write_history
        history = load_history()
        history["rpg"] = self.rpg.to_dict()
        _write_history(history)
