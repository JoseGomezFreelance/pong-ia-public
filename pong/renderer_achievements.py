"""
pong/renderer_achievements.py -- Mixin de logros y galeria.

Contiene los metodos de dibujado del popup de logro desbloqueado,
la galeria completa de logros con estadisticas y la cabecera con
barra de progreso.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from pong.achievements import AchievementDef, AchievementEngine

from pong.config.layout import WINDOW_HEIGHT, WINDOW_WIDTH
from pong.config.ui_achievements import (
    ACHIEVEMENT_POPUP_BORDER_WIDTH,
    ACHIEVEMENT_POPUP_DURATION,
    ACHIEVEMENT_POPUP_FADE_DURATION,
    ACHIEVEMENT_POPUP_FONT_FLAVOR,
    ACHIEVEMENT_POPUP_FONT_NAME,
    ACHIEVEMENT_POPUP_HEIGHT,
    ACHIEVEMENT_POPUP_MARGIN,
    ACHIEVEMENT_POPUP_SLIDE_DURATION,
    ACHIEVEMENT_POPUP_WIDTH,
    ACHIEVEMENT_TILE_BORDER_WIDTH,
    ACHIEVEMENT_TILE_GAP_X,
    ACHIEVEMENT_TILE_GAP_Y,
    ACHIEVEMENT_TILE_HEIGHT,
    ACHIEVEMENT_TILE_PADDING,
    ACHIEVEMENT_TILE_WIDTH,
    ACHIEVEMENTS_BACK_BUTTON_HEIGHT,
    ACHIEVEMENTS_BACK_BUTTON_MARGIN_TOP,
    ACHIEVEMENTS_BACK_BUTTON_TEXT,
    ACHIEVEMENTS_BACK_BUTTON_WIDTH,
    ACHIEVEMENTS_SCREEN_CATEGORY_GAP,
    ACHIEVEMENTS_SCREEN_CATEGORY_HEADER_HEIGHT,
    ACHIEVEMENTS_SCREEN_HEADER_HEIGHT,
    ACHIEVEMENTS_SCREEN_MARGIN_TOP,
    ACHIEVEMENTS_SCREEN_MARGIN_X,
    COLOR_ACHIEVEMENT_CATEGORY_HEADER,
    COLOR_ACHIEVEMENT_LOCKED_BG,
    COLOR_ACHIEVEMENT_LOCKED_BORDER,
    COLOR_ACHIEVEMENT_LOCKED_MYSTERY,
    COLOR_ACHIEVEMENT_LOCKED_TEXT,
    COLOR_ACHIEVEMENT_PROGRESS_BAR,
    COLOR_ACHIEVEMENT_PROGRESS_BAR_BG,
    COLOR_ACHIEVEMENT_PROGRESS_TEXT,
    COLOR_ACHIEVEMENT_UNLOCKED_BG,
    COLOR_ACHIEVEMENT_UNLOCKED_BORDER,
    COLOR_ACHIEVEMENT_UNLOCKED_DESC,
    COLOR_ACHIEVEMENT_UNLOCKED_FLAVOR,
    COLOR_ACHIEVEMENT_UNLOCKED_NAME,
    STATS_SECTION_HEADER_GAP,
    STATS_SECTION_LABEL_COLOR,
    STATS_SECTION_MOOD_COLOR,
    STATS_SECTION_RECORD_COLOR,
    STATS_SECTION_ROW_HEIGHT,
    STATS_SECTION_VALUE_COLOR,
)
from pong.config.ui_end_screen import (
    COLOR_COPY_BUTTON_BG,
    COLOR_COPY_BUTTON_HOVER_BG,
    COLOR_RECORDS_HEADER,
)
from pong.config.zx_spectrum import ZX_BLACK, ZX_CYAN_BRIGHT, ZX_WHITE, ZX_YELLOW
from pong.achievements import (
    CATEGORY_CAREER,
    CATEGORY_EMOTION,
    CATEGORY_MATCH,
    CATEGORY_SECRET,
)
from pong.achievement_icons import get_icon
from pong.save_manager import _format_time
from pong.theme import ThemeColors


class AchievementsMixin:
    """Mixin: popup de logro, galeria de logros y estadisticas."""

    # -- Atributos declarados en Renderer, visibles aquí para mypy --
    screen: pygame.Surface
    font: pygame.font.Font
    copy_button_font: pygame.font.Font
    records_font: pygame.font.Font
    achievement_name_font: pygame.font.Font
    achievement_flavor_font: pygame.font.Font
    achievement_tile_name_font: pygame.font.Font
    achievement_tile_desc_font: pygame.font.Font
    achievement_category_font: pygame.font.Font
    achievement_progress_font: pygame.font.Font
    achievements_back_button_rect: pygame.Rect

    _CATEGORY_ORDER = [
        (CATEGORY_CAREER, "CARRERA"),
        (CATEGORY_MATCH, "HAZANA"),
        (CATEGORY_SECRET, "SECRETO"),
        (CATEGORY_EMOTION, "EMOCIONAL"),
    ]

    def _build_achievements_back_button_rect(self) -> pygame.Rect:
        """Rectangulo fijo del boton 'Volver' en la galeria de logros."""
        return pygame.Rect(
            ACHIEVEMENTS_SCREEN_MARGIN_X,
            ACHIEVEMENTS_BACK_BUTTON_MARGIN_TOP,
            ACHIEVEMENTS_BACK_BUTTON_WIDTH,
            ACHIEVEMENTS_BACK_BUTTON_HEIGHT,
        )

    def draw_achievement_popup(self, achievement_def: AchievementDef, elapsed: float) -> None:
        """Dibuja el popup de logro desbloqueado estilo ZX Spectrum.

        El popup aparece centrado horizontalmente desde la parte inferior
        de la ventana, con animacion slide-up y borde ZX_CYAN_BRIGHT.

        Args:
            achievement_def: AchievementDef del logro.
            elapsed:         Segundos desde que se mostro el popup.
        """
        duration = ACHIEVEMENT_POPUP_DURATION

        # Calcular alpha para fade-out
        alpha = 255
        fade_start = duration - ACHIEVEMENT_POPUP_FADE_DURATION
        if elapsed > fade_start:
            progress = (elapsed - fade_start) / ACHIEVEMENT_POPUP_FADE_DURATION
            alpha = max(0, int(255 * (1.0 - progress)))

        if alpha <= 0:
            return

        popup_width = ACHIEVEMENT_POPUP_WIDTH
        popup_height = ACHIEVEMENT_POPUP_HEIGHT
        popup_x = (WINDOW_WIDTH - popup_width) // 2

        # Posicion final: parte inferior de la ventana con margen
        final_y = WINDOW_HEIGHT - popup_height - ACHIEVEMENT_POPUP_MARGIN

        # Animacion slide-up (ease-out cuadratico)
        if elapsed < ACHIEVEMENT_POPUP_SLIDE_DURATION:
            t = elapsed / ACHIEVEMENT_POPUP_SLIDE_DURATION
            t = 1.0 - (1.0 - t) ** 2          # ease-out
            start_y = WINDOW_HEIGHT             # fuera de pantalla por abajo
            popup_y = int(start_y + (final_y - start_y) * t)
        else:
            popup_y = final_y

        # Crear superficie con canal alpha
        popup_surface = pygame.Surface(
            (popup_width, popup_height), pygame.SRCALPHA,
        )

        # Fondo negro con alpha
        popup_surface.fill((*ZX_BLACK, alpha))

        # Borde cyan ZX Spectrum
        border_color = (*ZX_CYAN_BRIGHT, alpha)
        pygame.draw.rect(
            popup_surface, border_color,
            (0, 0, popup_width, popup_height),
            ACHIEVEMENT_POPUP_BORDER_WIDTH,
        )

        # Icono 24x24 del logro
        icon_surface = get_icon(achievement_def, unlocked=True, scale=1)
        icon_surface = icon_surface.copy()
        icon_surface.set_alpha(alpha)
        popup_surface.blit(icon_surface, (12, 18))

        text_x = 46

        # Estrella + nombre del logro
        name_color = (*ZX_YELLOW, alpha)
        name_text = self.achievement_name_font.render(
            f"\u2605 LOGRO: {achievement_def.name}",
            True, name_color,
        )
        popup_surface.blit(name_text, (text_x, 10))

        # Flavor text
        flavor_color = (*ZX_WHITE, alpha)
        flavor_text = self.achievement_flavor_font.render(
            achievement_def.flavor,
            True, flavor_color,
        )
        popup_surface.blit(flavor_text, (text_x, 35))

        self.screen.blit(popup_surface, (popup_x, popup_y))

    def draw_achievements_screen(self, achievements: AchievementEngine,
                                 scroll_offset: int,
                                 mouse_pos: tuple[int, int] | None,
                                 colors: ThemeColors | None,
                                 stats_data: dict[str, Any] | None = None) -> int:
        """Dibuja la pantalla completa de estadisticas y logros.

        Muestra estadisticas de carrera arriba, y debajo todos los
        logros organizados por categoria en un grid de dos columnas
        con scroll vertical.

        Args:
            achievements:  AchievementEngine con las definiciones y desbloqueos.
            scroll_offset: Posicion de scroll actual (en filas de tiles).
            mouse_pos:     Posicion del cursor (x, y).
            colors:        ThemeColors con los colores del frame.
            stats_data:    dict de estadisticas derivadas (de compute_derived_stats).

        Returns:
            int: scroll_offset ajustado al maximo permitido.
        """
        if colors is None:
            colors = ThemeColors()

        self.screen.fill(colors.end_screen_bg)

        # --- Header fijo ---
        self._draw_achievements_screen_header(achievements, mouse_pos, colors)

        # --- Contenido scrollable ---
        content_top = (
            ACHIEVEMENTS_SCREEN_MARGIN_TOP + ACHIEVEMENTS_SCREEN_HEADER_HEIGHT
        )
        scroll_step = ACHIEVEMENT_TILE_HEIGHT + ACHIEVEMENT_TILE_GAP_Y
        scroll_px = scroll_offset * scroll_step

        col_x = [
            ACHIEVEMENTS_SCREEN_MARGIN_X,
            ACHIEVEMENTS_SCREEN_MARGIN_X + ACHIEVEMENT_TILE_WIDTH
            + ACHIEVEMENT_TILE_GAP_X,
        ]

        # Clipping: no dibujar fuera del area scrollable.
        clip_rect = pygame.Rect(0, content_top, WINDOW_WIDTH,
                                WINDOW_HEIGHT - content_top)
        self.screen.set_clip(clip_rect)

        y = content_top - scroll_px

        # --- Seccion de estadisticas (antes de los logros) ---
        if stats_data:
            y = self._draw_stats_section(y, stats_data, colors)
            y += ACHIEVEMENTS_SCREEN_CATEGORY_GAP

        for cat_key, cat_label in self._CATEGORY_ORDER:
            cat_defs = [
                d for d in achievements.definitions.values()
                if d.category == cat_key
            ]
            cat_unlocked = sum(
                1 for d in cat_defs if achievements.is_unlocked(d.id)
            )

            # Cabecera de categoria
            header_text = f"{cat_label} ({cat_unlocked}/{len(cat_defs)})"
            if (y + ACHIEVEMENTS_SCREEN_CATEGORY_HEADER_HEIGHT > content_top
                    and y < WINDOW_HEIGHT):
                self._draw_gallery_category_header(y, header_text, colors)
            y += ACHIEVEMENTS_SCREEN_CATEGORY_HEADER_HEIGHT + 4

            # Tiles en grid de 2 columnas
            num_rows = (len(cat_defs) + 1) // 2
            for i, adef in enumerate(cat_defs):
                col = i % 2
                row = i // 2
                tile_y = y + row * scroll_step
                tile_x = col_x[col]

                if (tile_y + ACHIEVEMENT_TILE_HEIGHT > content_top
                        and tile_y < WINDOW_HEIGHT):
                    is_unlocked = achievements.is_unlocked(adef.id)
                    self._draw_achievement_tile(
                        tile_x, tile_y, adef, is_unlocked,
                    )

            y += num_rows * scroll_step
            y += ACHIEVEMENTS_SCREEN_CATEGORY_GAP

        # Restaurar clipping
        self.screen.set_clip(None)

        # --- Calcular max scroll ---
        total_content_height = y + scroll_px - content_top
        visible_height = WINDOW_HEIGHT - content_top - 10
        if total_content_height > visible_height:
            max_scroll = (
                (total_content_height - visible_height) // scroll_step + 1
            )
        else:
            max_scroll = 0
        scroll_offset = min(scroll_offset, max_scroll)

        pygame.display.flip()
        return scroll_offset

    def _draw_achievements_screen_header(self, achievements: AchievementEngine,
                                         mouse_pos: tuple[int, int] | None,
                                         colors: ThemeColors) -> None:
        """Dibuja la cabecera fija de la galeria de logros.

        Incluye boton Volver, titulo, contador y barra de progreso.
        """
        # Boton "Volver"
        back_hover = bool(
            mouse_pos
            and self.achievements_back_button_rect.collidepoint(mouse_pos)
        )
        bg = (
            COLOR_COPY_BUTTON_HOVER_BG if back_hover else COLOR_COPY_BUTTON_BG
        )
        pygame.draw.rect(self.screen, bg,
                         self.achievements_back_button_rect)
        pygame.draw.rect(self.screen, colors.copy_button_border,
                         self.achievements_back_button_rect, 2)
        back_label = self.copy_button_font.render(
            ACHIEVEMENTS_BACK_BUTTON_TEXT, True, colors.copy_button_text,
        )
        back_rect = back_label.get_rect(
            center=self.achievements_back_button_rect.center,
        )
        self.screen.blit(back_label, back_rect)

        # Titulo centrado
        title = self.font.render(
            "ESTADÍSTICAS Y LOGROS", True, colors.end_screen_text,
        )
        title_rect = title.get_rect(
            centerx=WINDOW_WIDTH // 2,
            top=ACHIEVEMENTS_SCREEN_MARGIN_TOP,
        )
        self.screen.blit(title, title_rect)

        # Contador X/45 (XX%) a la derecha
        total = achievements.count_total()
        unlocked = achievements.count_unlocked()
        pct = int(unlocked / total * 100) if total > 0 else 0
        count_text = f"{unlocked}/{total} ({pct}%)"
        count_surface = self.achievement_progress_font.render(
            count_text, True, COLOR_ACHIEVEMENT_PROGRESS_TEXT,
        )
        count_rect = count_surface.get_rect(
            right=WINDOW_WIDTH - ACHIEVEMENTS_SCREEN_MARGIN_X,
            top=ACHIEVEMENTS_SCREEN_MARGIN_TOP + 4,
        )
        self.screen.blit(count_surface, count_rect)

        # Barra de progreso
        bar_y = ACHIEVEMENTS_SCREEN_MARGIN_TOP + 44
        bar_x = ACHIEVEMENTS_SCREEN_MARGIN_X
        bar_w = WINDOW_WIDTH - 2 * ACHIEVEMENTS_SCREEN_MARGIN_X
        bar_h = 14
        pygame.draw.rect(
            self.screen, COLOR_ACHIEVEMENT_PROGRESS_BAR_BG,
            (bar_x, bar_y, bar_w, bar_h),
        )
        if total > 0:
            fill_w = int(bar_w * unlocked / total)
            if fill_w > 0:
                pygame.draw.rect(
                    self.screen, COLOR_ACHIEVEMENT_PROGRESS_BAR,
                    (bar_x, bar_y, fill_w, bar_h),
                )
        pygame.draw.rect(
            self.screen, COLOR_RECORDS_HEADER,
            (bar_x, bar_y, bar_w, bar_h), 1,
        )

    def _draw_stats_section(self, y: int, stats: dict[str, Any], colors: ThemeColors) -> int:
        """Dibuja la seccion de estadisticas (General, Records, Emocional).

        Args:
            y:      Posicion Y inicial.
            stats:  dict de compute_derived_stats().
            colors: ThemeColors.

        Returns:
            int: posicion Y tras dibujar toda la seccion.
        """
        margin_x = ACHIEVEMENTS_SCREEN_MARGIN_X
        row_h = STATS_SECTION_ROW_HEIGHT
        label_font = self.records_font       # 18pt, ya existe
        value_font = self.records_font

        def _draw_row(yy: int, label: str, value: Any, value_color: tuple[int, int, int] = STATS_SECTION_VALUE_COLOR) -> int:
            """Dibuja una fila: label a la izquierda, valor a la derecha."""
            lbl = label_font.render(label, True, STATS_SECTION_LABEL_COLOR)
            self.screen.blit(lbl, (margin_x + 10, yy + 2))
            val = value_font.render(str(value), True, value_color)
            val_rect = val.get_rect(
                right=WINDOW_WIDTH - margin_x - 10, top=yy + 2,
            )
            self.screen.blit(val, val_rect)
            return yy + row_h

        # ---- GENERAL ----
        self._draw_gallery_category_header(y, "GENERAL", colors)
        y += ACHIEVEMENTS_SCREEN_CATEGORY_HEADER_HEIGHT + STATS_SECTION_HEADER_GAP

        y = _draw_row(y, "Partidas jugadas", stats["total_matches"])
        win_text = (
            f'{stats["total_victories"]} ({stats["win_rate"]}%)'
        )
        y = _draw_row(y, "Victorias", win_text)
        y = _draw_row(y, "Derrotas", stats["total_defeats"])
        y = _draw_row(
            y, "Tiempo total jugado", _format_time(stats["total_time"]),
        )
        y = _draw_row(y, "Puntos anotados", stats["total_points"])
        y = _draw_row(y, "Puntos del rival", stats["total_computer_points"])
        y = _draw_row(y, "Rally hits totales", stats["total_rallies"])
        y += STATS_SECTION_HEADER_GAP

        # ---- RECORDS ----
        self._draw_gallery_category_header(y, "RÉCORDS", colors)
        y += ACHIEVEMENTS_SCREEN_CATEGORY_HEADER_HEIGHT + STATS_SECTION_HEADER_GAP

        rc = STATS_SECTION_RECORD_COLOR
        y = _draw_row(y, "Rally más largo", stats["rec_longest_rally"], rc)
        y = _draw_row(y, "Mayor racha de puntos", stats["rec_longest_streak"], rc)
        y = _draw_row(y, "Mayor puntuación", stats["rec_max_score"], rc)
        y = _draw_row(y, "Victoria más rápida", stats["rec_fastest_win"], rc)
        y = _draw_row(
            y, "Mayor dominación", stats["rec_biggest_domination"], rc,
        )
        y += STATS_SECTION_HEADER_GAP

        # ---- EMOCIONAL ----
        self._draw_gallery_category_header(y, "EMOCIONAL", colors)
        y += ACHIEVEMENTS_SCREEN_CATEGORY_HEADER_HEIGHT + STATS_SECTION_HEADER_GAP

        moods = stats["moods_experienced"]
        mood_count = len(moods)
        mood_total = stats["moods_total"]
        y = _draw_row(
            y, "Estados de ánimo vistos",
            f"{mood_count}/{mood_total}",
            STATS_SECTION_MOOD_COLOR,
        )
        if moods:
            mood_list = ", ".join(moods)
            mood_surface = label_font.render(
                mood_list, True, STATS_SECTION_MOOD_COLOR,
            )
            self.screen.blit(mood_surface, (margin_x + 20, y + 2))
            y += row_h

        return y

    def _draw_gallery_category_header(self, y: int, text: str, colors: ThemeColors) -> None:
        """Dibuja la cabecera de una categoria con lineas horizontales."""
        surface = self.achievement_category_font.render(
            text, True, COLOR_ACHIEVEMENT_CATEGORY_HEADER,
        )
        text_rect = surface.get_rect(
            centerx=WINDOW_WIDTH // 2, top=y + 4,
        )

        # Lineas a los lados del texto
        line_y = text_rect.centery
        pygame.draw.line(
            self.screen, COLOR_ACHIEVEMENT_CATEGORY_HEADER,
            (ACHIEVEMENTS_SCREEN_MARGIN_X, line_y),
            (text_rect.left - 10, line_y), 1,
        )
        pygame.draw.line(
            self.screen, COLOR_ACHIEVEMENT_CATEGORY_HEADER,
            (text_rect.right + 10, line_y),
            (WINDOW_WIDTH - ACHIEVEMENTS_SCREEN_MARGIN_X, line_y), 1,
        )
        self.screen.blit(surface, text_rect)

    def _draw_achievement_tile(self, x: int, y: int, adef: AchievementDef, is_unlocked: bool) -> None:
        """Dibuja un tile individual de logro (desbloqueado o bloqueado)."""
        tile_rect = pygame.Rect(
            x, y, ACHIEVEMENT_TILE_WIDTH, ACHIEVEMENT_TILE_HEIGHT,
        )
        pad = ACHIEVEMENT_TILE_PADDING
        icon_size = 24
        icon_x = x + pad
        icon_y = y + (ACHIEVEMENT_TILE_HEIGHT - icon_size) // 2
        text_x = icon_x + icon_size + 8
        max_text_w = x + ACHIEVEMENT_TILE_WIDTH - pad - text_x

        if is_unlocked:
            # Fondo y borde verde
            pygame.draw.rect(
                self.screen, COLOR_ACHIEVEMENT_UNLOCKED_BG, tile_rect,
            )
            pygame.draw.rect(
                self.screen, COLOR_ACHIEVEMENT_UNLOCKED_BORDER,
                tile_rect, ACHIEVEMENT_TILE_BORDER_WIDTH,
            )

            icon = get_icon(adef, unlocked=True, scale=1)
            self.screen.blit(icon, (icon_x, icon_y))

            # Linea 1: estrella + nombre
            name_text = f"\u2605 {adef.name}"
            name_surface = self.achievement_tile_name_font.render(
                name_text, True, COLOR_ACHIEVEMENT_UNLOCKED_NAME,
            )
            self.screen.blit(name_surface, (text_x, y + pad))

            # Linea 2: flavor text (truncado si es necesario)
            flavor = adef.flavor
            flavor_surface = self.achievement_tile_desc_font.render(
                flavor, True, COLOR_ACHIEVEMENT_UNLOCKED_FLAVOR,
            )
            if flavor_surface.get_width() > max_text_w:
                while (flavor
                       and self.achievement_tile_desc_font.size(
                           flavor + "...")[0] > max_text_w):
                    flavor = flavor[:-1]
                flavor += "..."
                flavor_surface = self.achievement_tile_desc_font.render(
                    flavor, True, COLOR_ACHIEVEMENT_UNLOCKED_FLAVOR,
                )
            self.screen.blit(flavor_surface, (text_x, y + pad + 18))

            # Linea 3: descripcion
            desc = adef.description
            desc_surface = self.achievement_tile_desc_font.render(
                desc, True, COLOR_ACHIEVEMENT_UNLOCKED_DESC,
            )
            if desc_surface.get_width() > max_text_w:
                while (desc
                       and self.achievement_tile_desc_font.size(
                           desc + "...")[0] > max_text_w):
                    desc = desc[:-1]
                desc += "..."
                desc_surface = self.achievement_tile_desc_font.render(
                    desc, True, COLOR_ACHIEVEMENT_UNLOCKED_DESC,
                )
            self.screen.blit(desc_surface, (text_x, y + pad + 32))
        else:
            # Fondo y borde oscuro
            pygame.draw.rect(
                self.screen, COLOR_ACHIEVEMENT_LOCKED_BG, tile_rect,
            )
            pygame.draw.rect(
                self.screen, COLOR_ACHIEVEMENT_LOCKED_BORDER,
                tile_rect, ACHIEVEMENT_TILE_BORDER_WIDTH,
            )

            icon = get_icon(adef, unlocked=False, scale=1)
            self.screen.blit(icon, (icon_x, icon_y))

            if adef.hidden:
                # Logro secreto: todo "???"
                name_surface = self.achievement_tile_name_font.render(
                    "? ???", True, COLOR_ACHIEVEMENT_LOCKED_MYSTERY,
                )
                self.screen.blit(name_surface, (text_x, y + pad))

                desc_surface = self.achievement_tile_desc_font.render(
                    "???", True, COLOR_ACHIEVEMENT_LOCKED_MYSTERY,
                )
                self.screen.blit(desc_surface, (text_x, y + pad + 18))
            else:
                # Logro bloqueado pero visible
                name_surface = self.achievement_tile_name_font.render(
                    f"? {adef.name}", True, COLOR_ACHIEVEMENT_LOCKED_TEXT,
                )
                self.screen.blit(name_surface, (text_x, y + pad))

                desc = adef.description
                desc_surface = self.achievement_tile_desc_font.render(
                    desc, True, COLOR_ACHIEVEMENT_LOCKED_TEXT,
                )
                if desc_surface.get_width() > max_text_w:
                    while (desc
                           and self.achievement_tile_desc_font.size(
                               desc + "...")[0] > max_text_w):
                        desc = desc[:-1]
                    desc += "..."
                    desc_surface = self.achievement_tile_desc_font.render(
                        desc, True, COLOR_ACHIEVEMENT_LOCKED_TEXT,
                    )
                self.screen.blit(desc_surface, (text_x, y + pad + 18))
