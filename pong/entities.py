"""
pong/entities.py -- Paleta y Pelota del juego.

Este modulo define las dos "entidades fisicas" del Pong:
- Paddle (paleta): el rectangulo que el jugador (o la IA) mueve arriba/abajo.
- Ball (pelota): el cuadrado que rebota en paredes y paletas.

Ambas clases usan las constantes definidas en pong/config.py para saber su
tamano, velocidad y los limites de la zona de juego.
"""

from __future__ import annotations

import random

import pygame

from pong.config.colors import COLOR_FOREGROUND
from pong.config.gameplay import (
    BALL_RALLY_MAX_SPEED_MULTIPLIER,
    BALL_RALLY_SPEEDUP_STEP,
    BALL_RALLY_SPEEDUP_THRESHOLD,
    BALL_SIZE,
    BALL_SPEED_X,
    BALL_SPEED_Y,
    PADDLE_HEIGHT,
    PADDLE_SPEED,
    PADDLE_WIDTH,
)
from pong.config.layout import GAME_AREA_HEIGHT, WINDOW_WIDTH


# ============================================================
# PALETA (Paddle)
# ============================================================

class Paddle:
    """
    Representa una paleta del juego.

    Una paleta es el rectangulo que el jugador (o el ordenador) mueve
    para golpear la pelota. Solo se mueve verticalmente (arriba/abajo)
    dentro de la zona de juego.

    Atributos:
        rect:  Rectangulo de pygame que define posicion y tamano.
        speed: Pixeles que se mueve por frame cuando el jugador pulsa una tecla.
    """

    def __init__(self, x: int, y: int) -> None:
        """
        Crea una paleta en la posicion (x, y).

        Args:
            x: Posicion horizontal (pixeles desde la izquierda).
            y: Posicion vertical (pixeles desde arriba de la zona de juego).
        """
        self.rect: pygame.Rect = pygame.Rect(x, y, PADDLE_WIDTH, PADDLE_HEIGHT)
        self.speed: int = PADDLE_SPEED
        self._frac_y: float = 0.0  # Acumulador fraccionario (modo agente)

    def move_up(self, speed_multiplier: float = 1.0) -> None:
        """
        Mueve la paleta hacia arriba.

        Resta 'speed' pixeles a la posicion vertical. Si la paleta se saldria
        de la pantalla por arriba, la fija en el borde superior (top = 0).
        """
        self._frac_y -= self.speed * speed_multiplier
        dy = int(self._frac_y)
        self._frac_y -= dy
        self.rect.y += dy
        if self.rect.top < 0:
            self.rect.top = 0

    def move_down(self, speed_multiplier: float = 1.0) -> None:
        """
        Mueve la paleta hacia abajo.

        Suma 'speed' pixeles a la posicion vertical. Si la paleta se saldria
        por debajo de la zona de juego, la fija en el borde inferior.
        """
        self._frac_y += self.speed * speed_multiplier
        dy = int(self._frac_y)
        self._frac_y -= dy
        self.rect.y += dy
        if self.rect.bottom > GAME_AREA_HEIGHT:
            self.rect.bottom = GAME_AREA_HEIGHT

    def move_toward(self, target_y: int, speed: int, speed_multiplier: float = 1.0) -> None:
        """
        Mueve la paleta hacia un objetivo (usado por la IA).

        La paleta se desplaza 'speed' pixeles hacia 'target_y'. Si ya esta
        suficientemente cerca (dentro de 'speed' pixeles), se queda quieta.

        Args:
            target_y:         Posicion vertical objetivo (centro de la pelota).
            speed:            Pixeles maximos a moverse por frame.
            speed_multiplier: Multiplicador de velocidad (1.0 = normal,
                              <1.0 = bullet time).
        """
        effective_speed = speed * speed_multiplier
        diff = target_y - self.rect.centery
        if abs(diff) > effective_speed:
            # Mover en la direccion del objetivo
            self._frac_y += effective_speed if diff > 0 else -effective_speed
            dy = int(self._frac_y)
            self._frac_y -= dy
            self.rect.y += dy
        # Mantener la paleta dentro de la zona de juego
        if self.rect.top < 0:
            self.rect.top = 0
        if self.rect.bottom > GAME_AREA_HEIGHT:
            self.rect.bottom = GAME_AREA_HEIGHT

    def draw(self, surface: pygame.Surface, y_offset: int = 0, color: tuple[int, int, int] | None = None) -> None:
        """
        Dibuja la paleta en la pantalla.

        Args:
            surface:  Superficie de pygame donde dibujar.
            y_offset: Desplazamiento vertical (para que la zona de juego
                      empiece debajo de la banda de marcador).
            color:    Color RGB opcional. Si es None, usa COLOR_FOREGROUND.
        """
        pygame.draw.rect(
            surface,
            color if color is not None else COLOR_FOREGROUND,
            self.rect.move(0, y_offset),
        )


# ============================================================
# PELOTA (Ball)
# ============================================================

