"""Pruebas del indicador visual de estado del LLM en el renderer."""
from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import ANY, patch

import pygame

from pong.config.layout import WINDOW_HEIGHT, WINDOW_WIDTH
from pong.config.narrator import COLOR_ANSWER_INACTIVE
from pong.config.ui_end_screen import (
    COLOR_COPY_BUTTON_TEXT,
    END_SCREEN_COPY_BUTTON_TEXT,
    END_SCREEN_RESTART_BUTTON_TEXT,
)
from pong.renderer import Renderer


class _RecordingFont:
    """Fuente fake para capturar que texto se renderiza en el indicador."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, bool, Any]] = []

    def render(self, text: str, antialias: bool, color: Any) -> pygame.Surface:
        self.calls.append((text, antialias, color))
        return pygame.Surface((120, 24))


class _SummaryRecordingFont(_RecordingFont):
    """Fuente fake con medicion de ancho para probar word wrap."""

    def size(self, text: str) -> tuple[int, int]:
        return (max(1, len(text)) * 8, 24)


class _DummyDrawable:
    """Objeto minimo con metodo draw compatible con Renderer.draw_game()."""

    def draw(self, *_args: Any, **_kwargs: Any) -> None:
        return None


class RendererLLMStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.font.init()

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.font.quit()

    def setUp(self) -> None:
        self.screen = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
        self.renderer = Renderer(self.screen)

    def test_draw_narration_area_renders_llm_on_label_when_enabled(self) -> None:
        status_font = _RecordingFont()
        self.renderer.llm_status_font = status_font  # type: ignore[assignment]

        self.renderer._draw_narration_area("Narracion de prueba", llm_enabled=True)

        self.assertIn(("LLM ON", True, COLOR_ANSWER_INACTIVE), status_font.calls)

    def test_draw_narration_area_renders_llm_off_label_when_disabled(self) -> None:
        status_font = _RecordingFont()
        self.renderer.llm_status_font = status_font  # type: ignore[assignment]

        self.renderer._draw_narration_area("Narracion de prueba", llm_enabled=False)

        self.assertIn(("LLM off", True, COLOR_ANSWER_INACTIVE), status_font.calls)

    def test_draw_game_passes_llm_enabled_to_narration_area(self) -> None:
        player = _DummyDrawable()
        computer = _DummyDrawable()
        ball = _DummyDrawable()

        with patch.object(self.renderer, "_draw_scores"), patch.object(
            self.renderer, "_draw_center_line"
        ), patch.object(self.renderer, "_draw_narration_area") as draw_narration, patch(
            "pong.renderer.pygame.display.flip"
        ):
            self.renderer.draw_game(
                score=object(),  # type: ignore[arg-type]
                player=player,  # type: ignore[arg-type]
                computer=computer,  # type: ignore[arg-type]
                ball=ball,  # type: ignore[arg-type]
                narration_text="Texto actual",
                llm_enabled=True,
            )

        draw_narration.assert_called_once_with(
            "Texto actual", llm_enabled=True, colors=ANY
        )

    def test_end_summary_text_is_wrapped_with_guillemets(self) -> None:
        summary_font = _SummaryRecordingFont()
        self.renderer.summary_font = summary_font  # type: ignore[assignment]

        self.renderer._draw_match_summary_section(
            y=20,
            summary_text="Partido parejo con charla tensa y cierre agresivo.",
            summary_progress=1.0,
        )

        rendered_lines = [text for text, _, _ in summary_font.calls]
        self.assertTrue(any(line.startswith("\u00ab") for line in rendered_lines))
        self.assertTrue(any(line.endswith("\u00bb") for line in rendered_lines))

    def test_draw_copy_button_renders_expected_label(self) -> None:
        copy_font = _RecordingFont()
        self.renderer.copy_button_font = copy_font  # type: ignore[assignment]

        self.renderer._draw_copy_button(hovered=False)

        self.assertIn(
            (END_SCREEN_COPY_BUTTON_TEXT, True, COLOR_COPY_BUTTON_TEXT),
            copy_font.calls,
        )

    def test_draw_restart_button_renders_expected_label(self) -> None:
        restart_font = _RecordingFont()
        self.renderer.copy_button_font = restart_font  # type: ignore[assignment]

        self.renderer._draw_restart_button(hovered=False)

        self.assertIn(
            (END_SCREEN_RESTART_BUTTON_TEXT, True, COLOR_COPY_BUTTON_TEXT),
            restart_font.calls,
        )


if __name__ == "__main__":
    unittest.main()
