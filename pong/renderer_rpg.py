"""
pong/renderer_rpg.py -- Mixin de renderizado RPG.

Contiene los metodos de dibujado de:
- Barra de XP durante el gameplay.
- Pantalla de habilidades (overlay desde pantalla final).
- Pantalla de ascension (overlay desde pantalla final).
- Prediccion de trayectoria (habilidad de ascension).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from pong.entities import Ball
    from pong.rpg_engine import RPGState

from pong.config.layout import (
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    XP_BAR_HEIGHT,
    XP_BAR_TOP,
    GAME_AREA_TOP,
    GAME_AREA_HEIGHT,
)
from pong.config.rpg import (
    ASCENSION_MIN_POINTS,
    ASCENSION_SKILL_MAX_LEVEL,
    RPG_SKILLS,
    RPG_ASCENSION_SKILLS,
    XP_BAR_BG_COLOR,
    XP_BAR_BORDER_COLOR,
    XP_BAR_COLOR,
    XP_LEVEL_COLOR,
    XP_TEXT_FONT_SIZE,
)
from pong.config.ui_rpg import (
    ASCENSION_CARD_GAP_Y,
    ASCENSION_CARD_HEIGHT,
    ASCENSION_CARD_WIDTH,
    ASCENSION_SCREEN_HEADER_HEIGHT,
    ASCENSION_SCREEN_MARGIN_TOP,
    ASCENSION_SCREEN_MARGIN_X,
    COLOR_ASCENSION_BUTTON_BG,
    COLOR_ASCENSION_BUTTON_BORDER,
    COLOR_ASCENSION_BUTTON_HOVER_BG,
    COLOR_ASCENSION_BUTTON_TEXT,
    COLOR_ASCENSION_CONFIRM_BG,
    COLOR_ASCENSION_CONFIRM_HOVER_BG,
    COLOR_ASCENSION_GOLD,
    COLOR_ASCENSION_GOLD_DARK,
    COLOR_SKILL_AVAILABLE_BG,
    COLOR_SKILL_AVAILABLE_BORDER,
    COLOR_SKILL_BUY_BG,
    COLOR_SKILL_BUY_HOVER_BG,
    COLOR_SKILL_COST,
    COLOR_SKILL_DESC,
    COLOR_SKILL_LOCKED_BG,
    COLOR_SKILL_LOCKED_BORDER,
    COLOR_SKILL_LOCKED_TEXT,
    COLOR_SKILL_NAME,
    COLOR_SKILL_PURCHASED_BG,
    COLOR_SKILL_PURCHASED_BORDER,
    COLOR_SKILL_PURCHASED_TEXT,
    COLOR_SKILLS_BUTTON_BG,
    COLOR_SKILLS_BUTTON_BORDER,
    COLOR_SKILLS_BUTTON_HOVER_BG,
    END_SCREEN_ASCENSION_BUTTON_HEIGHT,
    END_SCREEN_ASCENSION_BUTTON_TEXT,
    END_SCREEN_ASCENSION_BUTTON_WIDTH,
    END_SCREEN_SKILLS_BUTTON_HEIGHT,
    END_SCREEN_SKILLS_BUTTON_TEXT,
    END_SCREEN_SKILLS_BUTTON_WIDTH,
    RPG_BACK_BUTTON_HEIGHT,
    RPG_BACK_BUTTON_MARGIN_TOP,
    RPG_BACK_BUTTON_TEXT,
    RPG_BACK_BUTTON_WIDTH,
    SKILL_BUY_BUTTON_HEIGHT,
    SKILL_BUY_BUTTON_WIDTH,
    SKILL_CARD_BORDER_WIDTH,
    SKILL_CARD_GAP_Y,
    SKILL_CARD_HEIGHT,
    SKILL_CARD_PADDING,
    SKILL_CARD_WIDTH,
    SKILLS_SCREEN_HEADER_HEIGHT,
    SKILLS_SCREEN_MARGIN_TOP,
    SKILLS_SCREEN_MARGIN_X,
)
from pong.config.zx_spectrum import ZX_BLACK, ZX_WHITE, ZX_YELLOW
from pong.theme import ThemeColors


class RPGRendererMixin:
    """Mixin: barra XP, pantalla habilidades, pantalla ascension."""

    # -- Atributos declarados en Renderer, visibles aqui para mypy --
    screen: pygame.Surface
    font: pygame.font.Font
    copy_button_font: pygame.font.Font
    records_font: pygame.font.Font

    # Rects de botones RPG (inicializados como None)
    skills_button_rect: pygame.Rect | None
    ascension_button_rect: pygame.Rect | None
    skills_back_button_rect: pygame.Rect | None
    ascension_back_button_rect: pygame.Rect | None
    ascension_confirm_button_rect: pygame.Rect | None
    ascension_dialog_accept_rect: pygame.Rect | None
    ascension_dialog_cancel_rect: pygame.Rect | None
    skill_buy_rects: list[tuple[str, pygame.Rect]]
    ascension_buy_rects: list[tuple[str, pygame.Rect]]

    # Fuentes RPG
    xp_font: pygame.font.Font
    skill_name_font: pygame.font.Font
    skill_desc_font: pygame.font.Font

    def _init_rpg_renderer(self) -> None:
        """Inicializa fuentes y rects del sistema RPG."""
        self.xp_font = pygame.font.Font(None, XP_TEXT_FONT_SIZE)
        self.skill_name_font = pygame.font.Font(None, 22)
        self.skill_desc_font = pygame.font.Font(None, 18)
        self.skills_button_rect = None
        self.ascension_button_rect = None
        self.skills_back_button_rect = None
        self.ascension_back_button_rect = None
        self.ascension_confirm_button_rect = None
        self.ascension_dialog_accept_rect = None
        self.ascension_dialog_cancel_rect = None
        self.skill_buy_rects = []
        self.ascension_buy_rects = []

    # ================================================================
    # BARRA DE XP (durante gameplay)
    # ================================================================

    def draw_xp_bar(
        self,
        rpg: RPGState,
        colors: ThemeColors | None = None,
    ) -> None:
        """Dibuja la barra de XP entre el campo de juego y la narracion."""
        if not rpg.rpg_unlocked:
            # Zona vacia con fondo de narracion
            narr_bg = colors.narration_bg if colors else (20, 20, 20)
            pygame.draw.rect(
                self.screen, narr_bg,
                (0, XP_BAR_TOP, WINDOW_WIDTH, XP_BAR_HEIGHT),
            )
            return

        level, xp_in_level, xp_needed = rpg.get_level_progress()
        progress = min(xp_in_level / xp_needed, 1.0) if xp_needed > 0 else 1.0

        # Fondo de la barra
        pygame.draw.rect(
            self.screen, XP_BAR_BG_COLOR,
            (0, XP_BAR_TOP, WINDOW_WIDTH, XP_BAR_HEIGHT),
        )

        # Borde superior e inferior
        pygame.draw.line(
            self.screen, XP_BAR_BORDER_COLOR,
            (0, XP_BAR_TOP), (WINDOW_WIDTH, XP_BAR_TOP),
        )
        pygame.draw.line(
            self.screen, XP_BAR_BORDER_COLOR,
            (0, XP_BAR_TOP + XP_BAR_HEIGHT - 1),
            (WINDOW_WIDTH, XP_BAR_TOP + XP_BAR_HEIGHT - 1),
        )

        # Texto nivel (izquierda)
        level_text = f"Nv. {level}"
        level_surf = self.xp_font.render(level_text, True, XP_LEVEL_COLOR)
        level_x = 10
        level_y = XP_BAR_TOP + (XP_BAR_HEIGHT - level_surf.get_height()) // 2
        self.screen.blit(level_surf, (level_x, level_y))

        # Barra de progreso
        bar_left = level_x + level_surf.get_width() + 10
        bar_right = WINDOW_WIDTH - 10
        xp_text = f"{int(xp_in_level)} / {int(xp_needed)}"
        xp_surf = self.xp_font.render(xp_text, True, XP_BAR_COLOR)
        bar_right = WINDOW_WIDTH - xp_surf.get_width() - 15

        bar_y = XP_BAR_TOP + 5
        bar_h = XP_BAR_HEIGHT - 10
        bar_w = bar_right - bar_left - 5

        if bar_w > 0:
            # Fondo de la barra
            pygame.draw.rect(
                self.screen, (15, 15, 40),
                (bar_left, bar_y, bar_w, bar_h),
            )
            # Relleno
            fill_w = int(bar_w * progress)
            if fill_w > 0:
                pygame.draw.rect(
                    self.screen, XP_BAR_COLOR,
                    (bar_left, bar_y, fill_w, bar_h),
                )
            # Borde de la barra
            pygame.draw.rect(
                self.screen, XP_BAR_BORDER_COLOR,
                (bar_left, bar_y, bar_w, bar_h), 1,
            )

        # Texto XP (derecha)
        xp_x = WINDOW_WIDTH - xp_surf.get_width() - 10
        xp_y = XP_BAR_TOP + (XP_BAR_HEIGHT - xp_surf.get_height()) // 2
        self.screen.blit(xp_surf, (xp_x, xp_y))

    # ================================================================
    # BOTONES EN PANTALLA FINAL
    # ================================================================

    def _draw_skills_button(
        self,
        x: int,
        y: int,
        hovered: bool,
    ) -> None:
        """Dibuja el boton 'Habilidades' (magenta) en la pantalla final."""
        rect = pygame.Rect(
            x, y,
            END_SCREEN_SKILLS_BUTTON_WIDTH,
            END_SCREEN_SKILLS_BUTTON_HEIGHT,
        )
        self.skills_button_rect = rect

        bg = COLOR_SKILLS_BUTTON_HOVER_BG if hovered else COLOR_SKILLS_BUTTON_BG
        pygame.draw.rect(self.screen, bg, rect)
        pygame.draw.rect(self.screen, COLOR_SKILLS_BUTTON_BORDER, rect, 2)

        text_surf = self.copy_button_font.render(
            END_SCREEN_SKILLS_BUTTON_TEXT, True, ZX_WHITE,
        )
        text_x = rect.x + (rect.width - text_surf.get_width()) // 2
        text_y = rect.y + (rect.height - text_surf.get_height()) // 2
        self.screen.blit(text_surf, (text_x, text_y))

    def _draw_ascension_button(
        self,
        x: int,
        y: int,
        hovered: bool,
    ) -> None:
        """Dibuja el boton 'Ascender' (dorado) en la pantalla final."""
        rect = pygame.Rect(
            x, y,
            END_SCREEN_ASCENSION_BUTTON_WIDTH,
            END_SCREEN_ASCENSION_BUTTON_HEIGHT,
        )
        self.ascension_button_rect = rect

        bg = COLOR_ASCENSION_BUTTON_HOVER_BG if hovered else COLOR_ASCENSION_BUTTON_BG
        pygame.draw.rect(self.screen, bg, rect)
        pygame.draw.rect(self.screen, COLOR_ASCENSION_BUTTON_BORDER, rect, 2)

        text_color = ZX_BLACK if hovered else COLOR_ASCENSION_BUTTON_TEXT
        text_surf = self.copy_button_font.render(
            END_SCREEN_ASCENSION_BUTTON_TEXT, True, text_color,
        )
        text_x = rect.x + (rect.width - text_surf.get_width()) // 2
        text_y = rect.y + (rect.height - text_surf.get_height()) // 2
        self.screen.blit(text_surf, (text_x, text_y))

    # ================================================================
    # PANTALLA DE HABILIDADES (overlay)
    # ================================================================

    def draw_skills_screen(
        self,
        rpg: RPGState,
        scroll: int,
        mouse_pos: tuple[int, int],
    ) -> None:
        """Dibuja la pantalla completa de habilidades RPG."""
        self.skill_buy_rects = []

        # Fondo
        self.screen.fill(ZX_BLACK)

        mx, my = mouse_pos
        x0 = SKILLS_SCREEN_MARGIN_X
        y = SKILLS_SCREEN_MARGIN_TOP - scroll

        # Boton volver (fijo, no scrollea)
        back_rect = pygame.Rect(
            x0, RPG_BACK_BUTTON_MARGIN_TOP,
            RPG_BACK_BUTTON_WIDTH, RPG_BACK_BUTTON_HEIGHT,
        )
        self.skills_back_button_rect = back_rect
        back_hovered = back_rect.collidepoint(mx, my)
        bg = (35, 35, 35) if back_hovered else (10, 10, 10)
        pygame.draw.rect(self.screen, bg, back_rect)
        pygame.draw.rect(self.screen, ZX_WHITE, back_rect, 1)
        back_text = self.copy_button_font.render(RPG_BACK_BUTTON_TEXT, True, ZX_WHITE)
        self.screen.blit(
            back_text,
            (back_rect.x + (back_rect.width - back_text.get_width()) // 2,
             back_rect.y + (back_rect.height - back_text.get_height()) // 2),
        )

        # Titulo
        y = SKILLS_SCREEN_MARGIN_TOP + RPG_BACK_BUTTON_HEIGHT + 10 - scroll
        title_surf = self.font.render("HABILIDADES RPG", True, ZX_YELLOW)
        self.screen.blit(
            title_surf,
            ((WINDOW_WIDTH - title_surf.get_width()) // 2, y),
        )
        y += title_surf.get_height() + 8

        # Balance de segundos
        balance_text = f"Segundos disponibles: {rpg.skill_seconds_balance:.1f}s"
        balance_surf = self.skill_name_font.render(balance_text, True, XP_LEVEL_COLOR)
        self.screen.blit(balance_surf, (x0, y))

        # Nivel actual
        level_text = f"Nivel: {rpg.level}"
        level_surf = self.skill_name_font.render(level_text, True, XP_BAR_COLOR)
        self.screen.blit(level_surf, (WINDOW_WIDTH - x0 - level_surf.get_width(), y))
        y += balance_surf.get_height() + 12

        # Tarjetas de habilidades
        for skill_def in RPG_SKILLS:
            skill_id = skill_def["id"]
            cost = skill_def["cost"]
            unlock_level = skill_def["unlock_level"]
            name = skill_def["name"]
            desc = skill_def["description"]

            is_purchased = rpg.is_skill_active(skill_id)  # type: ignore[arg-type]
            is_unlocked = rpg.is_skill_unlocked(skill_id)  # type: ignore[arg-type]
            can_buy = rpg.can_buy_skill(skill_id)  # type: ignore[arg-type]

            card_rect = pygame.Rect(x0, y, SKILL_CARD_WIDTH, SKILL_CARD_HEIGHT)

            # Color de fondo y borde segun estado
            if is_purchased:
                bg_color = COLOR_SKILL_PURCHASED_BG
                border_color = COLOR_SKILL_PURCHASED_BORDER
            elif is_unlocked:
                bg_color = COLOR_SKILL_AVAILABLE_BG
                border_color = COLOR_SKILL_AVAILABLE_BORDER
            else:
                bg_color = COLOR_SKILL_LOCKED_BG
                border_color = COLOR_SKILL_LOCKED_BORDER

            pygame.draw.rect(self.screen, bg_color, card_rect)
            pygame.draw.rect(self.screen, border_color, card_rect, SKILL_CARD_BORDER_WIDTH)

            # Nombre
            name_surf = self.skill_name_font.render(str(name), True, COLOR_SKILL_NAME)
            self.screen.blit(
                name_surf,
                (x0 + SKILL_CARD_PADDING, y + SKILL_CARD_PADDING),
            )

            if not is_unlocked:
                # Bloqueada
                lock_text = f"Requiere Nv. {unlock_level}"
                lock_surf = self.skill_desc_font.render(
                    lock_text, True, COLOR_SKILL_LOCKED_TEXT,
                )
                self.screen.blit(
                    lock_surf,
                    (x0 + SKILL_CARD_PADDING,
                     y + SKILL_CARD_PADDING + name_surf.get_height() + 2),
                )
            else:
                # Descripcion
                desc_surf = self.skill_desc_font.render(
                    str(desc), True, COLOR_SKILL_DESC,
                )
                # Truncar si es muy larga
                max_desc_w = SKILL_CARD_WIDTH - SKILL_CARD_PADDING * 2 - SKILL_BUY_BUTTON_WIDTH - 10
                if desc_surf.get_width() > max_desc_w:
                    # Recortar
                    desc_surf = desc_surf.subsurface(
                        (0, 0, max_desc_w, desc_surf.get_height())
                    )
                self.screen.blit(
                    desc_surf,
                    (x0 + SKILL_CARD_PADDING,
                     y + SKILL_CARD_PADDING + name_surf.get_height() + 2),
                )

                if is_purchased:
                    # Etiqueta ACTIVA
                    active_surf = self.skill_name_font.render(
                        "ACTIVA", True, COLOR_SKILL_PURCHASED_TEXT,
                    )
                    self.screen.blit(
                        active_surf,
                        (x0 + SKILL_CARD_WIDTH - SKILL_CARD_PADDING - active_surf.get_width(),
                         y + (SKILL_CARD_HEIGHT - active_surf.get_height()) // 2),
                    )
                else:
                    # Boton COMPRAR
                    buy_rect = pygame.Rect(
                        x0 + SKILL_CARD_WIDTH - SKILL_CARD_PADDING - SKILL_BUY_BUTTON_WIDTH,
                        y + (SKILL_CARD_HEIGHT - SKILL_BUY_BUTTON_HEIGHT) // 2,
                        SKILL_BUY_BUTTON_WIDTH,
                        SKILL_BUY_BUTTON_HEIGHT,
                    )
                    buy_hovered = buy_rect.collidepoint(mx, my) and can_buy
                    buy_bg = COLOR_SKILL_BUY_HOVER_BG if buy_hovered else COLOR_SKILL_BUY_BG
                    if not can_buy:
                        buy_bg = (30, 30, 30)

                    pygame.draw.rect(self.screen, buy_bg, buy_rect)
                    pygame.draw.rect(self.screen, COLOR_SKILL_COST, buy_rect, 1)

                    buy_text = f"COMPRAR ({cost}s)"
                    buy_color = ZX_WHITE if can_buy else COLOR_SKILL_LOCKED_TEXT
                    buy_surf = self.skill_desc_font.render(buy_text, True, buy_color)
                    self.screen.blit(
                        buy_surf,
                        (buy_rect.x + (buy_rect.width - buy_surf.get_width()) // 2,
                         buy_rect.y + (buy_rect.height - buy_surf.get_height()) // 2),
                    )

                    if can_buy:
                        self.skill_buy_rects.append((skill_id, buy_rect))  # type: ignore[arg-type]

            y += SKILL_CARD_HEIGHT + SKILL_CARD_GAP_Y

    @staticmethod
    def _format_ascension_desc(skill_def: dict[str, object], level: int) -> str:
        """Formatea la descripcion de una habilidad de ascension para un nivel."""
        sid = skill_def["id"]
        if sid == "veteran_start":
            return f"XP por segundo x{1.0 + 0.1 * level:.1f}"
        if sid == "persistent_memory":
            return f"+{3.0 * level:.0f}s de XP bonus al anotar punto"
        if sid == "legacy_paddle":
            return f"+{8 * level}px tamano de pala permanente"
        if sid == "rival_reading":
            return f"Trayectoria visible ({40 * level}px)"
        if sid == "master_spin":
            return f"Efectos de pelota x{1.0 + 0.2 * level:.1f}"
        if sid == "superior_reflex":
            return f"+{1 * level} velocidad maxima de pala"
        if sid == "hacker":
            chance = 0.10 + 0.03 * level
            offset = 10 + 3 * level
            return f"IA falla {chance * 100:.0f}% (5-{offset}px)"
        if sid == "critical_hit":
            chance = 0.10 + 0.03 * level
            mult = 1.5 + 0.1 * level
            return f"{chance * 100:.0f}% prob. de golpe a x{mult:.1f}"
        if sid == "victory_echo":
            return f"+{5.0 * level:.0f}s de habilidad al anotar"
        if sid == "sovereign":
            xp_pct = 5 * level
            sec_pct = 8 * level
            return f"Conservar {xp_pct}% XP y {sec_pct}% segundos al ascender"
        return str(skill_def.get("description", ""))

    # ================================================================
    # DIALOGO DE CONFIRMACION DE ASCENSION
    # ================================================================

    def draw_ascension_confirm_dialog(
        self,
        mouse_pos: tuple[int, int],
    ) -> None:
        """Dibuja el dialogo de confirmacion de ascension sobre la end screen."""
        mx, my = mouse_pos

        # Fondo semitransparente
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        # Caja del dialogo
        box_w, box_h = 500, 220
        box_x = (WINDOW_WIDTH - box_w) // 2
        box_y = (WINDOW_HEIGHT - box_h) // 2
        box_rect = pygame.Rect(box_x, box_y, box_w, box_h)
        pygame.draw.rect(self.screen, ZX_BLACK, box_rect)
        pygame.draw.rect(self.screen, COLOR_ASCENSION_GOLD, box_rect, 2)

        # Titulo
        title = self.font.render("ASCENSION", True, COLOR_ASCENSION_GOLD)
        self.screen.blit(
            title,
            (box_x + (box_w - title.get_width()) // 2, box_y + 16),
        )

        # Mensaje de advertencia (varias lineas)
        warn_lines = [
            "Al ascender se reiniciara tu nivel, XP",
            "y todas las habilidades normales.",
            "",
            "Podras comprar habilidades de ascension",
            "permanentes con tus puntos acumulados.",
            "",
            "Esta decision NO es reversible.",
        ]
        y = box_y + 16 + title.get_height() + 10
        for line in warn_lines:
            if line:
                color = (255, 85, 85) if "NO es reversible" in line else ZX_WHITE
                surf = self.skill_desc_font.render(line, True, color)
                self.screen.blit(
                    surf, (box_x + (box_w - surf.get_width()) // 2, y),
                )
            y += 16

        # Botones
        btn_w, btn_h = 140, 34
        gap = 30
        total_w = btn_w * 2 + gap
        btn_y = box_y + box_h - btn_h - 18

        # Boton Aceptar (dorado)
        accept_x = box_x + (box_w - total_w) // 2
        accept_rect = pygame.Rect(accept_x, btn_y, btn_w, btn_h)
        self.ascension_dialog_accept_rect = accept_rect
        accept_hover = accept_rect.collidepoint(mx, my)
        a_bg = COLOR_ASCENSION_CONFIRM_HOVER_BG if accept_hover else COLOR_ASCENSION_CONFIRM_BG
        pygame.draw.rect(self.screen, a_bg, accept_rect)
        pygame.draw.rect(self.screen, COLOR_ASCENSION_GOLD, accept_rect, 1)
        a_color = ZX_BLACK if accept_hover else COLOR_ASCENSION_GOLD
        a_surf = self.copy_button_font.render("Aceptar", True, a_color)
        self.screen.blit(
            a_surf,
            (accept_rect.x + (btn_w - a_surf.get_width()) // 2,
             accept_rect.y + (btn_h - a_surf.get_height()) // 2),
        )

        # Boton Cancelar (gris)
        cancel_x = accept_x + btn_w + gap
        cancel_rect = pygame.Rect(cancel_x, btn_y, btn_w, btn_h)
        self.ascension_dialog_cancel_rect = cancel_rect
        cancel_hover = cancel_rect.collidepoint(mx, my)
        c_bg = (50, 50, 50) if cancel_hover else (25, 25, 25)
        pygame.draw.rect(self.screen, c_bg, cancel_rect)
        pygame.draw.rect(self.screen, ZX_WHITE, cancel_rect, 1)
        c_surf = self.copy_button_font.render("Cancelar", True, ZX_WHITE)
        self.screen.blit(
            c_surf,
            (cancel_rect.x + (btn_w - c_surf.get_width()) // 2,
             cancel_rect.y + (btn_h - c_surf.get_height()) // 2),
        )

    # ================================================================
    # PANTALLA DE ASCENSION (overlay)
    # ================================================================

    def draw_ascension_screen(
        self,
        rpg: RPGState,
        scroll: int,
        mouse_pos: tuple[int, int],
    ) -> None:
        """Dibuja la pantalla completa de ascension."""
        self.ascension_buy_rects = []

        # Fondo
        self.screen.fill(ZX_BLACK)

        mx, my = mouse_pos
        x0 = ASCENSION_SCREEN_MARGIN_X

        # Sin boton volver: la ascension es irreversible
        self.ascension_back_button_rect = None

        # Titulo
        y = ASCENSION_SCREEN_MARGIN_TOP + 10 - scroll
        title_surf = self.font.render("ASCENSION", True, COLOR_ASCENSION_GOLD)
        self.screen.blit(
            title_surf,
            ((WINDOW_WIDTH - title_surf.get_width()) // 2, y),
        )
        y += title_surf.get_height() + 8

        # Aviso
        warn_text = "Ascender reinicia nivel, XP y habilidades normales."
        warn_surf = self.skill_desc_font.render(warn_text, True, (255, 85, 85))
        self.screen.blit(warn_surf, ((WINDOW_WIDTH - warn_surf.get_width()) // 2, y))
        y += warn_surf.get_height() + 8

        # Stats
        stats_lines = [
            f"Nivel actual: {rpg.level}  |  Ascensiones: {rpg.ascension_count}",
            f"Puntos de ascension disponibles: {rpg.ascension_points_available}  "
            f"(total historico: {rpg.ascension_points_total})",
        ]
        for line in stats_lines:
            line_surf = self.skill_name_font.render(line, True, COLOR_ASCENSION_GOLD)
            self.screen.blit(line_surf, (x0, y))
            y += line_surf.get_height() + 4

        y += 8

        # Tarjetas de habilidades de ascension
        for skill_def in RPG_ASCENSION_SKILLS:
            skill_id = skill_def["id"]
            base_cost: int = skill_def["base_cost"]  # type: ignore[assignment]
            max_lvl: int = skill_def.get("max_level", ASCENSION_SKILL_MAX_LEVEL)  # type: ignore[assignment]
            name = skill_def["name"]
            desc_template: str = skill_def["description"]  # type: ignore[assignment]

            current_level = rpg.get_ascension_level(skill_id)  # type: ignore[arg-type]
            is_maxed = current_level >= max_lvl
            can_buy = rpg.can_buy_ascension_skill(skill_id)  # type: ignore[arg-type]
            next_cost = rpg.get_ascension_skill_cost(skill_id)  # type: ignore[arg-type]

            card_rect = pygame.Rect(x0, y, ASCENSION_CARD_WIDTH, ASCENSION_CARD_HEIGHT)

            if is_maxed:
                bg_color = COLOR_SKILL_PURCHASED_BG
                border_color = COLOR_ASCENSION_GOLD
            elif current_level > 0:
                bg_color = (20, 25, 15)
                border_color = COLOR_ASCENSION_GOLD_DARK
            elif can_buy:
                bg_color = (30, 25, 10)
                border_color = COLOR_ASCENSION_GOLD_DARK
            else:
                bg_color = COLOR_SKILL_LOCKED_BG
                border_color = COLOR_SKILL_LOCKED_BORDER

            pygame.draw.rect(self.screen, bg_color, card_rect)
            pygame.draw.rect(self.screen, border_color, card_rect, 1)

            # Nombre con nivel
            if current_level > 0:
                display_name = f"{name} (Nv. {current_level}/{max_lvl})"
            else:
                display_name = str(name)
            name_surf = self.skill_name_font.render(display_name, True, COLOR_ASCENSION_GOLD)
            self.screen.blit(
                name_surf,
                (x0 + SKILL_CARD_PADDING, y + SKILL_CARD_PADDING),
            )

            # Descripcion con valores del nivel actual/siguiente
            desc_text = self._format_ascension_desc(
                skill_def, current_level if current_level > 0 else 1,
            )
            desc_surf = self.skill_desc_font.render(desc_text, True, COLOR_SKILL_DESC)
            max_desc_w = ASCENSION_CARD_WIDTH - SKILL_CARD_PADDING * 2 - SKILL_BUY_BUTTON_WIDTH - 10
            if desc_surf.get_width() > max_desc_w:
                desc_surf = desc_surf.subsurface(
                    (0, 0, max_desc_w, desc_surf.get_height())
                )
            self.screen.blit(
                desc_surf,
                (x0 + SKILL_CARD_PADDING,
                 y + SKILL_CARD_PADDING + name_surf.get_height() + 2),
            )

            if is_maxed:
                max_surf = self.skill_name_font.render(
                    "MAX", True, COLOR_ASCENSION_GOLD,
                )
                self.screen.blit(
                    max_surf,
                    (x0 + ASCENSION_CARD_WIDTH - SKILL_CARD_PADDING - max_surf.get_width(),
                     y + (ASCENSION_CARD_HEIGHT - max_surf.get_height()) // 2),
                )
            else:
                buy_rect = pygame.Rect(
                    x0 + ASCENSION_CARD_WIDTH - SKILL_CARD_PADDING - SKILL_BUY_BUTTON_WIDTH,
                    y + (ASCENSION_CARD_HEIGHT - SKILL_BUY_BUTTON_HEIGHT) // 2,
                    SKILL_BUY_BUTTON_WIDTH,
                    SKILL_BUY_BUTTON_HEIGHT,
                )
                buy_hovered = buy_rect.collidepoint(mx, my) and can_buy
                buy_bg = COLOR_ASCENSION_CONFIRM_HOVER_BG if buy_hovered else COLOR_ASCENSION_CONFIRM_BG
                if not can_buy:
                    buy_bg = (30, 30, 30)

                pygame.draw.rect(self.screen, buy_bg, buy_rect)
                pygame.draw.rect(
                    self.screen,
                    COLOR_ASCENSION_GOLD if can_buy else COLOR_SKILL_LOCKED_BORDER,
                    buy_rect, 1,
                )

                buy_text = f"{next_cost} AP"
                buy_color = ZX_BLACK if (buy_hovered and can_buy) else (
                    COLOR_ASCENSION_GOLD if can_buy else COLOR_SKILL_LOCKED_TEXT
                )
                buy_surf = self.skill_desc_font.render(buy_text, True, buy_color)
                self.screen.blit(
                    buy_surf,
                    (buy_rect.x + (buy_rect.width - buy_surf.get_width()) // 2,
                     buy_rect.y + (buy_rect.height - buy_surf.get_height()) // 2),
                )

                if can_buy:
                    self.ascension_buy_rects.append((skill_id, buy_rect))  # type: ignore[arg-type]

            y += ASCENSION_CARD_HEIGHT + ASCENSION_CARD_GAP_Y

        # Boton ASCENDER (prominente)
        y += 12
        confirm_w = 200
        confirm_h = 40
        confirm_rect = pygame.Rect(
            (WINDOW_WIDTH - confirm_w) // 2, y,
            confirm_w, confirm_h,
        )
        self.ascension_confirm_button_rect = confirm_rect
        can_asc = rpg.can_ascend()
        confirm_hovered = confirm_rect.collidepoint(mx, my) and can_asc

        if can_asc:
            c_bg = COLOR_ASCENSION_CONFIRM_HOVER_BG if confirm_hovered else COLOR_ASCENSION_CONFIRM_BG
            c_border = COLOR_ASCENSION_GOLD
        else:
            c_bg = (30, 30, 30)
            c_border = COLOR_SKILL_LOCKED_BORDER

        pygame.draw.rect(self.screen, c_bg, confirm_rect)
        pygame.draw.rect(self.screen, c_border, confirm_rect, 2)

        asc_label = "ASCENDER" if can_asc else f"Necesitas {rpg.ascension_points_total}/{ASCENSION_MIN_POINTS} pts"
        asc_color = ZX_BLACK if confirm_hovered else (
            COLOR_ASCENSION_GOLD if can_asc else COLOR_SKILL_LOCKED_TEXT
        )
        asc_surf = self.copy_button_font.render(asc_label, True, asc_color)
        self.screen.blit(
            asc_surf,
            (confirm_rect.x + (confirm_rect.width - asc_surf.get_width()) // 2,
             confirm_rect.y + (confirm_rect.height - asc_surf.get_height()) // 2),
        )

    # ================================================================
    # PREDICCION DE TRAYECTORIA (habilidad de ascension: rival_reading)
    # ================================================================

    def draw_trajectory_prediction(
        self,
        ball: Ball,
        colors: ThemeColors | None = None,
        max_distance: float = 120.0,
    ) -> None:
        """Dibuja una linea punteada de prediccion de trayectoria."""
        if ball.speed_x == 0:
            return

        color = (85, 85, 85)  # Gris sutil
        x = float(ball.rect.centerx)
        y = float(ball.rect.centery)
        sx = float(ball.speed_x)
        sy = float(ball.speed_y)

        field_top = GAME_AREA_TOP
        field_bottom = GAME_AREA_TOP + GAME_AREA_HEIGHT

        total_distance = 0.0
        step = 4.0

        while total_distance < max_distance:
            x += sx * (step / abs(sx)) if sx != 0 else 0
            y += sy * (step / abs(sx)) if sx != 0 else step

            # Rebote en bordes superior/inferior
            if y < field_top:
                y = 2 * field_top - y
                sy = -sy
            elif y > field_bottom:
                y = 2 * field_bottom - y
                sy = -sy

            total_distance += step

            # Punto cada 8px
            if int(total_distance) % 8 < 4:
                px, py = int(x), int(y)
                if field_top <= py <= field_bottom and 0 <= px <= WINDOW_WIDTH:
                    pygame.draw.circle(self.screen, color, (px, py), 1)
