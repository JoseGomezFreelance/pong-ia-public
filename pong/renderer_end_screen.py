"""
pong/renderer_end_screen.py -- Mixin de pantalla final y depuracion.

Contiene los metodos de dibujado de la pantalla de fin de partida
(resumen, records, botones) y la pantalla de depuracion (timeline,
historial LLM, memoria).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from pong.achievements import AchievementDef, AchievementEngine
    from pong.scoring import ScoreState

from pong.config.layout import WINDOW_HEIGHT, WINDOW_WIDTH
from pong.config.ui_achievements import (
    ACHIEVEMENTS_BACK_BUTTON_TEXT,
    ACHIEVEMENTS_SCREEN_HEADER_HEIGHT,
    ACHIEVEMENTS_SCREEN_MARGIN_TOP,
    END_SCREEN_DEBUG_BUTTON_HEIGHT,
    END_SCREEN_DEBUG_BUTTON_MARGIN_BOTTOM,
    END_SCREEN_DEBUG_BUTTON_TEXT,
    END_SCREEN_DEBUG_BUTTON_WIDTH,
    END_SCREEN_LOGROS_BUTTON_HEIGHT,
    END_SCREEN_LOGROS_BUTTON_TEXT,
    END_SCREEN_LOGROS_BUTTON_WIDTH,
)
from pong.config.ui_end_screen import (
    COLOR_COPY_BUTTON_BG,
    COLOR_COPY_BUTTON_HOVER_BG,
    COLOR_EXPORT_BUTTON_BG,
    COLOR_EXPORT_BUTTON_HOVER_BG,
    COLOR_RECORDS_HEADER,
    COLOR_RECORDS_NEW,
    COLOR_RECORDS_TEXT,
    COLOR_RESTART_BUTTON_BG,
    COLOR_RESTART_BUTTON_HOVER_BG,
    DEBUG_LINE_HEIGHT,
    END_SCREEN_COPY_BUTTON_HEIGHT,
    END_SCREEN_COPY_BUTTON_MARGIN_RIGHT,
    END_SCREEN_COPY_BUTTON_MARGIN_TOP,
    END_SCREEN_COPY_BUTTON_TEXT,
    END_SCREEN_COPY_BUTTON_WIDTH,
    END_SCREEN_EXPORT_BUTTON_HEIGHT,
    END_SCREEN_EXPORT_BUTTON_MARGIN_LEFT,
    END_SCREEN_EXPORT_BUTTON_MARGIN_TOP,
    END_SCREEN_EXPORT_BUTTON_TEXT,
    END_SCREEN_EXPORT_BUTTON_WIDTH,
    END_SCREEN_RESTART_BUTTON_HEIGHT,
    END_SCREEN_RESTART_BUTTON_MARGIN_RIGHT,
    END_SCREEN_RESTART_BUTTON_MARGIN_TOP,
    END_SCREEN_RESTART_BUTTON_TEXT,
    END_SCREEN_RESTART_BUTTON_WIDTH,
    END_SCREEN_TEXT_MARGIN,
    RECORDS_TABLE_MARGIN_TOP,
    RECORDS_TABLE_ROW_HEIGHT,
    SUMMARY_LINE_HEIGHT,
    SUMMARY_MAX_LINES,
    SUMMARY_PROGRESS_BAR_HEIGHT,
    SUMMARY_PROGRESS_BAR_WIDTH,
    SUMMARY_PROGRESS_BAR_X,
    SUMMARY_PROGRESS_BLOCK_GAP,
    SUMMARY_PROGRESS_BLOCK_WIDTH,
)
from pong.save_manager import (
    RECORD_CATEGORIES, format_record_value, format_record_date,
)
from pong.theme import ThemeColors


class EndScreenMixin:
    """Mixin: pantalla final (resumen, records, botones) y depuracion."""

    # -- Atributos declarados en Renderer, visibles aquí para mypy --
    screen: pygame.Surface
    font: pygame.font.Font
    llm_status_font: pygame.font.Font
    copy_button_font: pygame.font.Font
    summary_font: pygame.font.Font
    records_font: pygame.font.Font
    debug_font: pygame.font.Font
    copy_button_rect: pygame.Rect
    restart_button_rect: pygame.Rect
    export_button_rect: pygame.Rect
    logros_button_rect: pygame.Rect | None
    debug_button_rect: pygame.Rect | None
    debug_back_button_rect: pygame.Rect

    def _wrap_text(self, text: str, max_width: int,
                   font: pygame.font.Font | None = None) -> list[str]:
        raise NotImplementedError  # Provided by Renderer

    def _build_copy_button_rect(self) -> pygame.Rect:
        """
        Calcula el rectangulo fijo del boton "copiar" en pantalla final.

        Returns:
            pygame.Rect: Rectangulo del boton en esquina superior derecha.
        """
        return pygame.Rect(
            WINDOW_WIDTH - END_SCREEN_COPY_BUTTON_MARGIN_RIGHT
            - END_SCREEN_COPY_BUTTON_WIDTH,
            END_SCREEN_COPY_BUTTON_MARGIN_TOP,
            END_SCREEN_COPY_BUTTON_WIDTH,
            END_SCREEN_COPY_BUTTON_HEIGHT,
        )

    def _build_export_button_rect(self) -> pygame.Rect:
        """
        Calcula el rectangulo fijo del boton "Exportar partida".

        Returns:
            pygame.Rect: Rectangulo del boton en esquina superior izquierda.
        """
        return pygame.Rect(
            END_SCREEN_EXPORT_BUTTON_MARGIN_LEFT,
            END_SCREEN_EXPORT_BUTTON_MARGIN_TOP,
            END_SCREEN_EXPORT_BUTTON_WIDTH,
            END_SCREEN_EXPORT_BUTTON_HEIGHT,
        )

    def _build_restart_button_rect(self) -> pygame.Rect:
        """
        Calcula el rectangulo fijo del boton "Jugar otra vez".

        Returns:
            pygame.Rect: Rectangulo del boton debajo de "copiar".
        """
        return pygame.Rect(
            WINDOW_WIDTH - END_SCREEN_RESTART_BUTTON_MARGIN_RIGHT
            - END_SCREEN_RESTART_BUTTON_WIDTH,
            END_SCREEN_RESTART_BUTTON_MARGIN_TOP,
            END_SCREEN_RESTART_BUTTON_WIDTH,
            END_SCREEN_RESTART_BUTTON_HEIGHT,
        )

    def draw_end_screen(self, score: ScoreState, elapsed_text: str,
                        quit_hint: str,
                        summary_text: str | None = None,
                        summary_progress: float = 0.0,
                        copy_status_text: str = "",
                        mouse_pos: tuple[int, int] | None = None,
                        colors: ThemeColors | None = None,
                        records: dict[str, Any] | None = None,
                        new_records: list[str] | None = None,
                        achievements: AchievementEngine | None = None) -> None:
        """
        Dibuja la pantalla final con resumen, records y logros.

        Args:
            score:             ScoreState final.
            elapsed_text:      Tiempo total formateado.
            quit_hint:         Texto de instrucciones para el usuario.
            summary_text:      Resumen del LLM (None si aun no esta listo).
            summary_progress:  Progreso de la barra (0.0-1.0).
            copy_status_text:  Mensaje de estado del boton copiar.
            mouse_pos:         Posicion actual del cursor (x, y), opcional.
            colors:            ThemeColors con los colores del frame.
            records:           dict con los records guardados (puede ser None).
            new_records:       list de claves de records nuevos esta partida.
            achievements:      AchievementEngine (puede ser None).
        """
        if colors is None:
            colors = ThemeColors()
        if new_records is None:
            new_records = []

        self.screen.fill(colors.end_screen_bg)

        y = 20

        # --- Boton "Exportar partida" en esquina superior izquierda ---
        export_hover = bool(
            mouse_pos and self.export_button_rect.collidepoint(mouse_pos)
        )
        self._draw_export_button(export_hover, colors)

        # --- Titulo (centrado entre los dos botones) ---
        title = self.font.render(
            "FIN DE PARTIDA", True, colors.end_screen_text
        )
        title_rect = title.get_rect(centerx=WINDOW_WIDTH // 2, top=y)
        self.screen.blit(title, title_rect)

        # --- Boton "copiar" en esquina superior derecha ---
        copy_hover = bool(
            mouse_pos and self.copy_button_rect.collidepoint(mouse_pos)
        )
        self._draw_copy_button(copy_hover, colors)

        # --- Boton "Jugar otra vez" (debajo de copiar) ---
        restart_hover = bool(
            mouse_pos and self.restart_button_rect.collidepoint(mouse_pos)
        )
        self._draw_restart_button(restart_hover, colors)

        if copy_status_text:
            status_surface = self.llm_status_font.render(
                copy_status_text, True, colors.summary_label
            )
            status_rect = status_surface.get_rect(
                right=self.restart_button_rect.right,
                top=self.restart_button_rect.bottom + 6,
            )
            self.screen.blit(status_surface, status_rect)

        y += 50

        # --- Resumen LLM o barra de progreso ---
        y = self._draw_match_summary_section(
            y, summary_text, summary_progress, colors
        )

        # --- Tabla de records ---
        y = self._draw_records_table(y, records, new_records, colors)

        # --- Resumen de logros ---
        y = self._draw_achievements_summary(y, achievements, colors, mouse_pos)

        # --- Resumen del partido ---
        final_score = (
            f"Sets finales: Jugador {score.player_sets} - "
            f"Ordenador {score.computer_sets}"
        )
        set_score = (
            f"Juegos del ultimo set: Jugador {score.player_games} - "
            f"Ordenador {score.computer_games}"
        )
        play_time = f"Tiempo total: {elapsed_text}"
        for line in (final_score, set_score, play_time, quit_hint):
            txt = self.debug_font.render(line, True, colors.end_screen_text)
            self.screen.blit(txt, (20, y))
            y += 30

        # --- Boton "Depuracion" centrado en la parte inferior ---
        btn_x = (WINDOW_WIDTH - END_SCREEN_DEBUG_BUTTON_WIDTH) // 2
        btn_y = WINDOW_HEIGHT - END_SCREEN_DEBUG_BUTTON_HEIGHT - END_SCREEN_DEBUG_BUTTON_MARGIN_BOTTOM
        self.debug_button_rect = pygame.Rect(
            btn_x, btn_y,
            END_SCREEN_DEBUG_BUTTON_WIDTH,
            END_SCREEN_DEBUG_BUTTON_HEIGHT,
        )
        debug_hover = bool(
            mouse_pos and self.debug_button_rect.collidepoint(mouse_pos)
        )
        self._draw_debug_button(debug_hover, colors)

        pygame.display.flip()

    def _draw_debug_button(self, hovered: bool, colors: ThemeColors | None = None) -> None:
        """Dibuja el boton 'Depuracion' con fondo rojo."""
        if colors is None:
            colors = ThemeColors()
        bg_color = (
            COLOR_RESTART_BUTTON_HOVER_BG if hovered
            else COLOR_RESTART_BUTTON_BG
        )
        if self.debug_button_rect is None:
            return
        pygame.draw.rect(self.screen, bg_color, self.debug_button_rect)
        pygame.draw.rect(
            self.screen, colors.copy_button_border,
            self.debug_button_rect, 2,
        )
        label = self.copy_button_font.render(
            END_SCREEN_DEBUG_BUTTON_TEXT, True, colors.copy_button_text,
        )
        label_rect = label.get_rect(center=self.debug_button_rect.center)
        self.screen.blit(label, label_rect)

    def draw_debug_screen(self, score_timeline: list[dict[str, Any]],
                          narration_log: list[dict[str, Any]],
                          narrator_memory: Any, scroll_offset: int,
                          format_elapsed_fn: Callable[[float], str],
                          mouse_pos: tuple[int, int] | None,
                          colors: ThemeColors | None) -> int:
        """Dibuja la pantalla de depuracion con telemetria scrollable.

        Args:
            score_timeline:    Lista de eventos de punto.
            narration_log:     Lista de narraciones generadas.
            narrator_memory:   Memoria del narrador (deque).
            scroll_offset:     Posicion de scroll actual.
            format_elapsed_fn: Funcion para formatear timestamps.
            mouse_pos:         Posicion actual del cursor (x, y).
            colors:            ThemeColors con los colores del frame.

        Returns:
            int: scroll_offset ajustado al maximo permitido.
        """
        if colors is None:
            colors = ThemeColors()

        self.screen.fill(colors.end_screen_bg)

        # --- Header fijo: boton Volver + titulo ---
        back_hover = bool(
            mouse_pos
            and self.debug_back_button_rect.collidepoint(mouse_pos)
        )
        self._draw_debug_back_button(back_hover, colors)

        title = self.font.render(
            "DEPURACIÓN", True, colors.end_screen_text,
        )
        title_rect = title.get_rect(
            centerx=WINDOW_WIDTH // 2,
            top=ACHIEVEMENTS_SCREEN_MARGIN_TOP,
        )
        self.screen.blit(title, title_rect)

        # --- Preparar historial combinado ---
        debug_lines = []

        debug_lines.append("=== EVENTOS DE PUNTO ===")
        if not score_timeline:
            debug_lines.append("Sin puntos registrados.")
        else:
            for point in score_timeline:
                stamp = format_elapsed_fn(point["elapsed_seconds"])
                debug_lines.append(
                    f"[{stamp}] {point['description']} -> "
                    f"{point['scoreboard']}"
                )

        debug_lines.append("")
        debug_lines.append("=== HISTORIAL DE MENSAJES LLM ===")
        if not narration_log:
            debug_lines.append("Sin mensajes de narrador registrados.")
        else:
            for entry in narration_log:
                stamp = format_elapsed_fn(entry["elapsed_seconds"])
                debug_lines.append(
                    f"[{stamp}] ({entry['event_label']}, "
                    f"{entry['scoreboard']}) {entry['text']}"
                )

        debug_lines.append("")
        debug_lines.append("=== MEMORIA FINAL DEL LLM ===")
        if not narrator_memory:
            debug_lines.append("Sin memoria final.")
        else:
            for index, turn in enumerate(narrator_memory, start=1):
                marker = turn.get("scoreboard")
                if not marker:
                    player_score = turn.get("player_score", "?")
                    computer_score = turn.get("computer_score", "?")
                    marker = f"{player_score}-{computer_score}"
                debug_lines.append(
                    f"{index}. Evento={turn['event_label']} | "
                    f"Jugada={turn['last_play']} | "
                    f"Marcador={marker} | "
                    f"Narracion={turn['narration']}"
                )

        # --- Aplanar lineas con wrapping ---
        max_text_width = WINDOW_WIDTH - END_SCREEN_TEXT_MARGIN
        flattened_lines = []
        for line in debug_lines:
            flattened_lines.extend(self._wrap_text(line, max_text_width))

        # --- Render con scroll vertical ---
        start_y = (
            ACHIEVEMENTS_SCREEN_MARGIN_TOP
            + ACHIEVEMENTS_SCREEN_HEADER_HEIGHT
        )
        visible_height = WINDOW_HEIGHT - start_y - 15
        max_visible_lines = max(1, visible_height // DEBUG_LINE_HEIGHT)
        max_scroll = max(0, len(flattened_lines) - max_visible_lines)

        scroll_offset = min(scroll_offset, max_scroll)

        visible_lines = flattened_lines[
            scroll_offset : scroll_offset + max_visible_lines
        ]

        for i, line in enumerate(visible_lines):
            txt = self.debug_font.render(line, True, colors.end_screen_text)
            self.screen.blit(txt, (20, start_y + i * DEBUG_LINE_HEIGHT))

        pygame.display.flip()

        return scroll_offset

    def _draw_debug_back_button(self, hovered: bool, colors: ThemeColors | None = None) -> None:
        """Dibuja el boton 'Volver' en la pantalla de depuracion."""
        if colors is None:
            colors = ThemeColors()
        bg_color = (
            COLOR_EXPORT_BUTTON_HOVER_BG if hovered
            else COLOR_EXPORT_BUTTON_BG
        )
        pygame.draw.rect(self.screen, bg_color, self.debug_back_button_rect)
        pygame.draw.rect(
            self.screen, colors.copy_button_border,
            self.debug_back_button_rect, 2,
        )
        label = self.copy_button_font.render(
            ACHIEVEMENTS_BACK_BUTTON_TEXT, True, colors.copy_button_text,
        )
        label_rect = label.get_rect(
            center=self.debug_back_button_rect.center,
        )
        self.screen.blit(label, label_rect)

    def _draw_copy_button(self, hovered: bool, colors: ThemeColors | None = None) -> None:
        """
        Dibuja el boton "copiar" con estilo retro.

        Args:
            hovered: True si el cursor esta sobre el boton.
            colors:  ThemeColors con los colores del frame.
        """
        if colors is None:
            colors = ThemeColors()
        bg_color = COLOR_COPY_BUTTON_HOVER_BG if hovered else COLOR_COPY_BUTTON_BG
        pygame.draw.rect(self.screen, bg_color, self.copy_button_rect)
        pygame.draw.rect(
            self.screen, colors.copy_button_border, self.copy_button_rect, 2
        )

        label_surface = self.copy_button_font.render(
            END_SCREEN_COPY_BUTTON_TEXT, True, colors.copy_button_text
        )
        label_rect = label_surface.get_rect(center=self.copy_button_rect.center)
        self.screen.blit(label_surface, label_rect)

    def _draw_export_button(self, hovered: bool, colors: ThemeColors | None = None) -> None:
        """
        Dibuja el boton "Exportar partida" con estilo retro.

        Args:
            hovered: True si el cursor esta sobre el boton.
            colors:  ThemeColors con los colores del frame.
        """
        if colors is None:
            colors = ThemeColors()
        bg_color = COLOR_EXPORT_BUTTON_HOVER_BG if hovered else COLOR_EXPORT_BUTTON_BG
        pygame.draw.rect(self.screen, bg_color, self.export_button_rect)
        pygame.draw.rect(
            self.screen, colors.copy_button_border, self.export_button_rect, 2
        )

        label_surface = self.copy_button_font.render(
            END_SCREEN_EXPORT_BUTTON_TEXT, True, colors.copy_button_text
        )
        label_rect = label_surface.get_rect(center=self.export_button_rect.center)
        self.screen.blit(label_surface, label_rect)

    def _draw_restart_button(self, hovered: bool, colors: ThemeColors | None = None) -> None:
        """
        Dibuja el boton "Jugar otra vez" con fondo rojo.

        Args:
            hovered: True si el cursor esta sobre el boton.
            colors:  ThemeColors con los colores del frame.
        """
        if colors is None:
            colors = ThemeColors()
        bg_color = (
            COLOR_RESTART_BUTTON_HOVER_BG if hovered else COLOR_RESTART_BUTTON_BG
        )
        pygame.draw.rect(self.screen, bg_color, self.restart_button_rect)
        pygame.draw.rect(
            self.screen, colors.copy_button_border, self.restart_button_rect, 2
        )

        label_surface = self.copy_button_font.render(
            END_SCREEN_RESTART_BUTTON_TEXT, True, colors.copy_button_text
        )
        label_rect = label_surface.get_rect(center=self.restart_button_rect.center)
        self.screen.blit(label_surface, label_rect)

    def _draw_records_table(self, y: int, records: dict[str, Any] | None, new_records: list[str], colors: ThemeColors) -> int:
        """
        Dibuja la tabla de mejores marcas debajo del resumen LLM.

        Muestra las 5 categorias de records con su valor y fecha.
        Las categorias con nuevo record se marcan con una estrella.

        Args:
            y:           Posicion Y actual en la pantalla.
            records:     dict con los records actuales (puede ser None/vacio).
            new_records: list de claves de records nuevos en esta partida.
            colors:      ThemeColors con los colores del frame.

        Returns:
            int: Nueva posicion Y despues de la tabla.
        """
        if records is None:
            records = {}

        y += RECORDS_TABLE_MARGIN_TOP

        # --- Cabecera ---
        header = self.records_font.render(
            "MEJORES MARCAS", True, COLOR_RECORDS_HEADER,
        )
        header_rect = header.get_rect(centerx=WINDOW_WIDTH // 2, top=y)
        self.screen.blit(header, header_rect)
        y += RECORDS_TABLE_ROW_HEIGHT + 2

        # --- Linea separadora ---
        pygame.draw.line(
            self.screen, COLOR_RECORDS_HEADER,
            (20, y), (WINDOW_WIDTH - 20, y), 1,
        )
        y += 4

        # --- Columnas ---
        col_category = 20
        col_value = 340
        col_date = 520
        col_new = 680

        for key, label in RECORD_CATEGORIES:
            rec = records.get(key)

            # Nombre de la categoria
            cat_surface = self.records_font.render(
                label, True, COLOR_RECORDS_TEXT,
            )
            self.screen.blit(cat_surface, (col_category, y))

            if rec:
                # Valor formateado
                val_text = format_record_value(key, rec["value"])
                val_surface = self.records_font.render(
                    val_text, True, COLOR_RECORDS_TEXT,
                )
                self.screen.blit(val_surface, (col_value, y))

                # Fecha
                date_text = format_record_date(rec.get("date", ""))
                date_surface = self.records_font.render(
                    date_text, True, COLOR_RECORDS_TEXT,
                )
                self.screen.blit(date_surface, (col_date, y))

                # Marcador de nuevo record
                if key in new_records:
                    new_surface = self.records_font.render(
                        "\u2605 NUEVO", True, COLOR_RECORDS_NEW,
                    )
                    self.screen.blit(new_surface, (col_new, y))
            else:
                # Sin datos todavia
                dash_surface = self.records_font.render(
                    "\u2014", True, COLOR_RECORDS_TEXT,
                )
                self.screen.blit(dash_surface, (col_value, y))

            y += RECORDS_TABLE_ROW_HEIGHT

        y += 6
        return y

    def _draw_achievements_summary(self, y: int, achievements: AchievementEngine | None,
                                    colors: ThemeColors,
                                    mouse_pos: tuple[int, int] | None = None) -> int:
        """Dibuja un resumen de logros en la pantalla final.

        Muestra el contador de logros desbloqueados/totales, los logros
        recien desbloqueados en esta partida y un boton para abrir la
        galeria completa.

        Args:
            y:            Posicion Y actual.
            achievements: AchievementEngine (puede ser None).
            colors:       ThemeColors con los colores del frame.
            mouse_pos:    Posicion del cursor (x, y), opcional.

        Returns:
            int: Nueva posicion Y.
        """
        if achievements is None:
            return y

        y += RECORDS_TABLE_MARGIN_TOP

        # Cabecera: LOGROS: X/45
        total = achievements.count_total()
        unlocked = achievements.count_unlocked()
        header = self.records_font.render(
            f"LOGROS: {unlocked}/{total}", True, COLOR_RECORDS_HEADER,
        )
        header_rect = header.get_rect(centerx=WINDOW_WIDTH // 2, top=y)
        self.screen.blit(header, header_rect)
        y += RECORDS_TABLE_ROW_HEIGHT + 2

        # Linea separadora
        pygame.draw.line(
            self.screen, COLOR_RECORDS_HEADER,
            (20, y), (WINDOW_WIDTH - 20, y), 1,
        )
        y += 4

        # Guardar inicio de la lista para centrar el boton despues
        list_start_y = y

        # Mostrar logros desbloqueados que aun estan en la cola de notificaciones
        # o los mas recientes (de esta sesion)
        recent = []
        for aid, data in achievements.unlocked.items():
            adef = achievements.definitions.get(aid)
            if adef:
                recent.append(adef)

        # Mostrar los ultimos 5 logros desbloqueados
        for adef in recent[-5:]:
            line = f"\u2605 {adef.name} \u2014 {adef.flavor}"
            surface = self.records_font.render(
                line, True, COLOR_RECORDS_NEW,
            )
            self.screen.blit(surface, (20, y))
            y += RECORDS_TABLE_ROW_HEIGHT

        if not recent:
            dash = self.records_font.render(
                "Ninguno desbloqueado todavia", True, COLOR_RECORDS_TEXT,
            )
            self.screen.blit(dash, (20, y))
            y += RECORDS_TABLE_ROW_HEIGHT

        # Boton "Logros" a la derecha, centrado verticalmente con la lista
        list_end_y = y
        btn_center_y = (list_start_y + list_end_y) // 2
        btn_x = WINDOW_WIDTH - END_SCREEN_LOGROS_BUTTON_WIDTH - 20
        btn_y = btn_center_y - END_SCREEN_LOGROS_BUTTON_HEIGHT // 2
        self.logros_button_rect = pygame.Rect(
            btn_x, btn_y,
            END_SCREEN_LOGROS_BUTTON_WIDTH,
            END_SCREEN_LOGROS_BUTTON_HEIGHT,
        )
        logros_hover = bool(
            mouse_pos and self.logros_button_rect is not None
            and self.logros_button_rect.collidepoint(mouse_pos)
        )
        self._draw_logros_button(logros_hover, colors)

        y += 6
        return y

    def _draw_logros_button(self, hovered: bool, colors: ThemeColors | None = None) -> None:
        """Dibuja el boton 'Logros' con fondo rojo (estilo 'Jugar otra vez')."""
        if self.logros_button_rect is None:
            return
        if colors is None:
            colors = ThemeColors()
        bg_color = (
            COLOR_RESTART_BUTTON_HOVER_BG if hovered
            else COLOR_RESTART_BUTTON_BG
        )
        pygame.draw.rect(self.screen, bg_color, self.logros_button_rect)
        pygame.draw.rect(
            self.screen, colors.copy_button_border,
            self.logros_button_rect, 2,
        )
        label = self.copy_button_font.render(
            END_SCREEN_LOGROS_BUTTON_TEXT, True, colors.copy_button_text,
        )
        label_rect = label.get_rect(center=self.logros_button_rect.center)
        self.screen.blit(label, label_rect)

    def _draw_match_summary_section(self, y: int, summary_text: str | None,
                                    summary_progress: float,
                                    colors: ThemeColors | None = None) -> int:
        """
        Dibuja la seccion de resumen LLM: barra de progreso o texto.

        Si el resumen no esta listo, dibuja una barra de progreso estilo Pong.
        Si esta listo, dibuja el texto del resumen entre comillas angulares
        (\u00ab \u00bb) con word wrap.

        Args:
            y:                Posicion Y actual en la pantalla.
            summary_text:     String con el resumen (o None si aun no esta listo).
            summary_progress: Float 0.0-1.0 indicando progreso de la barra.
            colors:           ThemeColors con los colores del frame.

        Returns:
            int: Nueva posicion Y despues de esta seccion.
        """
        if colors is None:
            colors = ThemeColors()

        if summary_text is not None:
            # --- Resumen listo: mostrar texto ---
            label = self.debug_font.render(
                "Veredicto final del LLM:", True, colors.summary_label,
            )
            self.screen.blit(label, (20, y))
            y += 28

            clean_text = summary_text.strip().strip("\u00ab\u00bb\"'`")
            if not clean_text:
                clean_text = "(sin resumen disponible)"
            quoted_summary = f"\u00ab{clean_text}\u00bb"

            max_width = WINDOW_WIDTH - END_SCREEN_TEXT_MARGIN
            lines = self._wrap_text(quoted_summary, max_width, self.summary_font)
            for line_text in lines[:SUMMARY_MAX_LINES]:
                line_surface = self.summary_font.render(
                    line_text, True, colors.summary_text,
                )
                self.screen.blit(line_surface, (20, y))
                y += SUMMARY_LINE_HEIGHT
            y += 10
        else:
            # --- Resumen pendiente: mostrar barra de progreso ---
            label = self.debug_font.render(
                "LLM reflexionando sobre partido y conversacion...",
                True,
                colors.summary_label,
            )
            self.screen.blit(label, (20, y))
            y += 28

            self._draw_pong_progress_bar(y, summary_progress, colors)
            y += SUMMARY_PROGRESS_BAR_HEIGHT + 15

        return y

    def _draw_pong_progress_bar(self, y: int, progress: float, colors: ThemeColors | None = None) -> None:
        """
        Dibuja una barra de progreso estilo Pong con bloques individuales.

        Fila horizontal de bloques que se rellenan de izquierda a
        derecha. Los bloques rellenos usan el color del tema; los vacios
        gris oscuro.

        Args:
            y:        Posicion Y donde dibujar la barra.
            progress: Float 0.0-1.0 indicando cuanto esta llena.
            colors:   ThemeColors con los colores del frame.
        """
        if colors is None:
            colors = ThemeColors()
        block_step = SUMMARY_PROGRESS_BLOCK_WIDTH + SUMMARY_PROGRESS_BLOCK_GAP
        total_blocks = SUMMARY_PROGRESS_BAR_WIDTH // block_step
        filled_blocks = int(total_blocks * min(progress, 1.0))

        for i in range(total_blocks):
            block_x = SUMMARY_PROGRESS_BAR_X + i * block_step
            block_rect = pygame.Rect(
                block_x, y,
                SUMMARY_PROGRESS_BLOCK_WIDTH, SUMMARY_PROGRESS_BAR_HEIGHT,
            )
            if i < filled_blocks:
                pygame.draw.rect(self.screen, colors.progress_filled, block_rect)
            else:
                pygame.draw.rect(self.screen, colors.progress_empty, block_rect)
