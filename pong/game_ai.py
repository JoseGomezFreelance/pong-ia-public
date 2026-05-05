"""
pong/game_ai.py -- Mixin con la lógica de IA del ordenador.

Extraído de game.py para reducir su tamaño. La clase Game hereda
de GameAIMixin para obtener estos métodos.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from pong.config.gameplay import (
    AI_RALLY_PRESS_STEP,
    AI_RALLY_PRESS_THRESHOLD,
    AI_REACTION_ZONE,
    AI_SPEED,
    AI_SPEED_MAX,
    AI_SPEED_MIN,
    PADDLE_HEIGHT,
    PLAYER_IDLE_VARIANCE_THRESHOLD,
    RALLY_IDLE_RAMP,
    RALLY_IDLE_THRESHOLD,
)
from pong.config.layout import GAME_AREA_HEIGHT
from pong.config.layout import WINDOW_WIDTH

if TYPE_CHECKING:
    from pong.emotional_state import EmotionalState
    from pong.entities import Ball, Paddle
    from pong.game_state import MatchState
    from pong.question_system import QuestionSystem


class GameAIMixin:
    """Métodos de IA del ordenador, usados por Game vía herencia."""

    # -- Atributos declarados en Game, visibles aquí para mypy --
    _player_positions: list[int]
    _player_idle_score: float
    match: MatchState
    questions: QuestionSystem
    emotional_target: EmotionalState
    emotional_state: EmotionalState
    emotion_active: bool
    ball: Ball
    computer: Paddle
    computer_home_x: int

    def _log(self, category: str, message: str) -> None:
        raise NotImplementedError  # Provided by Game

    # --------------------------------------------------------
    # Detección de inactividad del jugador
    # --------------------------------------------------------

    def _compute_idle_score(self) -> float:
        """Calcula cuánto está quieto el jugador (0.0=activo, 1.0=estático)."""
        if len(self._player_positions) < 8:
            return 0.0
        positions = self._player_positions
        mean_y = sum(positions) / len(positions)
        variance = sum((p - mean_y) ** 2 for p in positions) / len(positions)
        if variance < PLAYER_IDLE_VARIANCE_THRESHOLD:
            return 1.0
        elif variance < PLAYER_IDLE_VARIANCE_THRESHOLD * 4:
            return 1.0 - (
                (variance - PLAYER_IDLE_VARIANCE_THRESHOLD)
                / (PLAYER_IDLE_VARIANCE_THRESHOLD * 3)
            )
        return 0.0

    def _apply_autonomous_emotion(self) -> None:
        """Ajusta la emoción autónomamente ante inactividad o exploit."""
        idle_score = self._compute_idle_score()
        self._player_idle_score = idle_score
        rally = self.match.rally_hits

        # Monotonía de respuestas (todas iguales: Duda, Sí o No)
        recent_answers = [e.answer for e in self.questions.dialogue_history[-3:]]
        monotone = len(recent_answers) >= 2 and len(set(recent_answers)) == 1

        # Urgencia: sube con rally largo + jugador inactivo
        rally_factor = 0.0
        if rally > RALLY_IDLE_THRESHOLD:
            rally_factor = min(
                1.0, (rally - RALLY_IDLE_THRESHOLD) / RALLY_IDLE_RAMP
            )
        urgency = idle_score * rally_factor

        # Bonus si las respuestas son monótone
        if monotone and rally > RALLY_IDLE_THRESHOLD:
            urgency = min(1.0, urgency + 0.3)

        if urgency <= 0.05:
            return

        # Subir agresividad y bajar estabilidad para romper el rally
        min_aggr = 0.5 + urgency * 0.5
        min_stab = max(0.3, 1.0 - urgency * 0.5)

        if self.emotional_target.aggressiveness < min_aggr:
            self.emotional_target.aggressiveness = min_aggr
        if self.emotional_target.stability > min_stab:
            self.emotional_target.stability = min_stab

        if urgency > 0.7:
            self.emotional_target.mood_tag = "irritado"
        elif urgency > 0.3:
            self.emotional_target.mood_tag = "aburrido"

        if not self.emotion_active:
            self.emotion_active = True

        # Log periódico (cada 20 golpes)
        if rally > 0 and rally % 20 == 0:
            self._log(
                "EMOCION",
                f"Auto-ajuste: urgency={urgency:.2f} idle={idle_score:.2f} "
                f"rally={rally} agr={self.emotional_target.aggressiveness:.2f}",
            )

    # --------------------------------------------------------
    # IA del ordenador
    # --------------------------------------------------------

    def update_ai(self, speed_multiplier: float = 1.0) -> None:
        """
        Mueve la paleta del ordenador con comportamiento modulado por emoción.

        Durante los primeros 30 s (antes de la primera pregunta) se usa la
        estrategia clásica: seguir la pelota cuando se acerca, volver al
        centro cuando se aleja, a AI_SPEED fijo.

        Tras la primera pregunta, el perfil emocional del LLM modula:
        - **Agresividad**: velocidad (AI_SPEED_MIN..AI_SPEED_MAX), predicción
          de la trayectoria y golpes con el canto de la paleta.
        - **Estabilidad**: jitter aleatorio en el target (0 = errático).
        - **Motivación**: mezcla entre seguir la pelota y quedarse quieta
          (0 = rendida).

        Args:
            speed_multiplier: Multiplicador de velocidad (1.0 = normal,
                              <1.0 = bullet time).
        """
        post_200_hits = max(0, self.match.rally_hits - AI_RALLY_PRESS_THRESHOLD)
        self.computer.rect.x = max(
            WINDOW_WIDTH // 2,
            self.computer_home_x - post_200_hits * AI_RALLY_PRESS_STEP,
        )

        # --- 1. Target base (igual que siempre) ---
        if self.ball.speed_x > 0:
            target_y = self.ball.rect.centery
        else:
            target_y = GAME_AREA_HEIGHT // 2

        # Sin emoción activa, usar comportamiento clásico
        if not self.emotion_active:
            self.computer.move_toward(target_y, AI_SPEED, speed_multiplier)
            return

        emo = self.emotional_state

        # --- 2. Predicción de trayectoria (agresividad > 0.6) ---
        if emo.aggressiveness > 0.6 and self.ball.speed_x > 0:
            effective_speed_x = self.ball.get_effective_speed_x(speed_multiplier)
            effective_speed_y = self.ball.get_effective_speed_y(speed_multiplier)
            frames_to_reach = abs(
                (self.computer.rect.centerx - self.ball.rect.centerx)
                / max(abs(effective_speed_x), 1.0)
            )
            predicted_y = self.ball.rect.centery + effective_speed_y * frames_to_reach
            predicted_y = max(0, min(GAME_AREA_HEIGHT, predicted_y))
            blend = (emo.aggressiveness - 0.6) / 0.4
            target_y = int(target_y + (predicted_y - target_y) * blend)

        # --- 3. Golpe con el canto (agresividad > 0.7) ---
        if emo.aggressiveness > 0.7 and self.ball.speed_x > 0:
            edge_blend = (emo.aggressiveness - 0.7) / 0.3
            offset = PADDLE_HEIGHT * 0.35 * edge_blend
            if abs(self.ball.speed_y) < 1.0:
                # Pelota casi recta (exploit): alternar dirección cada golpe
                offset *= 1 if self.match.rally_hits % 2 == 0 else -1
            elif self.ball.speed_y > 0:
                pass  # offset positivo (golpear con borde inferior)
            else:
                offset = -offset
            target_y = int(target_y + offset)

        # --- 4. Erraticidad (estabilidad < 0.5) ---
        if emo.stability < 0.5:
            jitter_amplitude = (0.5 - emo.stability) * 100
            target_y = int(target_y + random.gauss(0, jitter_amplitude))

        # --- 5. Motivación (0 = no moverse, 1 = seguir pelota al 100%) ---
        current_y = self.computer.rect.centery
        target_y = int(current_y + (target_y - current_y) * emo.motivation)

        # --- 6. Velocidad modulada por agresividad ---
        ai_speed = AI_SPEED_MIN + (AI_SPEED_MAX - AI_SPEED_MIN) * emo.aggressiveness

        # --- 7. Clamping y movimiento ---
        target_y = max(0, min(GAME_AREA_HEIGHT, target_y))
        self.computer.move_toward(target_y, int(ai_speed), speed_multiplier)
