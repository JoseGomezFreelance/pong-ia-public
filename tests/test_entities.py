"""Tests de entidades del juego: Paddle y Ball (pong/entities.py)."""
from __future__ import annotations

import unittest

import pygame

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
from pong.entities import Ball, Paddle


class TestPaddleInit(unittest.TestCase):

    def test_rect_dimensions(self) -> None:
        p = Paddle(10, 100)
        self.assertEqual(p.rect.width, PADDLE_WIDTH)
        self.assertEqual(p.rect.height, PADDLE_HEIGHT)
        self.assertEqual(p.rect.x, 10)
        self.assertEqual(p.rect.y, 100)

    def test_default_speed(self) -> None:
        p = Paddle(0, 0)
        self.assertEqual(p.speed, PADDLE_SPEED)


class TestPaddleMovement(unittest.TestCase):

    def test_move_up(self) -> None:
        p = Paddle(0, 100)
        p.move_up()
        self.assertEqual(p.rect.y, 100 - PADDLE_SPEED)

    def test_move_up_clamps_at_top(self) -> None:
        p = Paddle(0, 2)
        p.move_up()
        self.assertEqual(p.rect.top, 0)

    def test_move_down(self) -> None:
        p = Paddle(0, 100)
        p.move_down()
        self.assertEqual(p.rect.y, 100 + PADDLE_SPEED)

    def test_move_down_clamps_at_bottom(self) -> None:
        p = Paddle(0, GAME_AREA_HEIGHT - PADDLE_HEIGHT - 1)
        p.move_down()
        self.assertEqual(p.rect.bottom, GAME_AREA_HEIGHT)

    def test_move_toward_moves_down(self) -> None:
        p = Paddle(0, 100)
        center_before = p.rect.centery
        p.move_toward(center_before + 50, 5)
        self.assertGreater(p.rect.centery, center_before)

    def test_move_toward_moves_up(self) -> None:
        p = Paddle(0, 200)
        center_before = p.rect.centery
        p.move_toward(center_before - 50, 5)
        self.assertLess(p.rect.centery, center_before)

    def test_move_toward_stays_if_close(self) -> None:
        p = Paddle(0, 100)
        center = p.rect.centery
        p.move_toward(center + 2, 5)
        # diff=2 < speed=5, so should not move
        self.assertEqual(p.rect.centery, center)

    def test_move_toward_respects_speed_multiplier(self) -> None:
        p1 = Paddle(0, 200)
        p2 = Paddle(0, 200)
        target = p1.rect.centery + 100
        p1.move_toward(target, 10, speed_multiplier=1.0)
        p2.move_toward(target, 10, speed_multiplier=0.5)
        # p2 should move less (or same if rounded)
        self.assertGreaterEqual(p1.rect.centery, p2.rect.centery)

    def test_move_toward_clamps_top(self) -> None:
        p = Paddle(0, 5)
        p.move_toward(-100, 20)
        self.assertGreaterEqual(p.rect.top, 0)

    def test_move_toward_clamps_bottom(self) -> None:
        p = Paddle(0, GAME_AREA_HEIGHT - PADDLE_HEIGHT - 5)
        p.move_toward(GAME_AREA_HEIGHT + 100, 20)
        self.assertLessEqual(p.rect.bottom, GAME_AREA_HEIGHT)


