"""Pruebas para la exportacion y copiado de logs del juego."""
from __future__ import annotations

import unittest
from typing import Any

from pong.config.gameplay import PADDLE_HEIGHT
from pong.config.layout import GAME_AREA_HEIGHT
from pong.game import Game


class GameCopyLogsTests(unittest.TestCase):
    def _build_game_stub(self) -> Game:
        game = Game.__new__(Game)
        game.terminal_log_lines = []
        return game

    def test_build_terminal_export_text_joins_lines(self) -> None:
        game = self._build_game_stub()
        game.terminal_log_lines = ["uno", "dos", "tres"]

        export_text = game._build_terminal_export_text()

        self.assertEqual("uno\ndos\ntres", export_text)

    def test_copy_terminal_logs_reports_success(self) -> None:
        game = self._build_game_stub()
        game.terminal_log_lines = ["linea"]
        seen_logs: list[tuple[str, str]] = []
        seen_status: list[str] = []
        game._log = lambda category, message: seen_logs.append((category, message))  # type: ignore[method-assign]
        game._set_copy_status = lambda message: seen_status.append(message)  # type: ignore[method-assign]
        game._copy_text_to_clipboard = lambda text: (True, "")  # type: ignore[method-assign]

        game._copy_terminal_logs()

        self.assertEqual([("COPIA", "Se copiaron 5 caracteres al portapapeles.")], seen_logs)
        self.assertEqual(["Logs copiados."], seen_status)

    def test_copy_terminal_logs_reports_failure(self) -> None:
        game = self._build_game_stub()
        game.terminal_log_lines = ["linea"]
        seen_logs: list[tuple[str, str]] = []
        seen_status: list[str] = []
        game._log = lambda category, message: seen_logs.append((category, message))  # type: ignore[method-assign]
        game._set_copy_status = lambda message: seen_status.append(message)  # type: ignore[method-assign]
        game._copy_text_to_clipboard = lambda text: (False, "sin permisos")  # type: ignore[method-assign]

        game._copy_terminal_logs()

        self.assertEqual([("COPIA", "Fallo al copiar logs: sin permisos")], seen_logs)
        self.assertEqual(["No se pudo copiar."], seen_status)

    def test_restart_match_resets_state_and_requests_new_intro(self) -> None:
        class _BallStub:
            def __init__(self) -> None:
                self.reset_called = False

            def reset(self) -> None:
                self.reset_called = True

        class _PaddleStub:
            def __init__(self, y: int) -> None:
                self.rect = type("RectStub", (), {"y": y})()

        class _NarrationStub:
            def __init__(self) -> None:
                self.reset_called = False
                self.reformulations: list[str] = []
                self.requests: list[tuple[str, dict[str, str], bool]] = []

            def reset_match_state(self) -> None:
                self.reset_called = True

            def request_reformulation(self, question: str) -> None:
                self.reformulations.append(question)

            def build_game_state(self, *args: Any, **kwargs: Any) -> dict[str, str]:
                return {"event_label": "inicio"}

            def request(self, event_label: str, game_state: dict[str, str], priority: bool = False) -> None:
                self.requests.append((event_label, game_state, priority))

        class _AchievementsStub:
            def __init__(self) -> None:
                self.started = 0
                self.pending_notifications: list[str] = ["dummy"]
                self.notification_start: float | None = 12.0

            def start_match(self) -> None:
                self.started += 1

            def set_notification_start(self, value: float | None) -> None:
                self.notification_start = value

        game = Game.__new__(Game)
        game.showing_end_screen = True
        game.game_saved = False
        game.paused = True
        game.end_screen_scroll = 5
        game.copy_status_text = "ok"
        game.copy_status_expires_at = 99.0
        game.new_records = ["max_rally"]
        game.player = _PaddleStub(10)  # type: ignore[assignment]
        game.computer = _PaddleStub(30)  # type: ignore[assignment]
        game.ball = _BallStub()  # type: ignore[assignment]
        game.narration = _NarrationStub()  # type: ignore[assignment]
        game.achievements = _AchievementsStub()  # type: ignore[assignment]
        game.renderer = type("RendererStub", (), {"clear_background_image": lambda self: None})()
        game.imagegen_active = False
        game._last_imagegen_time = 0.0
        game.imagegen_unlocked = False
        game._save_game_calls = 0  # type: ignore[attr-defined]
        game._save_game = lambda: setattr(game, "_save_game_calls", game._save_game_calls + 1)  # type: ignore[method-assign,attr-defined]
        game._log = lambda *_args, **_kwargs: None  # type: ignore[method-assign]

        game._restart_match()

        self.assertEqual(1, game._save_game_calls)  # type: ignore[attr-defined]
        self.assertFalse(game.showing_end_screen)
        self.assertFalse(game.paused)
        self.assertEqual(0, game.end_screen_scroll)
        self.assertEqual("", game.copy_status_text)
        self.assertEqual([], game.new_records)
        self.assertTrue(game.ball.reset_called)  # type: ignore[attr-defined]
        self.assertTrue(game.narration.reset_called)  # type: ignore[attr-defined]
        self.assertEqual(1, game.achievements.started)  # type: ignore[attr-defined]
        self.assertEqual([], game.achievements.pending_notifications)
        self.assertIsNone(game.achievements.notification_start)  # type: ignore[attr-defined]
        self.assertTrue(game.narration.reformulations)  # type: ignore[attr-defined]
        self.assertTrue(game.narration.requests)  # type: ignore[attr-defined]
        self.assertTrue(game.narration.requests[-1][2])  # type: ignore[attr-defined]
        center_y = GAME_AREA_HEIGHT // 2 - PADDLE_HEIGHT // 2
        self.assertEqual(center_y, game.player.rect.y)
        self.assertEqual(center_y, game.computer.rect.y)


if __name__ == "__main__":
    unittest.main()