class Ball:
    """
    Representa la pelota del juego.

    La pelota se mueve en diagonal rebotando en las paredes superior e
    inferior. Cuando sale por los lados izquierdo o derecho, alguien anota.

    Atributos:
        rect:    Rectangulo de pygame (posicion y tamano).
        speed_x: Velocidad horizontal (positiva = derecha, negativa = izquierda).
        speed_y: Velocidad vertical (positiva = abajo, negativa = arriba).
    """

    def __init__(self) -> None:
        """Crea la pelota en el centro de la zona de juego con direccion aleatoria."""
        self.rect: pygame.Rect = pygame.Rect(
            WINDOW_WIDTH // 2 - BALL_SIZE // 2,
            GAME_AREA_HEIGHT // 2 - BALL_SIZE // 2,
            BALL_SIZE,
            BALL_SIZE,
        )
        # Direccion horizontal aleatoria: izquierda (-1) o derecha (+1)
        self.speed_x: int = BALL_SPEED_X * random.choice([-1, 1])
        self.speed_y: int = BALL_SPEED_Y * random.choice([-1, 1])
        self.rally_speed_multiplier: float = 1.0
        # Acumuladores fraccionarios para multiplicadores muy bajos (modo agente)
        self._frac_x: float = 0.0
        self._frac_y: float = 0.0

    def reset(self) -> None:
        """
        Devuelve la pelota al centro con direccion aleatoria.

        Se llama cada vez que alguien anota un punto, para empezar
        un nuevo rally desde el centro.
        """
        self.rect.center = (WINDOW_WIDTH // 2, GAME_AREA_HEIGHT // 2)
        self.speed_x = BALL_SPEED_X * random.choice([-1, 1])
        self.speed_y = BALL_SPEED_Y * random.choice([-1, 1])
        self.rally_speed_multiplier = 1.0
        self._frac_x = 0.0
        self._frac_y = 0.0

    def sync_rally_speed(self, rally_hits: int) -> None:
        """Ajusta la aceleracion acumulada segun la longitud del rally."""
        extra_hits = max(0, rally_hits - BALL_RALLY_SPEEDUP_THRESHOLD)
        extra_multiplier = min(
            BALL_RALLY_MAX_SPEED_MULTIPLIER - 1.0,
            extra_hits * BALL_RALLY_SPEEDUP_STEP,
        )
        self.rally_speed_multiplier = 1.0 + extra_multiplier

    def get_effective_speed_x(self, speed_multiplier: float = 1.0) -> float:
        """Velocidad horizontal efectiva tras bullet time y aceleracion de rally."""
        return self.speed_x * speed_multiplier * self.rally_speed_multiplier

    def get_effective_speed_y(self, speed_multiplier: float = 1.0) -> float:
        """Velocidad vertical efectiva tras bullet time y aceleracion de rally."""
        return self.speed_y * speed_multiplier * self.rally_speed_multiplier

    def update(self, speed_multiplier: float = 1.0) -> None:
        """
        Mueve la pelota y la hace rebotar en las paredes superior e inferior.

        Se llama una vez por frame. La pelota avanza segun su velocidad
        y, si toca el techo o el suelo de la zona de juego, invierte
        su direccion vertical (rebote).

        Args:
            speed_multiplier: Multiplicador de velocidad (1.0 = normal,
                              <1.0 = bullet time). Afecta ambos ejes.
        """
        self._frac_x += self.get_effective_speed_x(speed_multiplier)
        self._frac_y += self.get_effective_speed_y(speed_multiplier)
        dx = int(self._frac_x)
        dy = int(self._frac_y)
        self._frac_x -= dx
        self._frac_y -= dy
        self.rect.x += dx
        self.rect.y += dy

        # Rebote en la pared superior
        if self.rect.top <= 0:
            self.rect.top = 0
            self.speed_y = abs(self.speed_y)  # Forzar hacia abajo

        # Rebote en la pared inferior
        if self.rect.bottom >= GAME_AREA_HEIGHT:
            self.rect.bottom = GAME_AREA_HEIGHT
            self.speed_y = -abs(self.speed_y)  # Forzar hacia arriba

    def check_paddle_collision(self, paddle: Paddle) -> bool:
        """
        Detecta si la pelota choca con una paleta y calcula el rebote.

        El angulo del rebote depende de DONDE golpea la pelota en la paleta:
        - Si golpea en la parte alta → la pelota sale hacia arriba.
        - Si golpea en el centro → sale casi horizontal.
        - Si golpea en la parte baja → sale hacia abajo.

        Esto le da al jugador control sobre la direccion de la pelota.

        Args:
            paddle: La paleta con la que comprobar la colision.

        Returns:
            True si hubo colision, False si no.
        """
        if not self.rect.colliderect(paddle.rect):
            return False

        # Invertir direccion horizontal (la pelota "rebota" en la paleta)
        self.speed_x = -self.speed_x

        # Calcular angulo segun el punto de impacto en la paleta.
        # relative_hit va de -1.0 (parte alta) a +1.0 (parte baja).
        relative_hit = (self.rect.centery - paddle.rect.centery) / (PADDLE_HEIGHT / 2)
        self.speed_y = int(BALL_SPEED_Y * max(-1.0, min(1.0, relative_hit)))

        # Evitar que la pelota se quede "atrapada" dentro de la paleta
        # empujandola fuera inmediatamente.
        if self.speed_x > 0:
            self.rect.left = paddle.rect.right
        else:
            self.rect.right = paddle.rect.left

        return True

    def draw(self, surface: pygame.Surface, y_offset: int = 0, color: tuple[int, int, int] | None = None) -> None:
        """
        Dibuja la pelota en la pantalla.

        Args:
            surface:  Superficie de pygame donde dibujar.
            y_offset: Desplazamiento vertical para la zona de juego.
            color:    Color RGB opcional. Si es None, usa COLOR_FOREGROUND.
        """
        pygame.draw.rect(
            surface,
            color if color is not None else COLOR_FOREGROUND,
            self.rect.move(0, y_offset),
        )