class TestBallInit(unittest.TestCase):

    def test_rect_dimensions(self) -> None:
        b = Ball()
        self.assertEqual(b.rect.width, BALL_SIZE)
        self.assertEqual(b.rect.height, BALL_SIZE)

    def test_starts_at_center(self) -> None:
        b = Ball()
        self.assertEqual(b.rect.centerx, WINDOW_WIDTH // 2)
        self.assertEqual(b.rect.centery, GAME_AREA_HEIGHT // 2)

    def test_speed_magnitude(self) -> None:
        b = Ball()
        self.assertEqual(abs(b.speed_x), BALL_SPEED_X)
        self.assertEqual(abs(b.speed_y), BALL_SPEED_Y)


class TestBallReset(unittest.TestCase):

    def test_reset_centers_ball(self) -> None:
        b = Ball()
        b.rect.x = 100
        b.rect.y = 100
        b.reset()
        self.assertEqual(b.rect.centerx, WINDOW_WIDTH // 2)
        self.assertEqual(b.rect.centery, GAME_AREA_HEIGHT // 2)

    def test_reset_randomizes_direction(self) -> None:
        directions = set()
        for _ in range(20):
            b = Ball()
            b.reset()
            directions.add((b.speed_x > 0, b.speed_y > 0))
        # Con 20 resets, deberiamos ver al menos 2 combinaciones distintas
        self.assertGreater(len(directions), 1)

    def test_reset_restores_rally_multiplier(self) -> None:
        b = Ball()
        b.sync_rally_speed(BALL_RALLY_SPEEDUP_THRESHOLD + 25)
        b.reset()
        self.assertEqual(b.rally_speed_multiplier, 1.0)


class TestBallRallySpeed(unittest.TestCase):

    def test_rally_multiplier_stays_at_one_until_threshold(self) -> None:
        b = Ball()
        b.sync_rally_speed(BALL_RALLY_SPEEDUP_THRESHOLD)
        self.assertEqual(b.rally_speed_multiplier, 1.0)

    def test_rally_multiplier_increases_after_threshold(self) -> None:
        b = Ball()
        extra_hits = 5
        b.sync_rally_speed(BALL_RALLY_SPEEDUP_THRESHOLD + extra_hits)
        expected = 1.0 + extra_hits * BALL_RALLY_SPEEDUP_STEP
        self.assertAlmostEqual(b.rally_speed_multiplier, expected)

    def test_rally_multiplier_caps_at_maximum(self) -> None:
        b = Ball()
        b.sync_rally_speed(BALL_RALLY_SPEEDUP_THRESHOLD + 999)
        self.assertEqual(b.rally_speed_multiplier, BALL_RALLY_MAX_SPEED_MULTIPLIER)


class TestBallUpdate(unittest.TestCase):

    def test_moves_by_speed(self) -> None:
        b = Ball()
        b.speed_x = BALL_SPEED_X
        b.speed_y = BALL_SPEED_Y
        x_before = b.rect.x
        y_before = b.rect.y
        b.update()
        self.assertEqual(b.rect.x, x_before + BALL_SPEED_X)
        self.assertEqual(b.rect.y, y_before + BALL_SPEED_Y)

    def test_bounce_top_wall(self) -> None:
        b = Ball()
        b.rect.top = 1
        b.speed_y = -BALL_SPEED_Y
        b.update()
        self.assertGreater(b.speed_y, 0)  # should bounce down
        self.assertGreaterEqual(b.rect.top, 0)

    def test_bounce_bottom_wall(self) -> None:
        b = Ball()
        b.rect.bottom = GAME_AREA_HEIGHT - 1
        b.speed_y = BALL_SPEED_Y
        b.update()
        self.assertLess(b.speed_y, 0)  # should bounce up
        self.assertLessEqual(b.rect.bottom, GAME_AREA_HEIGHT)

    def test_speed_multiplier_reduces_movement(self) -> None:
        b = Ball()
        b.speed_x = BALL_SPEED_X
        b.speed_y = 0
        b.rect.centery = GAME_AREA_HEIGHT // 2
        x_before = b.rect.x
        b.update(speed_multiplier=0.5)
        moved = b.rect.x - x_before
        self.assertEqual(moved, round(BALL_SPEED_X * 0.5))

    def test_rally_multiplier_increases_movement(self) -> None:
        b = Ball()
        b.speed_x = BALL_SPEED_X
        b.speed_y = 0
        b.sync_rally_speed(BALL_RALLY_SPEEDUP_THRESHOLD + 20)
        x_before = b.rect.x
        b.update()
        self.assertEqual(b.rect.x - x_before, 6)


class TestBallPaddleCollision(unittest.TestCase):

    def test_no_collision_when_far(self) -> None:
        b = Ball()
        p = Paddle(0, 0)
        b.rect.center = (WINDOW_WIDTH // 2, GAME_AREA_HEIGHT // 2)
        self.assertFalse(b.check_paddle_collision(p))

    def test_collision_inverts_speed_x(self) -> None:
        p = Paddle(50, 200)
        b = Ball()
        b.speed_x = -BALL_SPEED_X  # moving left toward paddle
        # Place ball overlapping with paddle
        b.rect.right = p.rect.right
        b.rect.centery = p.rect.centery
        original_sign = b.speed_x > 0
        result = b.check_paddle_collision(p)
        self.assertTrue(result)
        self.assertNotEqual(b.speed_x > 0, original_sign)

    def test_collision_center_hit_low_speed_y(self) -> None:
        p = Paddle(50, 200)
        b = Ball()
        b.speed_x = -BALL_SPEED_X
        b.rect.right = p.rect.right
        b.rect.centery = p.rect.centery  # dead center
        b.check_paddle_collision(p)
        # Center hit: speed_y ~= 0
        self.assertLessEqual(abs(b.speed_y), BALL_SPEED_Y)

    def test_collision_top_hit_negative_speed_y(self) -> None:
        p = Paddle(50, 200)
        b = Ball()
        b.speed_x = -BALL_SPEED_X
        b.rect.right = p.rect.right
        b.rect.centery = p.rect.top + 1  # near top
        b.check_paddle_collision(p)
        self.assertLess(b.speed_y, 0)

    def test_collision_pushes_ball_outside(self) -> None:
        p = Paddle(50, 200)
        b = Ball()
        b.speed_x = -BALL_SPEED_X
        b.rect.center = (p.rect.centerx, p.rect.centery)
        b.check_paddle_collision(p)
        # After collision, ball should not overlap paddle
        # speed_x was inverted to positive, so ball.left >= paddle.right
        if b.speed_x > 0:
            self.assertGreaterEqual(b.rect.left, p.rect.right)
        else:
            self.assertLessEqual(b.rect.right, p.rect.left)


if __name__ == "__main__":
    unittest.main()
