"""
pong/renderer_leaderboard.py -- Mixin de renderizado de rankings.

Contiene los metodos de dibujado de:
- Boton "Ranking" en la pantalla final.
- Pantalla de rankings/clasificaciones (overlay).
- Prompt de alias (input de texto).
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from pong.leaderboard import LeaderboardEntry

from pong.config.layout import WINDOW_HEIGHT, WINDOW_WIDTH
from pong.config.ui_leaderboard import (
    ALIAS_INPUT_HEIGHT,
    ALIAS_INPUT_WIDTH,
    ALIAS_MAX_LENGTH,
    ALIAS_PROMPT_HEIGHT,
    ALIAS_PROMPT_WIDTH,
    COLOR_ALIAS_ACCEPT_BG,
    COLOR_ALIAS_ACCEPT_HOVER_BG,
    COLOR_ALIAS_INPUT_BG,
    COLOR_ALIAS_INPUT_BORDER,
    COLOR_P2P_CONNECT_DETAIL,
    COLOR_P2P_CONNECT_OK,
    COLOR_P2P_CONNECT_SKIP,
    COLOR_P2P_CONNECT_TEXT,
    COLOR_RANKING_BUTTON_BG,
    COLOR_RANKING_BUTTON_BORDER,
    COLOR_RANKING_BUTTON_HOVER_BG,
    COLOR_RANKING_FOOTER,
    COLOR_RANKING_HEADER,
    COLOR_RANKING_PEER,
    COLOR_RANKING_SELF,
    COLOR_RANKING_SUSPICIOUS,
    COLOR_RANKING_TAB_ACTIVE,
    COLOR_RANKING_TAB_HOVER,
    COLOR_RANKING_TAB_INACTIVE,
    END_SCREEN_RANKING_BUTTON_HEIGHT,
    END_SCREEN_RANKING_BUTTON_TEXT,
    END_SCREEN_RANKING_BUTTON_WIDTH,
    P2P_CONNECT_MIN_SECONDS,
    RANKING_BACK_BUTTON_HEIGHT,
    RANKING_BACK_BUTTON_TEXT,
    RANKING_BACK_BUTTON_WIDTH,
    RANKING_CARD_GAP_Y,
    RANKING_ROW_HEIGHT,
    RANKING_SCREEN_HEADER_HEIGHT,
    RANKING_SCREEN_MARGIN_TOP,
    RANKING_SCREEN_MARGIN_X,
    RANKING_TAB_GAP,
    RANKING_TAB_HEIGHT,
    RANKING_TAB_WIDTH,
)
from pong.config.zx_spectrum import ZX_BLACK, ZX_WHITE, ZX_YELLOW
from pong.save_manager import RECORD_CATEGORIES

# Etiquetas cortas para las pestanas
_TAB_LABELS = [label for _key, label in RECORD_CATEGORIES]


class LeaderboardRendererMixin:
    """Mixin: boton de ranking, pantalla de clasificaciones, prompt de alias."""

    # -- Atributos declarados en Renderer, visibles aqui para mypy --
    screen: pygame.Surface
    font: pygame.font.Font
    copy_button_font: pygame.font.Font
    records_font: pygame.font.Font

    # Rects de botones del leaderboard
    ranking_button_rect: pygame.Rect | None
    ranking_back_button_rect: pygame.Rect | None
    ranking_tab_rects: list[pygame.Rect]
    alias_accept_button_rect: pygame.Rect | None
    p2p_continue_button_rect: pygame.Rect | None

    # Fuentes del leaderboard
    lb_title_font: pygame.font.Font
    lb_tab_font: pygame.font.Font
    lb_row_font: pygame.font.Font
    lb_footer_font: pygame.font.Font

    def _init_leaderboard_renderer(self) -> None:
        """Inicializa fuentes y rects del sistema de rankings."""
        self.lb_title_font = pygame.font.Font(None, 32)
        self.lb_tab_font = pygame.font.Font(None, 18)
        self.lb_row_font = pygame.font.Font(None, 22)
        self.lb_footer_font = pygame.font.Font(None, 18)
        self.ranking_button_rect = None
        self.ranking_back_button_rect = None
        self.ranking_tab_rects = []
        self.alias_accept_button_rect = None
        self.p2p_continue_button_rect = None

    # ================================================================
    # BOTON "RANKING" EN PANTALLA FINAL
    # ================================================================

    def _draw_ranking_button(
        self,
        x: int,
        y: int,
        hovered: bool,
    ) -> None:
        """Dibuja el boton 'Ranking' (azul) en la pantalla final."""
        rect = pygame.Rect(
            x, y,
            END_SCREEN_RANKING_BUTTON_WIDTH,
            END_SCREEN_RANKING_BUTTON_HEIGHT,
        )
        self.ranking_button_rect = rect

        bg = COLOR_RANKING_BUTTON_HOVER_BG if hovered else COLOR_RANKING_BUTTON_BG
        pygame.draw.rect(self.screen, bg, rect)
        pygame.draw.rect(self.screen, COLOR_RANKING_BUTTON_BORDER, rect, 2)

        text_surf = self.copy_button_font.render(
            END_SCREEN_RANKING_BUTTON_TEXT, True, ZX_WHITE,
        )
        text_x = rect.x + (rect.width - text_surf.get_width()) // 2
        text_y = rect.y + (rect.height - text_surf.get_height()) // 2
        self.screen.blit(text_surf, (text_x, text_y))

    # ================================================================
    # PANTALLA DE RANKINGS (overlay)
    # ================================================================

    def draw_leaderboard_screen(
        self,
        entries_by_category: dict[str, list[LeaderboardEntry]],
        active_tab: int,
        scroll: int,
        mouse_pos: tuple[int, int],
        peer_count: int = 0,
        network_active: bool = False,
        validated_date: str = "",
        p2p_degraded: bool = False,
    ) -> int:
        """Dibuja la pantalla completa de rankings. Retorna scroll actualizado."""
        self.ranking_tab_rects = []

        self.screen.fill(ZX_BLACK)
        mx, my = mouse_pos
        x0 = RANKING_SCREEN_MARGIN_X

        # -- Boton volver (fijo, no scrollea) --
        back_rect = pygame.Rect(
            x0, RANKING_SCREEN_MARGIN_TOP,
            RANKING_BACK_BUTTON_WIDTH, RANKING_BACK_BUTTON_HEIGHT,
        )
        self.ranking_back_button_rect = back_rect
        back_hovered = back_rect.collidepoint(mx, my)
        bg = (35, 35, 35) if back_hovered else (10, 10, 10)
        pygame.draw.rect(self.screen, bg, back_rect)
        pygame.draw.rect(self.screen, ZX_WHITE, back_rect, 1)
        back_text = self.copy_button_font.render(RANKING_BACK_BUTTON_TEXT, True, ZX_WHITE)
        self.screen.blit(
            back_text,
            (back_rect.x + (back_rect.width - back_text.get_width()) // 2,
             back_rect.y + (back_rect.height - back_text.get_height()) // 2),
        )

        # -- Titulo --
        title_surf = self.lb_title_font.render("RANKING", True, ZX_YELLOW)
        self.screen.blit(
            title_surf,
            ((WINDOW_WIDTH - title_surf.get_width()) // 2,
             RANKING_SCREEN_MARGIN_TOP + 4),
        )

        y = RANKING_SCREEN_MARGIN_TOP + RANKING_SCREEN_HEADER_HEIGHT

        # -- Pestanas --
        tab_total_width = len(_TAB_LABELS) * RANKING_TAB_WIDTH + (len(_TAB_LABELS) - 1) * RANKING_TAB_GAP
        tab_x = (WINDOW_WIDTH - tab_total_width) // 2
        for i, label in enumerate(_TAB_LABELS):
            tab_rect = pygame.Rect(tab_x, y, RANKING_TAB_WIDTH, RANKING_TAB_HEIGHT)
            self.ranking_tab_rects.append(tab_rect)

            hovered = tab_rect.collidepoint(mx, my)
            if i == active_tab:
                bg_color = COLOR_RANKING_TAB_ACTIVE
            elif hovered:
                bg_color = COLOR_RANKING_TAB_HOVER
            else:
                bg_color = COLOR_RANKING_TAB_INACTIVE

            pygame.draw.rect(self.screen, bg_color, tab_rect)
            pygame.draw.rect(self.screen, ZX_WHITE, tab_rect, 1)

            tab_surf = self.lb_tab_font.render(label, True, ZX_WHITE)
            self.screen.blit(
                tab_surf,
                (tab_rect.x + (tab_rect.width - tab_surf.get_width()) // 2,
                 tab_rect.y + (tab_rect.height - tab_surf.get_height()) // 2),
            )
            tab_x += RANKING_TAB_WIDTH + RANKING_TAB_GAP

        y += RANKING_TAB_HEIGHT + 12

        # -- Cabecera de la tabla --
        header_y = y
        col_rank_x = x0 + 10
        col_name_x = x0 + 50
        col_value_x = WINDOW_WIDTH - x0 - 200
        col_date_x = WINDOW_WIDTH - x0 - 90

        for label, lx in [("#", col_rank_x), ("Jugador", col_name_x),
                          ("Valor", col_value_x), ("Fecha", col_date_x)]:
            surf = self.lb_row_font.render(label, True, COLOR_RANKING_HEADER)
            self.screen.blit(surf, (lx, header_y))
        y += RANKING_ROW_HEIGHT + 4

        # Linea separadora
        pygame.draw.line(
            self.screen, COLOR_RANKING_HEADER,
            (x0, y), (WINDOW_WIDTH - x0, y), 1,
        )
        y += 4

        # -- Filas de la tabla --
        active_key = RECORD_CATEGORIES[active_tab][0] if active_tab < len(RECORD_CATEGORIES) else ""
        entries = entries_by_category.get(active_key, [])

        table_top = y
        max_visible = (WINDOW_HEIGHT - table_top - 50) // (RANKING_ROW_HEIGHT + RANKING_CARD_GAP_Y)

        # Scroll con rueda (aplicado externamente, aqui solo usamos el offset)
        visible_entries = entries[scroll:scroll + max_visible]
        max_scroll = max(0, len(entries) - max_visible)

        from pong.leaderboard import format_entry_date, format_entry_value

        for rank_offset, entry in enumerate(visible_entries):
            rank = scroll + rank_offset + 1
            row_y = y + rank_offset * (RANKING_ROW_HEIGHT + RANKING_CARD_GAP_Y)

            if entry.is_suspicious:
                color = COLOR_RANKING_SUSPICIOUS
            elif entry.is_local:
                color = COLOR_RANKING_SELF
            else:
                color = COLOR_RANKING_PEER

            # Fondo de fila (sutil)
            row_rect = pygame.Rect(x0, row_y - 2, WINDOW_WIDTH - 2 * x0, RANKING_ROW_HEIGHT)
            if entry.is_local:
                pygame.draw.rect(self.screen, (0, 30, 0), row_rect)

            # Rank
            rank_surf = self.lb_row_font.render(str(rank), True, color)
            self.screen.blit(rank_surf, (col_rank_x, row_y))

            # Nombre
            display_name = entry.display_alias or entry.alias
            if entry.is_local:
                display_name += " (tu)"
            name_surf = self.lb_row_font.render(display_name, True, color)
            self.screen.blit(name_surf, (col_name_x, row_y))

            # Valor
            val_text = format_entry_value(entry)
            val_surf = self.lb_row_font.render(val_text, True, color)
            self.screen.blit(val_surf, (col_value_x, row_y))

            # Fecha
            date_text = format_entry_date(entry)
            date_surf = self.lb_row_font.render(date_text, True, color)
            self.screen.blit(date_surf, (col_date_x, row_y))

        # Mensaje si no hay entries
        if not entries:
            empty_text = "Sin records todavia. Juega una partida!"
            empty_surf = self.lb_row_font.render(empty_text, True, COLOR_RANKING_PEER)
            self.screen.blit(
                empty_surf,
                ((WINDOW_WIDTH - empty_surf.get_width()) // 2, y + 20),
            )

        # -- Footer con estado de red --
        footer_y = WINDOW_HEIGHT - 28
        if network_active and peer_count > 0:
            status = f"Peers en red: {peer_count}  |  Nombre validado"
            status_color = COLOR_P2P_CONNECT_OK
        elif network_active:
            # Animacion de puntos para indicar busqueda activa
            ticks = pygame.time.get_ticks()
            n_dots = (ticks // 500) % 4
            dots = "." * n_dots
            if validated_date:
                status = (
                    f"Buscando peers{dots}  |  "
                    f"Ultima validacion: {validated_date}"
                )
            else:
                status = (
                    f"Buscando peers en la red local{dots}  |  "
                    f"Nombre pendiente de validar"
                )
            status_color = COLOR_RANKING_FOOTER
        else:
            if validated_date:
                status = f"Red P2P: inactiva  |  Ultima validacion: {validated_date}"
            else:
                status = "Red P2P: inactiva"
            status_color = COLOR_RANKING_FOOTER
        footer_surf = self.lb_footer_font.render(status, True, status_color)
        self.screen.blit(
            footer_surf,
            ((WINDOW_WIDTH - footer_surf.get_width()) // 2, footer_y),
        )

        # Indicador de red degradada (solo si aplica)
        if p2p_degraded:
            degraded_text = "(P2P degradado — sin punch UDP directo)"
            degraded_surf = self.lb_footer_font.render(
                degraded_text, True, (220, 40, 40),
            )
            self.screen.blit(
                degraded_surf,
                ((WINDOW_WIDTH - degraded_surf.get_width()) // 2, footer_y + 16),
            )

        pygame.display.flip()
        return min(scroll, max_scroll)

    # ================================================================
    # PROMPT DE ALIAS (input de texto)
    # ================================================================

    def draw_alias_prompt(
        self,
        current_text: str,
        mouse_pos: tuple[int, int],
    ) -> None:
        """Dibuja el dialogo de entrada de alias centrado en pantalla."""
        mx, my = mouse_pos

        # Semi-transparente de fondo
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        # Recuadro del dialogo
        dialog_x = (WINDOW_WIDTH - ALIAS_PROMPT_WIDTH) // 2
        dialog_y = (WINDOW_HEIGHT - ALIAS_PROMPT_HEIGHT) // 2
        dialog_rect = pygame.Rect(dialog_x, dialog_y, ALIAS_PROMPT_WIDTH, ALIAS_PROMPT_HEIGHT)
        pygame.draw.rect(self.screen, (20, 20, 20), dialog_rect)
        pygame.draw.rect(self.screen, COLOR_ALIAS_INPUT_BORDER, dialog_rect, 2)

        # Titulo
        title_surf = self.lb_title_font.render("Nombre de jugador", True, ZX_YELLOW)
        self.screen.blit(
            title_surf,
            (dialog_x + (ALIAS_PROMPT_WIDTH - title_surf.get_width()) // 2,
             dialog_y + 20),
        )

        # Campo de texto
        input_x = dialog_x + (ALIAS_PROMPT_WIDTH - ALIAS_INPUT_WIDTH) // 2
        input_y = dialog_y + 70
        input_rect = pygame.Rect(input_x, input_y, ALIAS_INPUT_WIDTH, ALIAS_INPUT_HEIGHT)
        pygame.draw.rect(self.screen, COLOR_ALIAS_INPUT_BG, input_rect)
        pygame.draw.rect(self.screen, COLOR_ALIAS_INPUT_BORDER, input_rect, 2)

        # Texto del input
        text_surf = self.lb_row_font.render(current_text, True, ZX_WHITE)
        self.screen.blit(text_surf, (input_x + 8, input_y + 6))

        # Cursor parpadeante
        cursor_x = input_x + 8 + text_surf.get_width() + 2
        if pygame.time.get_ticks() % 1000 < 500:
            pygame.draw.line(
                self.screen, ZX_WHITE,
                (cursor_x, input_y + 6), (cursor_x, input_y + ALIAS_INPUT_HEIGHT - 6), 2,
            )

        # Hint de longitud
        hint = f"{len(current_text)}/{ALIAS_MAX_LENGTH}"
        hint_surf = self.lb_footer_font.render(hint, True, COLOR_RANKING_PEER)
        self.screen.blit(
            hint_surf,
            (input_x + ALIAS_INPUT_WIDTH - hint_surf.get_width() - 4, input_y + ALIAS_INPUT_HEIGHT + 4),
        )

        # Boton Aceptar
        btn_w, btn_h = 120, 34
        btn_x = dialog_x + (ALIAS_PROMPT_WIDTH - btn_w) // 2
        btn_y = dialog_y + ALIAS_PROMPT_HEIGHT - btn_h - 16
        btn_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)
        self.alias_accept_button_rect = btn_rect

        btn_hovered = btn_rect.collidepoint(mx, my)
        can_accept = len(current_text.strip()) > 0
        if can_accept:
            bg = COLOR_ALIAS_ACCEPT_HOVER_BG if btn_hovered else COLOR_ALIAS_ACCEPT_BG
        else:
            bg = (50, 50, 50)
        pygame.draw.rect(self.screen, bg, btn_rect)
        pygame.draw.rect(self.screen, ZX_WHITE, btn_rect, 1)

        btn_text = self.copy_button_font.render("Aceptar", True, ZX_WHITE if can_accept else (100, 100, 100))
        self.screen.blit(
            btn_text,
            (btn_x + (btn_w - btn_text.get_width()) // 2,
             btn_y + (btn_h - btn_text.get_height()) // 2),
        )

        pygame.display.flip()

    # ================================================================
    # PANTALLA DE CONEXION P2P
    # ================================================================

    def draw_p2p_connecting(
        self,
        elapsed: float,
        telemetry: dict[str, Any],
        mouse_pos: tuple[int, int],
    ) -> None:
        """Dibuja la pantalla de 'Conectando a la red de pares...' con telemetria."""
        mx, my = mouse_pos
        self.screen.fill(ZX_BLACK)

        cx = WINDOW_WIDTH // 2
        y = WINDOW_HEIGHT // 2 - 80

        # Titulo con puntos animados
        n_dots = int(elapsed * 2) % 4
        dots = "." * n_dots
        title = f"Conectando a la red de pares{dots}"
        title_surf = self.lb_title_font.render(title, True, COLOR_P2P_CONNECT_TEXT)
        self.screen.blit(title_surf, (cx - title_surf.get_width() // 2, y))
        y += 50

        # Telemetria
        discovery = telemetry.get("discovery_attempts", 0)
        active = telemetry.get("active_peers", 0)
        total_seen = telemetry.get("total_peers_seen", 0)
        bcast_addrs = telemetry.get("broadcast_addresses", [])

        lines = [
            f"Intentos de descubrimiento: {discovery}",
            f"Direcciones broadcast: {', '.join(bcast_addrs) if bcast_addrs else 'calculando...'}",
            f"Peers encontrados: {active}",
        ]
        if total_seen > active:
            lines.append(f"Peers vistos en total: {total_seen}")

        for line in lines:
            surf = self.lb_row_font.render(line, True, COLOR_P2P_CONNECT_DETAIL)
            self.screen.blit(surf, (cx - surf.get_width() // 2, y))
            y += 28

        y += 20

        # Barra de progreso visual
        bar_w = 300
        bar_h = 12
        bar_x = cx - bar_w // 2
        pygame.draw.rect(self.screen, (50, 50, 50), (bar_x, y, bar_w, bar_h))
        progress = min(1.0, elapsed / P2P_CONNECT_MIN_SECONDS)
        fill_w = int(bar_w * progress)
        bar_color = COLOR_P2P_CONNECT_OK if active > 0 else COLOR_P2P_CONNECT_TEXT
        pygame.draw.rect(self.screen, bar_color, (bar_x, y, fill_w, bar_h))
        pygame.draw.rect(self.screen, ZX_WHITE, (bar_x, y, bar_w, bar_h), 1)
        y += bar_h + 20

        # Mensaje de estado
        if active > 0:
            status = f"{active} peer(s) en la red"
            status_color = COLOR_P2P_CONNECT_OK
        else:
            status = "Buscando peers en la red local..."
            status_color = COLOR_P2P_CONNECT_DETAIL
        status_surf = self.lb_row_font.render(status, True, status_color)
        self.screen.blit(status_surf, (cx - status_surf.get_width() // 2, y))
        y += 40

        # Boton "Continuar" — visible siempre, activo tras MIN_SECONDS o si hay peers
        can_continue = elapsed >= P2P_CONNECT_MIN_SECONDS or active > 0
        btn_w, btn_h = 160, 36
        btn_x = cx - btn_w // 2
        btn_rect = pygame.Rect(btn_x, y, btn_w, btn_h)
        self.p2p_continue_button_rect = btn_rect

        btn_hovered = btn_rect.collidepoint(mx, my)
        if can_continue:
            if active > 0:
                btn_label = "Continuar"
                bg = COLOR_P2P_CONNECT_OK if btn_hovered else (0, 170, 0)
            else:
                btn_label = "Continuar sin peers"
                bg = COLOR_P2P_CONNECT_SKIP if btn_hovered else (85, 85, 85)
        else:
            btn_label = f"Espera {max(0, int(P2P_CONNECT_MIN_SECONDS - elapsed))}s..."
            bg = (40, 40, 40)

        pygame.draw.rect(self.screen, bg, btn_rect)
        pygame.draw.rect(self.screen, ZX_WHITE, btn_rect, 1)
        text_color = ZX_WHITE if can_continue else (100, 100, 100)
        btn_surf = self.copy_button_font.render(btn_label, True, text_color)
        self.screen.blit(
            btn_surf,
            (btn_x + (btn_w - btn_surf.get_width()) // 2,
             y + (btn_h - btn_surf.get_height()) // 2),
        )

        # Hint de ESC
        esc_surf = self.lb_footer_font.render(
            "ESC para cancelar", True, COLOR_P2P_CONNECT_DETAIL,
        )
        self.screen.blit(
            esc_surf,
            (cx - esc_surf.get_width() // 2, WINDOW_HEIGHT - 30),
        )

        pygame.display.flip()
