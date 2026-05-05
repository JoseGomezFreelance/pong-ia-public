"""
pong/splash.py -- Pantalla de carga estilo ZX Spectrum y portada pixel art.

Dos componentes:
1. ZXTerminal: terminal de boot que muestra mensajes de carga con borde
   de franjas de colores al estilo del Sinclair ZX Spectrum (carga de cinta).
2. ZXTitleScreen: portada procedural generada pixel a pixel con la
   paleta estricta de 16 colores del ZX Spectrum.

Ambos se dibujan exclusivamente con pygame.draw — no se cargan imagenes.
"""

from __future__ import annotations

import sys
import threading
import time
from typing import Any

import pygame

from pong.config.layout import WINDOW_HEIGHT, WINDOW_WIDTH
from pong.config.version import APP_VERSION
from pong.config.zx_spectrum import (
    ZX_BLACK,
    ZX_BLUE_BRIGHT,
    ZX_BLUE_DARK,
    ZX_BORDER_BOTTOM_HEIGHT,
    ZX_BORDER_STRIPE_COLORS,
    ZX_BORDER_STRIPE_HEIGHT,
    ZX_BORDER_TOP_HEIGHT,
    ZX_BORDER_WIDTH,
    ZX_BOOT_BEEP_DURATION,
    ZX_BOOT_BEEP_FREQ,
    ZX_BOOT_BEEP_VOLUME,
    ZX_BROWN,
    ZX_CURSOR_BLINK_MS,
    ZX_CYAN,
    ZX_CYAN_BRIGHT,
    ZX_DOWNLOAD_PROGRESS_WIDTH,
    ZX_GRAY_DARK,
    ZX_GRAY_LIGHT,
    ZX_GREEN_BRIGHT,
    ZX_GREEN_DARK,
    ZX_MAGENTA_BRIGHT,
    ZX_MAGENTA_DARK,
    ZX_RED_BRIGHT,
    ZX_RED_DARK,
    ZX_TERMINAL_FONT_SIZE,
    ZX_TERMINAL_LINE_HEIGHT,
    ZX_TERMINAL_MAX_LINES,
    ZX_TERMINAL_PADDING_X,
    ZX_TERMINAL_PADDING_Y,
    ZX_TITLE_BUTTON_FONT_SIZE,
    ZX_TITLE_BUTTON_GAP,
    ZX_TITLE_BUTTON_HEIGHT,
    ZX_TITLE_BUTTON_WIDTH,
    ZX_TITLE_DISPLAY_SECONDS,
    ZX_TITLE_PIXEL_SIZE,
    ZX_WHITE,
    ZX_YELLOW,
)
from pong.sound import build_square_wave


# ============================================================
# Fuente bitmap pixel art (5 columnas x 5 filas por caracter)
# ============================================================

_PIXEL_FONT = {
    "A": [
        [0, 1, 1, 1, 0],
        [1, 0, 0, 0, 1],
        [1, 1, 1, 1, 1],
        [1, 0, 0, 0, 1],
        [1, 0, 0, 0, 1],
    ],
    "B": [
        [1, 1, 1, 1, 0],
        [1, 0, 0, 0, 1],
        [1, 1, 1, 1, 0],
        [1, 0, 0, 0, 1],
        [1, 1, 1, 1, 0],
    ],
    "C": [
        [0, 1, 1, 1, 0],
        [1, 0, 0, 0, 0],
        [1, 0, 0, 0, 0],
        [1, 0, 0, 0, 0],
        [0, 1, 1, 1, 0],
    ],
    "D": [
        [1, 1, 1, 0, 0],
        [1, 0, 0, 1, 0],
        [1, 0, 0, 1, 0],
        [1, 0, 0, 1, 0],
        [1, 1, 1, 0, 0],
    ],
    "E": [
        [1, 1, 1, 1, 1],
        [1, 0, 0, 0, 0],
        [1, 1, 1, 0, 0],
        [1, 0, 0, 0, 0],
        [1, 1, 1, 1, 1],
    ],
    "F": [
        [1, 1, 1, 1, 1],
        [1, 0, 0, 0, 0],
        [1, 1, 1, 0, 0],
        [1, 0, 0, 0, 0],
        [1, 0, 0, 0, 0],
    ],
    "G": [
        [0, 1, 1, 1, 0],
        [1, 0, 0, 0, 0],
        [1, 0, 1, 1, 1],
        [1, 0, 0, 0, 1],
        [0, 1, 1, 1, 0],
    ],
    "H": [
        [1, 0, 0, 0, 1],
        [1, 0, 0, 0, 1],
        [1, 1, 1, 1, 1],
        [1, 0, 0, 0, 1],
        [1, 0, 0, 0, 1],
    ],
    "I": [
        [1, 1, 1, 1, 1],
        [0, 0, 1, 0, 0],
        [0, 0, 1, 0, 0],
        [0, 0, 1, 0, 0],
        [1, 1, 1, 1, 1],
    ],
    "J": [
        [0, 0, 1, 1, 1],
        [0, 0, 0, 1, 0],
        [0, 0, 0, 1, 0],
        [1, 0, 0, 1, 0],
        [0, 1, 1, 0, 0],
    ],
    "K": [
        [1, 0, 0, 1, 0],
        [1, 0, 1, 0, 0],
        [1, 1, 0, 0, 0],
        [1, 0, 1, 0, 0],
        [1, 0, 0, 1, 0],
    ],
    "L": [
        [1, 0, 0, 0, 0],
        [1, 0, 0, 0, 0],
        [1, 0, 0, 0, 0],
        [1, 0, 0, 0, 0],
        [1, 1, 1, 1, 1],
    ],
    "M": [
        [1, 0, 0, 0, 1],
        [1, 1, 0, 1, 1],
        [1, 0, 1, 0, 1],
        [1, 0, 0, 0, 1],
        [1, 0, 0, 0, 1],
    ],
    "N": [
        [1, 0, 0, 0, 1],
        [1, 1, 0, 0, 1],
        [1, 0, 1, 0, 1],
        [1, 0, 0, 1, 1],
        [1, 0, 0, 0, 1],
    ],
    "O": [
        [0, 1, 1, 1, 0],
        [1, 0, 0, 0, 1],
        [1, 0, 0, 0, 1],
        [1, 0, 0, 0, 1],
        [0, 1, 1, 1, 0],
    ],
    "P": [
        [1, 1, 1, 1, 0],
        [1, 0, 0, 0, 1],
        [1, 1, 1, 1, 0],
        [1, 0, 0, 0, 0],
        [1, 0, 0, 0, 0],
    ],
    "R": [
        [1, 1, 1, 1, 0],
        [1, 0, 0, 0, 1],
        [1, 1, 1, 1, 0],
        [1, 0, 1, 0, 0],
        [1, 0, 0, 1, 0],
    ],
    "S": [
        [0, 1, 1, 1, 1],
        [1, 0, 0, 0, 0],
        [0, 1, 1, 1, 0],
        [0, 0, 0, 0, 1],
        [1, 1, 1, 1, 0],
    ],
    "T": [
        [1, 1, 1, 1, 1],
        [0, 0, 1, 0, 0],
        [0, 0, 1, 0, 0],
        [0, 0, 1, 0, 0],
        [0, 0, 1, 0, 0],
    ],
    "U": [
        [1, 0, 0, 0, 1],
        [1, 0, 0, 0, 1],
        [1, 0, 0, 0, 1],
        [1, 0, 0, 0, 1],
        [0, 1, 1, 1, 0],
    ],
    "-": [
        [0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0],
        [1, 1, 1, 1, 1],
        [0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0],
    ],
    " ": [
        [0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0],
    ],
}


# ============================================================
# Borde de franjas coloreadas estilo ZX Spectrum
# ============================================================

def _draw_zx_border(surface: pygame.Surface) -> None:
    """Dibuja el borde tipico del ZX Spectrum con franjas de colores.

    El ZX Spectrum mostraba franjas horizontales de colores alternantes
    en los bordes izquierdo y derecho durante la carga de programas
    desde cinta de cassette. Las barras superior e inferior son solidas.

    Args:
        surface: Superficie de pygame donde dibujar.
    """
    w, h = surface.get_size()

    # Barras solidas arriba y abajo
    pygame.draw.rect(surface, ZX_GRAY_DARK,
                     (0, 0, w, ZX_BORDER_TOP_HEIGHT))
    pygame.draw.rect(surface, ZX_GRAY_DARK,
                     (0, h - ZX_BORDER_BOTTOM_HEIGHT,
                      w, ZX_BORDER_BOTTOM_HEIGHT))

    # Franjas laterales (solo entre las barras superior e inferior)
    colors = ZX_BORDER_STRIPE_COLORS
    num_colors = len(colors)
    stripe_top = ZX_BORDER_TOP_HEIGHT
    stripe_bottom = h - ZX_BORDER_BOTTOM_HEIGHT

    y = stripe_top
    i = 0
    while y < stripe_bottom:
        color = colors[i % num_colors]
        sh = min(ZX_BORDER_STRIPE_HEIGHT, stripe_bottom - y)
        # Franja izquierda
        pygame.draw.rect(surface, color,
                         (0, y, ZX_BORDER_WIDTH, sh))
        # Franja derecha
        pygame.draw.rect(surface, color,
                         (w - ZX_BORDER_WIDTH, y,
                          ZX_BORDER_WIDTH, sh))
        y += ZX_BORDER_STRIPE_HEIGHT
        i += 1


# ============================================================
# ZXTerminal -- Terminal de carga
# ============================================================

class ZXTerminal:
    """Terminal de carga estilo ZX Spectrum.

    Muestra mensajes de progreso de la inicializacion del juego dentro
    de un area negra rodeada por el borde de franjas de colores tipico
    de la carga de cinta del Sinclair ZX Spectrum.

    El texto se renderiza con fuente monoespaciada, sin anti-aliasing,
    y un cursor parpadeante al final de la ultima linea.
    """

    def __init__(self, screen: pygame.Surface) -> None:
        """
        Inicializa la terminal ZX Spectrum.

        Args:
            screen: Superficie principal de pygame.
        """
        self.screen: pygame.Surface = screen
        self.lines: list[str] = []

        # Intentar fuente monoespaciada del sistema; si no, usar la de pygame
        self.font: pygame.font.Font = pygame.font.SysFont("courier", ZX_TERMINAL_FONT_SIZE)
        if self.font.size("M")[0] == self.font.size("i")[0]:
            pass  # Es monoespaciada, perfecto
        else:
            self.font = pygame.font.Font(None, ZX_TERMINAL_FONT_SIZE)

        self._cursor_visible: bool = True
        self._cursor_timer: int = pygame.time.get_ticks()
        self._boot_beep_played: bool = False

    def play_boot_beep(self) -> None:
        """Reproduce el beep de arranque del ZX Spectrum (una sola vez)."""
        if self._boot_beep_played:
            return
        try:
            beep = build_square_wave(
                ZX_BOOT_BEEP_FREQ,
                ZX_BOOT_BEEP_DURATION,
                ZX_BOOT_BEEP_VOLUME,
            )
            if beep:
                beep.play()
        except (pygame.error, OSError):
            pass  # Si falla el audio, continuamos sin sonido
        self._boot_beep_played = True

    def add_line(self, text: str) -> None:
        """Añade una linea de texto a la terminal.

        Args:
            text: Texto de la linea a mostrar.
        """
        self.lines.append(text)
        if len(self.lines) > ZX_TERMINAL_MAX_LINES:
            self.lines = self.lines[-ZX_TERMINAL_MAX_LINES:]

    def update_last_line(self, text: str) -> None:
        """Reemplaza la ultima linea (para cambios de estado en el mismo paso).

        Args:
            text: Nuevo texto para la ultima linea.
        """
        if self.lines:
            self.lines[-1] = text
        else:
            self.lines.append(text)

    def render(self, step: int, total_steps: int) -> None:
        """Dibuja un frame completo de la terminal ZX Spectrum.

        Args:
            step:        Paso actual de inicializacion.
            total_steps: Numero total de pasos.
        """
        # 1. Borde de franjas de colores
        self.screen.fill(ZX_BLACK)
        _draw_zx_border(self.screen)

        # 2. Area de terminal (negro interior)
        inner_x = ZX_BORDER_WIDTH
        inner_y = ZX_BORDER_TOP_HEIGHT
        inner_w = WINDOW_WIDTH - 2 * ZX_BORDER_WIDTH
        inner_h = WINDOW_HEIGHT - ZX_BORDER_TOP_HEIGHT - ZX_BORDER_BOTTOM_HEIGHT
        pygame.draw.rect(self.screen, ZX_BLACK,
                         (inner_x, inner_y, inner_w, inner_h))

        # 3. Cabecera estilo ZX Spectrum
        x_start = inner_x + ZX_TERMINAL_PADDING_X
        y = inner_y + ZX_TERMINAL_PADDING_Y

        # (C) 2025 JGF
        header_surf = self.font.render("(C) 2025 JGF", False, ZX_WHITE)
        self.screen.blit(header_surf, (x_start, y))
        y += ZX_TERMINAL_LINE_HEIGHT

        # PONG-IA
        title_surf = self.font.render("PONG-IA", False, ZX_CYAN_BRIGHT)
        self.screen.blit(title_surf, (x_start, y))
        y += ZX_TERMINAL_LINE_HEIGHT

        # Version
        ver_surf = self.font.render(APP_VERSION, False, ZX_GRAY_LIGHT)
        self.screen.blit(ver_surf, (x_start, y))
        y += ZX_TERMINAL_LINE_HEIGHT * 2  # Linea en blanco

        # 4. Lineas de estado
        for line_text in self.lines:
            line_surf = self.font.render(line_text, False, ZX_WHITE)
            self.screen.blit(line_surf, (x_start, y))
            y += ZX_TERMINAL_LINE_HEIGHT

        # 5. Cursor parpadeante tras la ultima linea
        now = pygame.time.get_ticks()
        if now - self._cursor_timer >= ZX_CURSOR_BLINK_MS:
            self._cursor_visible = not self._cursor_visible
            self._cursor_timer = now

        if self._cursor_visible and self.lines:
            last_text = self.lines[-1]
            text_w = self.font.size(last_text)[0]
            cursor_surf = self.font.render("_", False, ZX_WHITE)
            self.screen.blit(
                cursor_surf,
                (x_start + text_w + 2, y - ZX_TERMINAL_LINE_HEIGHT),
            )

        # 6. Indicador de progreso (parte inferior de la terminal)
        filled = "=" * step
        empty = " " * (total_steps - step)
        progress_text = f"[{filled}{empty}] {step}/{total_steps}"
        prog_surf = self.font.render(progress_text, False, ZX_GREEN_BRIGHT)
        prog_y = (
            WINDOW_HEIGHT - ZX_BORDER_BOTTOM_HEIGHT
            - ZX_TERMINAL_PADDING_Y - ZX_TERMINAL_LINE_HEIGHT
        )
        self.screen.blit(prog_surf, (x_start, prog_y))

        # 7. Mantener ventana responsiva y permitir cerrar
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)

        pygame.display.flip()


# ============================================================
# ZXTitleScreen -- Portada pixel art procedural
# ============================================================

class ZXTitleScreen:
    """Portada del juego generada proceduralmente pixel a pixel.

    Toda la escena se construye usando solamente la paleta de 16 colores
    del ZX Spectrum, a una resolucion logica de (WINDOW_WIDTH / pixel_size)
    por (WINDOW_HEIGHT / pixel_size) pixeles logicos. Cada pixel logico
    se dibuja como un cuadrado de pixel_size x pixel_size pixeles reales.

    La escena incluye:
    - Borde de franjas ZX Spectrum
    - Marco decorativo interior
    - Titulo "PONG-IA" en pixel art grande
    - Escena de Pong en perspectiva (mesa, red, pelota, raquetas)
    - Branding "JGF" con lineas decorativas
    """

    def __init__(
        self,
        screen: pygame.Surface,
        *,
        show_integrity_notice: bool = False,
    ) -> None:
        """
        Args:
            screen: Superficie principal de pygame.
            show_integrity_notice: Mostrar aviso unico sobre integridad.
        """
        self.screen: pygame.Surface = screen
        self._surface: pygame.Surface | None = None
        self._show_integrity_notice: bool = show_integrity_notice

    # ----------------------------------------------------------
    # Pixel art helpers
    # ----------------------------------------------------------

    def _put_pixel(self, surface: pygame.Surface, lx: int, ly: int,
                   color: tuple[int, int, int], ps: int) -> None:
        """Dibuja un pixel logico como un cuadrado ps x ps.

        Args:
            surface: Superficie donde dibujar.
            lx:      Coordenada X logica.
            ly:      Coordenada Y logica.
            color:   Color RGB.
            ps:      Tamaño del pixel (pixel_size).
        """
        pygame.draw.rect(surface, color, (lx * ps, ly * ps, ps, ps))

    def _fill_rect(self, surface: pygame.Surface, lx: int, ly: int,
                   lw: int, lh: int, color: tuple[int, int, int],
                   ps: int) -> None:
        """Rellena un rectangulo logico.

        Args:
            surface: Superficie donde dibujar.
            lx, ly:  Esquina superior izquierda logica.
            lw, lh:  Ancho y alto logicos.
            color:   Color RGB.
            ps:      Tamaño del pixel (pixel_size).
        """
        pygame.draw.rect(surface, color,
                         (lx * ps, ly * ps, lw * ps, lh * ps))

    def _draw_text_bitmap(self, surface: pygame.Surface, text: str,
                          start_lx: int, start_ly: int,
                          color: tuple[int, int, int], ps: int,
                          scale: int = 1) -> None:
        """Renderiza texto con la fuente bitmap pixel art.

        Args:
            surface:   Superficie donde dibujar.
            text:      Texto a renderizar (se convierte a mayusculas).
            start_lx:  Posicion X logica del primer caracter.
            start_ly:  Posicion Y logica del primer caracter.
            color:     Color RGB.
            ps:        Tamaño del pixel (pixel_size).
            scale:     Factor de escala (1 = 5x5 px logicos por caracter).
        """
        cursor_lx = start_lx
        for char in text.upper():
            glyph = _PIXEL_FONT.get(char)
            if glyph is None:
                cursor_lx += 3 * scale  # Espacio para caracteres desconocidos
                continue
            for row_i, row in enumerate(glyph):
                for col_i, val in enumerate(row):
                    if val:
                        for sy in range(scale):
                            for sx in range(scale):
                                self._put_pixel(
                                    surface,
                                    cursor_lx + col_i * scale + sx,
                                    start_ly + row_i * scale + sy,
                                    color, ps,
                                )
            cursor_lx += (len(glyph[0]) + 1) * scale

    def _text_width(self, text: str, scale: int = 1) -> int:
        """Calcula el ancho logico de un texto en pixeles logicos.

        Args:
            text:  Texto a medir.
            scale: Factor de escala.

        Returns:
            Ancho en pixeles logicos.
        """
        width = 0
        for char in text.upper():
            glyph = _PIXEL_FONT.get(char)
            if glyph is None:
                width += 3 * scale
            else:
                width += (len(glyph[0]) + 1) * scale
        # Restar el ultimo gap
        if width > 0:
            width -= scale
        return width

    # ----------------------------------------------------------
    # Escena procedural
    # ----------------------------------------------------------

    def build(self) -> None:
        """Pre-renderiza toda la portada en una superficie interna."""
        ps = ZX_TITLE_PIXEL_SIZE
        lw = WINDOW_WIDTH // ps   # 200 pixeles logicos de ancho
        lh = WINDOW_HEIGHT // ps  # 186 pixeles logicos de alto

        self._surface = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
        self._surface.fill(ZX_BLACK)

        # --- Marco decorativo interior ---
        border_lx = ZX_BORDER_WIDTH // ps       # 12
        border_ly = ZX_BORDER_TOP_HEIGHT // ps   # 8
        border_lw = lw - 2 * border_lx           # 176
        border_lh = lh - 2 * border_ly           # 170

        # Borde exterior rojo
        self._draw_border_rect(
            self._surface, border_lx, border_ly,
            border_lw, border_lh, ZX_RED_DARK, ps,
        )
        # Borde interior cyan
        self._draw_border_rect(
            self._surface, border_lx + 1, border_ly + 1,
            border_lw - 2, border_lh - 2, ZX_CYAN, ps,
        )
        # Fondo negro interior
        self._fill_rect(
            self._surface, border_lx + 2, border_ly + 2,
            border_lw - 4, border_lh - 4, ZX_BLACK, ps,
        )

        # --- Franja de colores superior e inferior (dentro del marco) ---
        stripe_y_top = border_ly + 2
        stripe_y_bot = border_ly + border_lh - 4
        stripe_colors = [ZX_YELLOW, ZX_BLUE_BRIGHT, ZX_RED_BRIGHT,
                         ZX_MAGENTA_BRIGHT, ZX_CYAN_BRIGHT, ZX_GREEN_BRIGHT]
        for i in range(border_lw - 4):
            c = stripe_colors[i % len(stripe_colors)]
            self._put_pixel(self._surface,
                            border_lx + 2 + i, stripe_y_top, c, ps)
            self._put_pixel(self._surface,
                            border_lx + 2 + i, stripe_y_top + 1, c, ps)
            self._put_pixel(self._surface,
                            border_lx + 2 + i, stripe_y_bot, c, ps)
            self._put_pixel(self._surface,
                            border_lx + 2 + i, stripe_y_bot + 1, c, ps)

        # --- Titulo "PONG-IA" ---
        title_text = "PONG-IA"
        title_scale = 3
        title_w = self._text_width(title_text, title_scale)
        title_lx = (lw - title_w) // 2
        title_ly = border_ly + 5
        # Sombra
        self._draw_text_bitmap(
            self._surface, title_text,
            title_lx + 1, title_ly + 1,
            ZX_BLUE_DARK, ps, title_scale,
        )
        # Texto principal
        self._draw_text_bitmap(
            self._surface, title_text,
            title_lx, title_ly,
            ZX_CYAN_BRIGHT, ps, title_scale,
        )

        # --- Escena Pong en perspectiva ---
        scene_top = title_ly + 5 * title_scale + 6  # Debajo del titulo
        scene_center_x = lw // 2
        scene_center_y = scene_top + 30

        # Suelo en perspectiva (trapecio azul)
        self._draw_trapezoid(
            self._surface,
            top_left_x=scene_center_x - 20,
            top_y=scene_top + 5,
            top_width=40,
            bottom_left_x=scene_center_x - 55,
            bottom_y=scene_top + 55,
            bottom_width=110,
            color=ZX_BLUE_DARK, ps=ps,
        )

        # Mesa de ping pong (trapecio verde)
        table_top_y = scene_top + 10
        table_bot_y = scene_top + 48
        table_top_lx = scene_center_x - 16
        table_top_w = 32
        table_bot_lx = scene_center_x - 42
        table_bot_w = 84

        # Superficie de la mesa
        self._draw_trapezoid(
            self._surface,
            top_left_x=table_top_lx, top_y=table_top_y,
            top_width=table_top_w,
            bottom_left_x=table_bot_lx, bottom_y=table_bot_y,
            bottom_width=table_bot_w,
            color=ZX_GREEN_BRIGHT, ps=ps,
        )

        # Borde de la mesa
        self._draw_trapezoid_outline(
            self._surface,
            top_left_x=table_top_lx, top_y=table_top_y,
            top_width=table_top_w,
            bottom_left_x=table_bot_lx, bottom_y=table_bot_y,
            bottom_width=table_bot_w,
            color=ZX_GREEN_DARK, ps=ps,
        )

        # Red central (linea vertical con perspectiva)
        for ly in range(table_top_y, table_bot_y):
            t = (ly - table_top_y) / max(table_bot_y - table_top_y, 1)
            rx = int(scene_center_x + 0.5)
            self._put_pixel(self._surface, rx, ly, ZX_WHITE, ps)
            # Poste superior de la red (mas alto en la parte frontal)
            if ly == table_top_y:
                for ry in range(ly - 3, ly):
                    self._put_pixel(self._surface, rx, ry, ZX_WHITE, ps)

        # Linea central horizontal de la mesa
        for ly in [table_top_y, table_bot_y - 1]:
            mid_lx_start = int(table_top_lx + (table_bot_lx - table_top_lx) *
                               ((ly - table_top_y) / max(table_bot_y - table_top_y, 1)))
            mid_w = int(table_top_w + (table_bot_w - table_top_w) *
                        ((ly - table_top_y) / max(table_bot_y - table_top_y, 1)))
            for lx in range(mid_lx_start, mid_lx_start + mid_w):
                self._put_pixel(self._surface, lx, ly, ZX_GREEN_DARK, ps)

        # Pelota (3x3 pixeles blancos)
        ball_lx = scene_center_x + 8
        ball_ly = scene_top + 20
        for dy in range(3):
            for dx in range(3):
                self._put_pixel(self._surface,
                                ball_lx + dx, ball_ly + dy, ZX_WHITE, ps)

        # Raqueta izquierda (marron, en perspectiva)
        raq_ly = scene_top + 28
        raq_lx = table_bot_lx + 8
        for dy in range(8):
            for dx in range(3):
                self._put_pixel(self._surface,
                                raq_lx + dx, raq_ly + dy, ZX_BROWN, ps)
        # Mango
        for dy in range(4):
            self._put_pixel(self._surface,
                            raq_lx + 1, raq_ly + 8 + dy, ZX_BROWN, ps)

        # Raqueta derecha (roja)
        raq2_lx = table_bot_lx + table_bot_w - 11
        raq2_ly = scene_top + 25
        for dy in range(8):
            for dx in range(3):
                self._put_pixel(self._surface,
                                raq2_lx + dx, raq2_ly + dy, ZX_RED_BRIGHT, ps)
        # Mango
        for dy in range(4):
            self._put_pixel(self._surface,
                            raq2_lx + 1, raq2_ly + 8 + dy, ZX_BROWN, ps)

        # Patas de la mesa
        leg_y = table_bot_y
        legs = [
            (table_bot_lx + 5, leg_y),
            (table_bot_lx + table_bot_w - 6, leg_y),
        ]
        for leg_lx, leg_ly in legs:
            for dy in range(6):
                self._put_pixel(self._surface,
                                leg_lx, leg_ly + dy, ZX_BROWN, ps)
                self._put_pixel(self._surface,
                                leg_lx + 1, leg_ly + dy, ZX_BROWN, ps)

        # --- "JGF" branding ---
        jgf_scale = 2
        jgf_text = "JGF"
        jgf_w = self._text_width(jgf_text, jgf_scale)
        jgf_lx = (lw - jgf_w) // 2
        jgf_ly = border_ly + border_lh - 18
        self._draw_text_bitmap(
            self._surface, jgf_text, jgf_lx, jgf_ly,
            ZX_WHITE, ps, jgf_scale,
        )

        # Lineas decorativas bajo JGF
        line_y = jgf_ly + 5 * jgf_scale + 2
        line_half = jgf_w // 2 + 4
        center_lx = lw // 2
        for lx in range(center_lx - line_half, center_lx + line_half):
            self._put_pixel(self._surface, lx, line_y, ZX_WHITE, ps)
        # Punto central
        self._put_pixel(self._surface, center_lx, line_y + 2, ZX_WHITE, ps)
        for lx in range(center_lx - line_half, center_lx + line_half):
            self._put_pixel(self._surface, lx, line_y + 4, ZX_WHITE, ps)

        # --- Borde ZX Spectrum encima de todo ---
        _draw_zx_border(self._surface)

    # ----------------------------------------------------------
    # Dibujo de trapezoides (para perspectiva)
    # ----------------------------------------------------------

    def _draw_trapezoid(self, surface: pygame.Surface, top_left_x: int,
                        top_y: int, top_width: int, bottom_left_x: int,
                        bottom_y: int, bottom_width: int,
                        color: tuple[int, int, int], ps: int) -> None:
        """Rellena un trapezoide pixel a pixel (para perspectiva).

        Interpola linealmente entre la fila superior y la inferior.
        """
        height = bottom_y - top_y
        if height <= 0:
            return
        for row in range(height):
            t = row / height
            lx = int(top_left_x + (bottom_left_x - top_left_x) * t)
            w = int(top_width + (bottom_width - top_width) * t)
            ly = top_y + row
            for x in range(lx, lx + w):
                self._put_pixel(surface, x, ly, color, ps)

    def _draw_trapezoid_outline(self, surface: pygame.Surface,
                                top_left_x: int, top_y: int,
                                top_width: int, bottom_left_x: int,
                                bottom_y: int, bottom_width: int,
                                color: tuple[int, int, int],
                                ps: int) -> None:
        """Dibuja el contorno de un trapezoide pixel a pixel."""
        height = bottom_y - top_y
        if height <= 0:
            return
        for row in range(height):
            t = row / height
            lx = int(top_left_x + (bottom_left_x - top_left_x) * t)
            w = int(top_width + (bottom_width - top_width) * t)
            ly = top_y + row
            self._put_pixel(surface, lx, ly, color, ps)
            if w > 1:
                self._put_pixel(surface, lx + w - 1, ly, color, ps)

        # Linea superior e inferior
        for x in range(top_left_x, top_left_x + top_width):
            self._put_pixel(surface, x, top_y, color, ps)
        for x in range(bottom_left_x, bottom_left_x + bottom_width):
            self._put_pixel(surface, x, bottom_y - 1, color, ps)

    def _draw_border_rect(self, surface: pygame.Surface, lx: int, ly: int,
                          lw: int, lh: int, color: tuple[int, int, int],
                          ps: int) -> None:
        """Dibuja el contorno de un rectangulo logico.

        Args:
            surface: Superficie donde dibujar.
            lx, ly:  Esquina superior izquierda logica.
            lw, lh:  Ancho y alto logicos.
            color:   Color RGB.
            ps:      Tamaño del pixel.
        """
        # Linea superior
        for x in range(lx, lx + lw):
            self._put_pixel(surface, x, ly, color, ps)
        # Linea inferior
        for x in range(lx, lx + lw):
            self._put_pixel(surface, x, ly + lh - 1, color, ps)
        # Linea izquierda
        for y in range(ly, ly + lh):
            self._put_pixel(surface, lx, y, color, ps)
        # Linea derecha
        for y in range(ly, ly + lh):
            self._put_pixel(surface, lx + lw - 1, y, color, ps)

    # ----------------------------------------------------------
    # Mostrar la portada
    # ----------------------------------------------------------

    def _show_notice_overlay(self) -> None:
        """Muestra un aviso unico sobre la integridad del sistema de guardado."""
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
        overlay.fill(ZX_BLACK)
        overlay.set_alpha(220)
        self.screen.blit(overlay, (0, 0))

        font_title = pygame.font.Font(None, 30)
        font_body = pygame.font.Font(None, 22)
        font_hint = pygame.font.Font(None, 20)

        lines = [
            (font_title, "SISTEMA DE GUARDADO PROTEGIDO", ZX_CYAN_BRIGHT),
            (None, "", ZX_WHITE),
            (font_body, "Tus partidas, logros y progreso RPG estan", ZX_WHITE),
            (font_body, "protegidos con firma criptografica.", ZX_WHITE),
            (None, "", ZX_WHITE),
            (font_body, "Si cambias de placa base, el archivo de", ZX_YELLOW),
            (font_body, "guardado podria invalidarse y tu progreso", ZX_YELLOW),
            (font_body, "quedara congelado hasta ser re-firmado.", ZX_YELLOW),
            (None, "", ZX_WHITE),
            (font_hint, "Pulsa cualquier tecla para continuar", ZX_GRAY_LIGHT),
        ]

        y = WINDOW_HEIGHT // 2 - len(lines) * 14
        for font, text, color in lines:
            if font is None:
                y += 10
                continue
            surf = font.render(text, True, color)
            rect = surf.get_rect(centerx=WINDOW_WIDTH // 2, top=y)
            self.screen.blit(surf, rect)
            y += 26

        pygame.display.flip()

        # Esperar cualquier tecla o clic
        waiting = True
        while waiting:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit(0)
                if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                    waiting = False
            pygame.time.wait(30)

    def display(self) -> str:
        """Muestra la portada con botones JUGAR / INSTALAR MODELOS IA.

        Returns:
            ``"play"`` si el usuario elige jugar,
            ``"install"`` si elige instalar modelos.
        """
        if self._surface is None:
            self.build()

        if self._show_integrity_notice:
            self._show_notice_overlay()
            self._show_integrity_notice = False

        btn_font = pygame.font.Font(None, ZX_TITLE_BUTTON_FONT_SIZE)
        clock = pygame.time.Clock()
        blink_on = True
        last_blink = time.monotonic()

        # Posiciones de los dos botones (centrados verticalmente en
        # la mitad inferior del area interior, entre el dibujo y el borde)
        total_btn_block = ZX_TITLE_BUTTON_HEIGHT * 2 + ZX_TITLE_BUTTON_GAP
        inner_bottom = WINDOW_HEIGHT - ZX_BORDER_BOTTOM_HEIGHT
        mid_y = (WINDOW_HEIGHT // 2 + inner_bottom) // 2
        btn_y_base = mid_y - total_btn_block // 2
        play_rect = pygame.Rect(
            (WINDOW_WIDTH - ZX_TITLE_BUTTON_WIDTH) // 2,
            btn_y_base,
            ZX_TITLE_BUTTON_WIDTH,
            ZX_TITLE_BUTTON_HEIGHT,
        )
        install_rect = pygame.Rect(
            (WINDOW_WIDTH - ZX_TITLE_BUTTON_WIDTH) // 2,
            btn_y_base + ZX_TITLE_BUTTON_HEIGHT + ZX_TITLE_BUTTON_GAP,
            ZX_TITLE_BUTTON_WIDTH,
            ZX_TITLE_BUTTON_HEIGHT,
        )

        while True:
            # Dibujar portada pre-renderizada
            assert self._surface is not None
            self.screen.blit(self._surface, (0, 0))

            # Parpadeo
            now = time.monotonic()
            if now - last_blink > 0.6:
                blink_on = not blink_on
                last_blink = now

            mouse_pos = pygame.mouse.get_pos()

            if blink_on:
                self._draw_button(
                    play_rect, "JUGAR", btn_font, mouse_pos,
                    text_color=ZX_CYAN_BRIGHT,
                    bg_normal=ZX_BLUE_DARK,
                    bg_hover=ZX_BLUE_BRIGHT,
                    border_color=ZX_CYAN,
                )
                self._draw_button(
                    install_rect, "INSTALAR MODELOS IA", btn_font, mouse_pos,
                    text_color=ZX_GREEN_BRIGHT,
                    bg_normal=(0, 85, 0),       # verde muy oscuro
                    bg_hover=ZX_GREEN_DARK,
                    border_color=ZX_GREEN_BRIGHT,
                )
            else:
                # Fase apagada del parpadeo: botones oscurecidos (no invisibles)
                self._draw_button(
                    play_rect, "JUGAR", btn_font, mouse_pos,
                    text_color=ZX_BLUE_DARK,
                    bg_normal=(0, 0, 60),
                    bg_hover=(0, 0, 60),
                    border_color=ZX_BLUE_DARK,
                )
                self._draw_button(
                    install_rect, "INSTALAR MODELOS IA", btn_font, mouse_pos,
                    text_color=(0, 60, 0),
                    bg_normal=(0, 40, 0),
                    bg_hover=(0, 40, 0),
                    border_color=(0, 60, 0),
                )

            pygame.display.flip()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit(0)
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if play_rect.collidepoint(event.pos):
                        return "play"
                    if install_rect.collidepoint(event.pos):
                        return "install"
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN:
                        return "play"
                    if event.key == pygame.K_i:
                        return "install"
                    if event.key == pygame.K_a:
                        return "play_agent"

            clock.tick(30)

    # ----------------------------------------------------------
    # Dibujo de botones retro
    # ----------------------------------------------------------

    def _draw_button(
        self,
        rect: pygame.Rect,
        text: str,
        font: pygame.font.Font,
        mouse_pos: tuple[int, int],
        *,
        text_color: tuple[int, int, int],
        bg_normal: tuple[int, int, int],
        bg_hover: tuple[int, int, int],
        border_color: tuple[int, int, int],
    ) -> None:
        """Dibuja un boton estilo ZX Spectrum con efecto hover."""
        hovering = rect.collidepoint(mouse_pos)
        bg = bg_hover if hovering else bg_normal

        pygame.draw.rect(self.screen, bg, rect)
        pygame.draw.rect(self.screen, border_color, rect, 2)

        label = font.render(text, False, text_color)
        label_rect = label.get_rect(center=rect.center)
        self.screen.blit(label, label_rect)


# ============================================================
# ZXDownloadScreen -- Pantalla de descarga de modelos IA
# ============================================================

class ZXDownloadScreen:
    """Pantalla de descarga de modelos IA con estetica ZX Spectrum.

    Muestra el estado de cada modelo (LLM y difusion), permite
    descargarlos con un boton y muestra progreso en tiempo real.
    La descarga corre en un hilo separado para no bloquear pygame.
    """

    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self.font = pygame.font.SysFont("Courier", ZX_TERMINAL_FONT_SIZE)
        if self.font.get_height() < 10:
            self.font = pygame.font.Font(None, ZX_TERMINAL_FONT_SIZE)
        self.btn_font = pygame.font.Font(None, ZX_TITLE_BUTTON_FONT_SIZE)

    def run(self) -> None:
        """Bucle principal de la pantalla de descarga.

        Bloquea hasta que el usuario pulsa ESC (fuera de descarga).
        """
        import threading

        from pong.model_downloader import ModelStatus, check_models_status, run_downloads

        statuses = check_models_status()
        lock = threading.Lock()
        download_thread: threading.Thread | None = None
        downloading = False
        completed = False
        esc_warning_until = 0.0  # monotonic timestamp

        clock = pygame.time.Clock()

        # Boton DESCARGAR / VOLVER
        btn_width = ZX_TITLE_BUTTON_WIDTH
        btn_height = ZX_TITLE_BUTTON_HEIGHT
        action_rect = pygame.Rect(
            (WINDOW_WIDTH - btn_width) // 2,
            WINDOW_HEIGHT - ZX_BORDER_BOTTOM_HEIGHT - btn_height - 60,
            btn_width, btn_height,
        )
        back_rect = pygame.Rect(
            (WINDOW_WIDTH - btn_width) // 2,
            WINDOW_HEIGHT - ZX_BORDER_BOTTOM_HEIGHT - btn_height - 16,
            btn_width, btn_height,
        )

        while True:
            mouse_pos = pygame.mouse.get_pos()
            now = time.monotonic()

            # --- Detectar si terminaron todas las descargas ---
            if downloading and download_thread is not None:
                if not download_thread.is_alive():
                    downloading = False
                    completed = True
                    download_thread = None

            # --- Dibujar ---
            self.screen.fill(ZX_BLACK)
            _draw_zx_border(self.screen)

            inner_x = ZX_BORDER_WIDTH
            inner_y = ZX_BORDER_TOP_HEIGHT
            inner_w = WINDOW_WIDTH - 2 * ZX_BORDER_WIDTH
            inner_h = (
                WINDOW_HEIGHT - ZX_BORDER_TOP_HEIGHT - ZX_BORDER_BOTTOM_HEIGHT
            )
            pygame.draw.rect(
                self.screen, ZX_BLACK,
                (inner_x, inner_y, inner_w, inner_h),
            )

            x_start = inner_x + ZX_TERMINAL_PADDING_X
            y = inner_y + ZX_TERMINAL_PADDING_Y

            # Cabecera
            hdr = self.font.render("(C) 2025 JGF", False, ZX_WHITE)
            self.screen.blit(hdr, (x_start, y))
            y += ZX_TERMINAL_LINE_HEIGHT

            title = self.font.render(
                "INSTALADOR DE MODELOS IA", False, ZX_CYAN_BRIGHT,
            )
            self.screen.blit(title, (x_start, y))
            y += ZX_TERMINAL_LINE_HEIGHT * 2

            # --- Seccion 1: Modelo LLM (boton hacia selector) ---
            llm_status = statuses[0]
            with lock:
                llm_installed = llm_status.installed

            self.screen.blit(
                self.font.render("1. Modelo LLM", False, ZX_WHITE),
                (x_start, y),
            )
            y += ZX_TERMINAL_LINE_HEIGHT

            if llm_installed:
                st_surf = self.font.render(
                    "   Estado: Instalado", False, ZX_GREEN_BRIGHT,
                )
                self.screen.blit(st_surf, (x_start, y))
            else:
                st_surf = self.font.render(
                    "   Estado: No configurado", False, ZX_YELLOW,
                )
                self.screen.blit(st_surf, (x_start, y))
            y += ZX_TERMINAL_LINE_HEIGHT

            # Boton para abrir selector
            llm_btn_rect = pygame.Rect(
                x_start + 12, y, 240, ZX_TITLE_BUTTON_HEIGHT - 4,
            )
            self._draw_screen_button(
                llm_btn_rect, "SELECCIONAR MODELO >", mouse_pos,
                text_color=ZX_CYAN_BRIGHT,
                bg_normal=ZX_BLUE_DARK,
                bg_hover=ZX_BLUE_BRIGHT,
                border_color=ZX_CYAN,
            )
            y += ZX_TITLE_BUTTON_HEIGHT + ZX_TERMINAL_LINE_HEIGHT // 2

            # --- Seccion 2: Modelos de difusion ---
            diff_status = statuses[1]
            with lock:
                diff_name = diff_status.name
                diff_size = diff_status.size_hint
                diff_installed = diff_status.installed
                diff_progress = diff_status.progress
                diff_status_text = diff_status.status_text
                diff_error = diff_status.error

            label = f"2. {diff_name}  {diff_size}"
            self.screen.blit(
                self.font.render(label, False, ZX_WHITE), (x_start, y),
            )
            y += ZX_TERMINAL_LINE_HEIGHT

            if diff_error:
                color = ZX_RED_BRIGHT
            elif diff_installed:
                color = ZX_GREEN_BRIGHT
            elif "Descargando" in diff_status_text:
                color = ZX_CYAN_BRIGHT
            else:
                color = ZX_YELLOW

            display_status = diff_status_text
            if diff_installed and not diff_error:
                display_status = "Instalado"

            st_surf = self.font.render(
                f"   Estado: {display_status}", False, color,
            )
            self.screen.blit(st_surf, (x_start, y))
            y += ZX_TERMINAL_LINE_HEIGHT

            if not diff_installed and not diff_error and diff_progress != 0.0:
                bar = self._progress_bar(diff_progress)
                bar_surf = self.font.render(
                    f"   {bar}", False, ZX_GREEN_BRIGHT,
                )
                self.screen.blit(bar_surf, (x_start, y))
            y += ZX_TERMINAL_LINE_HEIGHT
            y += ZX_TERMINAL_LINE_HEIGHT // 2

            # Espacio total estimado
            total_hint = self.font.render(
                "Espacio total: ~5 GB", False, ZX_GRAY_LIGHT,
            )
            self.screen.blit(total_hint, (x_start, y))

            # Boton de accion (solo difusion)
            diff_pending = not diff_installed and not downloading

            if completed or diff_installed:
                self._draw_screen_button(
                    action_rect, "DIFUSION OK", mouse_pos,
                    text_color=ZX_GREEN_BRIGHT,
                    bg_normal=(0, 85, 0),
                    bg_hover=(0, 85, 0),
                    border_color=ZX_GREEN_BRIGHT,
                )
            elif downloading:
                self._draw_screen_button(
                    action_rect, "DESCARGANDO...", mouse_pos,
                    text_color=ZX_YELLOW,
                    bg_normal=ZX_GRAY_DARK,
                    bg_hover=ZX_GRAY_DARK,
                    border_color=ZX_YELLOW,
                )
            else:
                self._draw_screen_button(
                    action_rect, "DESCARGAR DIFUSION", mouse_pos,
                    text_color=ZX_CYAN_BRIGHT,
                    bg_normal=ZX_BLUE_DARK,
                    bg_hover=ZX_BLUE_BRIGHT,
                    border_color=ZX_CYAN,
                )

            # Boton volver / indicador ESC
            if downloading:
                self._draw_screen_button(
                    back_rect, "ESC = Espera...", mouse_pos,
                    text_color=ZX_GRAY_DARK,
                    bg_normal=ZX_BLACK,
                    bg_hover=ZX_BLACK,
                    border_color=ZX_GRAY_DARK,
                )
            else:
                self._draw_screen_button(
                    back_rect, "VOLVER (ESC)", mouse_pos,
                    text_color=ZX_WHITE,
                    bg_normal=ZX_GRAY_DARK,
                    bg_hover=(120, 120, 120),
                    border_color=ZX_WHITE,
                )

            # Mensaje de advertencia si intenta ESC durante descarga
            if now < esc_warning_until:
                warn = self.font.render(
                    "Espera a que termine la descarga...",
                    False, ZX_RED_BRIGHT,
                )
                warn_rect = warn.get_rect(
                    centerx=WINDOW_WIDTH // 2,
                    bottom=back_rect.top - 4,
                )
                self.screen.blit(warn, warn_rect)

            pygame.display.flip()

            # --- Eventos ---
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit(0)

                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if downloading:
                            esc_warning_until = now + 2.0
                        else:
                            return

                if event.type == pygame.MOUSEBUTTONDOWN:
                    if back_rect.collidepoint(event.pos) and not downloading:
                        return

                    # Boton selector LLM
                    if llm_btn_rect.collidepoint(event.pos) and not downloading:
                        selector = ZXModelSelectorScreen(self.screen)
                        result = selector.run()
                        if result in ("selected", "onnx"):
                            # Actualizar estado LLM
                            with lock:
                                statuses[0].installed = True
                                statuses[0].status_text = "Instalado"

                    # Boton descargar difusion
                    if action_rect.collidepoint(event.pos) and diff_pending:
                        downloading = True
                        # Solo descargar difusion (indice 1)
                        diff_only = [statuses[1]]
                        download_thread = threading.Thread(
                            target=run_downloads,
                            args=(diff_only, lock),
                            daemon=True,
                        )
                        download_thread.start()

            clock.tick(30)

    # ----------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------

    @staticmethod
    def _progress_bar(progress: float) -> str:
        """Genera una barra de progreso tipo ``[====    ] 45%``."""
        width = ZX_DOWNLOAD_PROGRESS_WIDTH
        if progress < 0:
            # Indeterminado: barra animada
            return "[" + "." * width + "] ..."
        filled = int(width * progress)
        empty = width - filled
        pct = int(progress * 100)
        return f"[{'=' * filled}{' ' * empty}] {pct}%"

    def _draw_screen_button(
        self,
        rect: pygame.Rect,
        text: str,
        mouse_pos: tuple[int, int],
        *,
        text_color: tuple[int, int, int],
        bg_normal: tuple[int, int, int],
        bg_hover: tuple[int, int, int],
        border_color: tuple[int, int, int],
    ) -> None:
        """Dibuja un boton en la pantalla de descarga."""
        hovering = rect.collidepoint(mouse_pos)
        bg = bg_hover if hovering else bg_normal

        pygame.draw.rect(self.screen, bg, rect)
        pygame.draw.rect(self.screen, border_color, rect, 2)

        label = self.btn_font.render(text, False, text_color)
        label_rect = label.get_rect(center=rect.center)
        self.screen.blit(label, label_rect)


# ============================================================
# ZXModelSelectorScreen -- Selector de nivel de modelo LLM
# ============================================================

class ZXModelSelectorScreen:
    """Pantalla de seleccion de modelo LLM con deteccion de hardware.

    Detecta el hardware del sistema, presenta 5 niveles con codificacion
    de color (verde/amarillo/rojo), permite descargar el modelo elegido
    y ejecuta un benchmark para verificar el rendimiento.
    """

    # Colores de recomendacion
    _COLORS = {
        "recommended": ZX_GREEN_BRIGHT,
        "tight": ZX_YELLOW,
        "not_recommended": ZX_RED_BRIGHT,
    }
    _LABELS = {
        "recommended": "Recomendado",
        "tight": "Justo",
        "not_recommended": "No recomendado",
    }

    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self.font = pygame.font.SysFont("Courier", ZX_TERMINAL_FONT_SIZE)
        if self.font.get_height() < 10:
            self.font = pygame.font.Font(None, ZX_TERMINAL_FONT_SIZE)
        self.btn_font = pygame.font.Font(None, ZX_TITLE_BUTTON_FONT_SIZE)
        self.small_font = pygame.font.SysFont("Courier", 16)
        if self.small_font.get_height() < 8:
            self.small_font = pygame.font.Font(None, 16)

    def run(self) -> str | None:
        """Bucle principal del selector de modelos.

        Returns:
            ``"selected"`` si se instalo y paso el benchmark,
            ``None`` si el usuario pulso ESC.
        """
        import threading

        from pong.benchmark import BenchmarkResult, run_benchmark
        from pong.config.llm_tiers import (
            LLM_TIERS,
            LLMTier,
            TIER_0_FALLBACK,
            TierRecommendation,
            best_recommended_tier,
            evaluate_all_tiers,
            evaluate_tier,
            tier_to_llm_config,
        )
        from pong.config.models import load_models_config, save_llm_config
        from pong.model_downloader import (
            ModelStatus,
            delete_llm_model,
            download_llm_for_tier,
            find_unused_llm_models,
            is_llm_tier_installed,
        )
        from pong.system_info import SystemInfo, detect_system_info

        clock = pygame.time.Clock()

        # -- Estado de la maquina de estados --
        state = "detecting"  # detecting | selecting | downloading | benchmarking | result | no_avx2 | onnx_downloading
        system_info: SystemInfo | None = None
        evaluations: list[tuple[LLMTier, TierRecommendation]] = []
        selected_idx: int = 0
        installed_set: set[str] = set()

        # Estado de descarga
        download_status = ModelStatus(name="", model_type="llm")
        download_lock = threading.Lock()
        download_thread: threading.Thread | None = None

        # Estado de benchmark
        benchmark_result: BenchmarkResult | None = None
        benchmark_tier: LLMTier | None = None

        # Estado de resultado
        result_text = ""
        result_color = ZX_GREEN_BRIGHT
        result_start = 0.0

        # Estado de limpieza
        unused_models: list[tuple[str, float]] = []
        cleanup_done = False

        # Tier 0 fallback (oculto hasta que se necesite)
        tier0_tried = False

        # ONNX fallback para CPUs sin AVX2
        onnx_available = False   # onnxruntime importable
        onnx_installed = False   # modelo ONNX ya descargado
        onnx_viable = False      # hardware viable para ONNX

        # Modelo activo actual (leido de models.toml, verificado en disco)
        active_model_label = ""
        try:
            current_llm_cfg, _ = load_models_config()
            if current_llm_cfg.filename and is_llm_tier_installed(current_llm_cfg.filename):
                for tier in LLM_TIERS:
                    if tier.filename == current_llm_cfg.filename:
                        active_model_label = tier.display_name
                        break
                if not active_model_label:
                    active_model_label = current_llm_cfg.resolved_display_name
        except Exception:
            pass

        # Mensajes de error/advertencia
        warning_text = ""
        warning_until = 0.0

        # Boton rects
        btn_width = ZX_TITLE_BUTTON_WIDTH
        btn_height = ZX_TITLE_BUTTON_HEIGHT
        action_rect = pygame.Rect(
            (WINDOW_WIDTH - btn_width) // 2,
            WINDOW_HEIGHT - ZX_BORDER_BOTTOM_HEIGHT - btn_height - 60,
            btn_width, btn_height,
        )
        back_rect = pygame.Rect(
            (WINDOW_WIDTH - btn_width) // 2,
            WINDOW_HEIGHT - ZX_BORDER_BOTTOM_HEIGHT - btn_height - 16,
            btn_width, btn_height,
        )

        # -- Lanzar deteccion en hilo --
        detect_done = threading.Event()

        def _detect() -> None:
            nonlocal system_info, evaluations, selected_idx, installed_set, state
            nonlocal onnx_available, onnx_installed, onnx_viable
            info = detect_system_info()

            # CPU sin AVX2: llama-cpp-python no puede arrancar
            if not info.has_avx2:
                system_info = info
                # Verificar si el fallback ONNX es viable
                from pong.config.llm_tiers import is_onnx_runtime_available, is_onnx_tier_viable
                from pong.model_downloader import is_onnx_model_installed
                onnx_viable = is_onnx_tier_viable(info)
                onnx_available = is_onnx_runtime_available()
                onnx_installed = is_onnx_model_installed()
                state = "no_avx2"
                detect_done.set()
                return

            evals = evaluate_all_tiers(info)
            best = best_recommended_tier(info)
            inst = set()
            for tier, _ in evals:
                if is_llm_tier_installed(tier.filename):
                    inst.add(tier.filename)
            # Si todos los tiers estan en rojo, añadir tier 0 como fallback
            all_red = all(
                r == TierRecommendation.NOT_RECOMMENDED for _, r in evals
            )
            if all_red:
                t0_rec = evaluate_tier(TIER_0_FALLBACK, info)
                evals.append((TIER_0_FALLBACK, t0_rec))
                if is_llm_tier_installed(TIER_0_FALLBACK.filename):
                    inst.add(TIER_0_FALLBACK.filename)
                # Pre-seleccionar tier 0 como mejor opcion
                selected_idx = len(evals) - 1
            system_info = info
            evaluations = evals
            installed_set = inst
            if not all_red:
                selected_idx = best.level - 1
            detect_done.set()

        threading.Thread(target=_detect, daemon=True).start()

        while True:
            now = time.monotonic()
            mouse_pos = pygame.mouse.get_pos()

            # -- Transiciones de estado --
            if state == "detecting" and detect_done.is_set():
                # _detect() puede haber cambiado state a "no_avx2"
                if state == "detecting":
                    state = "selecting"

            if state == "downloading" and download_thread is not None:
                if not download_thread.is_alive():
                    download_thread = None
                    with download_lock:
                        if download_status.installed:
                            # Descarga exitosa -> benchmark
                            state = "benchmarking"
                            benchmark_tier = evaluations[selected_idx][0]
                        elif download_status.error:
                            warning_text = f"Error: {download_status.error}"
                            warning_until = now + 5.0
                            state = "selecting"

            if state == "onnx_downloading" and download_thread is not None:
                if not download_thread.is_alive():
                    download_thread = None
                    with download_lock:
                        if download_status.installed:
                            onnx_installed = True
                            return "onnx"
                        elif download_status.error:
                            warning_text = f"Error: {download_status.error}"
                            warning_until = now + 5.0
                            state = "no_avx2"

            # -- Dibujar --
            self.screen.fill(ZX_BLACK)
            _draw_zx_border(self.screen)

            inner_x = ZX_BORDER_WIDTH
            inner_y = ZX_BORDER_TOP_HEIGHT
            inner_w = WINDOW_WIDTH - 2 * ZX_BORDER_WIDTH
            inner_h = WINDOW_HEIGHT - ZX_BORDER_TOP_HEIGHT - ZX_BORDER_BOTTOM_HEIGHT
            pygame.draw.rect(self.screen, ZX_BLACK, (inner_x, inner_y, inner_w, inner_h))

            x_start = inner_x + ZX_TERMINAL_PADDING_X
            y = inner_y + ZX_TERMINAL_PADDING_Y

            if state == "detecting":
                label = self.font.render("Analizando sistema...", False, ZX_CYAN_BRIGHT)
                self.screen.blit(label, (x_start, y))
                # Spinner animado
                dots = "." * (int(now * 3) % 4)
                dot_label = self.font.render(dots, False, ZX_WHITE)
                self.screen.blit(dot_label, (x_start + label.get_width() + 4, y))

            elif state == "selecting":
                y = self._draw_selecting(
                    x_start, y, mouse_pos, evaluations, selected_idx,
                    installed_set, system_info,
                )

                # Cartel de modelo activo
                if active_model_label:
                    active_text = f"Activo: {active_model_label}"
                    active_surf = self.small_font.render(active_text, False, ZX_CYAN)
                    ar = active_surf.get_rect(
                        centerx=WINDOW_WIDTH // 2,
                        bottom=action_rect.top - 8,
                    )
                    self.screen.blit(active_surf, ar)

                # Boton de accion
                tier = evaluations[selected_idx][0]
                is_installed = tier.filename in installed_set
                if is_installed:
                    btn_text = "USAR MODELO"
                    self._draw_screen_button(
                        action_rect, btn_text, mouse_pos,
                        text_color=ZX_GREEN_BRIGHT,
                        bg_normal=(0, 85, 0),
                        bg_hover=ZX_GREEN_DARK,
                        border_color=ZX_GREEN_BRIGHT,
                    )
                else:
                    btn_text = "DESCARGAR E INSTALAR"
                    self._draw_screen_button(
                        action_rect, btn_text, mouse_pos,
                        text_color=ZX_CYAN_BRIGHT,
                        bg_normal=ZX_BLUE_DARK,
                        bg_hover=ZX_BLUE_BRIGHT,
                        border_color=ZX_CYAN,
                    )

                # Boton volver
                self._draw_screen_button(
                    back_rect, "VOLVER (ESC)", mouse_pos,
                    text_color=ZX_WHITE,
                    bg_normal=ZX_GRAY_DARK,
                    bg_hover=(120, 120, 120),
                    border_color=ZX_WHITE,
                )

                # Advertencia
                if now < warning_until and warning_text:
                    warn = self.font.render(warning_text, False, ZX_RED_BRIGHT)
                    wr = warn.get_rect(centerx=WINDOW_WIDTH // 2, bottom=action_rect.top - 4)
                    self.screen.blit(warn, wr)

            elif state == "downloading":
                y = self._draw_downloading(x_start, y, download_status, download_lock)
                self._draw_screen_button(
                    back_rect, "ESC = Espera...", mouse_pos,
                    text_color=ZX_GRAY_DARK,
                    bg_normal=ZX_BLACK,
                    bg_hover=ZX_BLACK,
                    border_color=ZX_GRAY_DARK,
                )

            elif state == "benchmarking":
                # Delegar al benchmark (toma control del screen)
                assert benchmark_tier is not None
                config = tier_to_llm_config(benchmark_tier)
                bm_result = run_benchmark(self.screen, config)

                if bm_result is None:
                    # Cancelado
                    state = "selecting"
                    continue

                benchmark_result = bm_result

                if bm_result.passed:
                    if benchmark_tier.level == 0:
                        # Tier 0: guardar pero mostrar aviso de calidad
                        save_llm_config(config)
                        active_model_label = benchmark_tier.display_name
                        result_text = (
                            f"OK! FPS: {bm_result.fps_avg:.0f} | "
                            f"LLM: {bm_result.llm_avg_ms / 1000:.1f}s"
                        )
                        result_color = ZX_GREEN_BRIGHT
                        result_start = time.monotonic()
                        state = "tier0_warning"
                    else:
                        # Exito: guardar config y mostrar resultado
                        save_llm_config(config)
                        active_model_label = benchmark_tier.display_name
                        result_text = (
                            f"OK! FPS: {bm_result.fps_avg:.0f} | "
                            f"LLM: {bm_result.llm_avg_ms / 1000:.1f}s"
                        )
                        result_color = ZX_GREEN_BRIGHT
                        result_start = time.monotonic()
                        state = "result"
                else:
                    # Fallo: intentar nivel inferior
                    current_level = benchmark_tier.level
                    if current_level <= 0:
                        # Tier 0 tambien fallo: no hay mas opciones
                        warning_text = (
                            "Hardware insuficiente para cualquier modelo LLM"
                        )
                        warning_until = time.monotonic() + 8.0
                        state = "selecting"
                    elif current_level <= 1 and not tier0_tried:
                        # Tier 1 fallo: intentar tier 0 fallback
                        tier0_tried = True
                        benchmark_tier = TIER_0_FALLBACK
                        # Añadir tier 0 a evaluations si no esta
                        t0_in_evals = any(
                            t.level == 0 for t, _ in evaluations
                        )
                        if not t0_in_evals:
                            assert system_info is not None
                            t0_rec = evaluate_tier(TIER_0_FALLBACK, system_info)
                            evaluations.append((TIER_0_FALLBACK, t0_rec))
                        selected_idx = len(evaluations) - 1

                        if TIER_0_FALLBACK.filename in installed_set:
                            warning_text = (
                                f"Rendimiento insuficiente. Probando {TIER_0_FALLBACK.display_name}..."
                            )
                            warning_until = time.monotonic() + 3.0
                            state = "benchmarking"
                        else:
                            warning_text = (
                                f"Rendimiento insuficiente. Descargando {TIER_0_FALLBACK.display_name}..."
                            )
                            warning_until = time.monotonic() + 3.0
                            download_status = ModelStatus(
                                name=TIER_0_FALLBACK.display_name,
                                model_type="llm",
                            )
                            download_thread = threading.Thread(
                                target=download_llm_for_tier,
                                args=(
                                    TIER_0_FALLBACK.repo_id,
                                    TIER_0_FALLBACK.gguf_pattern,
                                    TIER_0_FALLBACK.filename,
                                    TIER_0_FALLBACK.download_url,
                                    TIER_0_FALLBACK.split,
                                    download_status,
                                    download_lock,
                                ),
                                daemon=True,
                            )
                            download_thread.start()
                            state = "downloading"
                    elif current_level <= 1:
                        # Tier 0 ya se intento y fallo
                        warning_text = (
                            "Hardware insuficiente para cualquier modelo LLM"
                        )
                        warning_until = time.monotonic() + 8.0
                        state = "selecting"
                    else:
                        # Bajar al nivel anterior
                        next_idx = current_level - 2  # level es 1-based
                        selected_idx = next_idx
                        next_tier = evaluations[next_idx][0]
                        benchmark_tier = next_tier

                        if next_tier.filename in installed_set:
                            # Ya descargado: ir directo a benchmark
                            warning_text = (
                                f"Rendimiento insuficiente. Probando {next_tier.display_name}..."
                            )
                            warning_until = time.monotonic() + 3.0
                            state = "benchmarking"
                        else:
                            # Descargar el tier inferior
                            warning_text = (
                                f"Rendimiento insuficiente. Descargando {next_tier.display_name}..."
                            )
                            warning_until = time.monotonic() + 3.0
                            download_status = ModelStatus(
                                name=next_tier.display_name,
                                model_type="llm",
                            )
                            download_thread = threading.Thread(
                                target=download_llm_for_tier,
                                args=(
                                    next_tier.repo_id,
                                    next_tier.gguf_pattern,
                                    next_tier.filename,
                                    next_tier.download_url,
                                    next_tier.split,
                                    download_status,
                                    download_lock,
                                ),
                                daemon=True,
                            )
                            download_thread.start()
                            state = "downloading"
                continue

            elif state == "no_avx2":
                # CPU sin AVX2: ofrecer fallback ONNX o continuar sin IA
                self._draw_no_avx2_offer(
                    x_start, y, action_rect, back_rect, mouse_pos,
                    system_info, onnx_available, onnx_installed, onnx_viable,
                )

            elif state == "onnx_downloading":
                # Descargando modelo ONNX
                self._draw_onnx_downloading(
                    x_start, y, download_status, download_lock,
                )

            elif state == "tier0_warning":
                # Aviso de calidad limitada para tier 0
                self._draw_tier0_warning(
                    x_start, y, action_rect, mouse_pos,
                )

            elif state == "result":
                # Mostrar resultado 3 segundos, luego verificar limpieza
                self._draw_result(x_start, y, result_text, result_color, benchmark_result)
                if now - result_start > 3.0:
                    # Buscar modelos no usados
                    assert benchmark_tier is not None
                    unused_models = find_unused_llm_models(benchmark_tier.filename)
                    if unused_models:
                        state = "cleanup"
                    else:
                        return "selected"

            elif state == "cleanup":
                total_gb = sum(gb for _, gb in unused_models)
                self._draw_cleanup(
                    x_start, y, unused_models, total_gb,
                    action_rect, back_rect, mouse_pos,
                )

                # Los botones se manejan en la seccion de eventos abajo

            pygame.display.flip()

            # -- Eventos --
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit(0)

                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if state == "selecting":
                            return None
                        elif state == "downloading":
                            warning_text = "Espera a que termine la descarga..."
                            warning_until = now + 2.0

                if state == "selecting" and event.type == pygame.MOUSEBUTTONDOWN:
                    # Click en un tier
                    for idx, (tier, rec) in enumerate(evaluations):
                        tier_rect = self._tier_row_rect(x_start, idx)
                        if tier_rect.collidepoint(event.pos):
                            selected_idx = idx
                            break

                    # Click en boton accion
                    if action_rect.collidepoint(event.pos):
                        tier = evaluations[selected_idx][0]
                        rec = evaluations[selected_idx][1]

                        # Advertencia si es rojo
                        if rec == TierRecommendation.NOT_RECOMMENDED:
                            # Toggle: primer click muestra aviso, segundo confirma
                            if now < warning_until and "no funcionar" in warning_text:
                                pass  # ya avisado, dejar pasar
                            else:
                                warning_text = "Este modelo puede no funcionar bien. Click de nuevo para confirmar."
                                warning_until = now + 4.0
                                continue

                        if tier.filename in installed_set:
                            # Ya instalado: ir a benchmark
                            state = "benchmarking"
                            benchmark_tier = tier
                        else:
                            # Descargar
                            download_status = ModelStatus(
                                name=tier.display_name,
                                model_type="llm",
                            )
                            download_thread = threading.Thread(
                                target=download_llm_for_tier,
                                args=(
                                    tier.repo_id,
                                    tier.gguf_pattern,
                                    tier.filename,
                                    tier.download_url,
                                    tier.split,
                                    download_status,
                                    download_lock,
                                ),
                                daemon=True,
                            )
                            download_thread.start()
                            state = "downloading"
                            benchmark_tier = tier

                    # Click en boton volver
                    if back_rect.collidepoint(event.pos) and state == "selecting":
                        return None

                if state == "no_avx2" and event.type == pygame.MOUSEBUTTONDOWN:
                    if action_rect.collidepoint(event.pos):
                        if onnx_viable and onnx_available:
                            if onnx_installed:
                                return "onnx"
                            else:
                                from pong.model_downloader import download_onnx_model
                                download_status = ModelStatus(
                                    name="DistilGPT-2 ONNX",
                                    model_type="onnx",
                                )
                                download_thread = threading.Thread(
                                    target=download_onnx_model,
                                    args=(download_status, download_lock),
                                    daemon=True,
                                )
                                download_thread.start()
                                state = "onnx_downloading"
                        else:
                            # Sin ONNX: action_rect es "CONTINUAR SIN IA"
                            return None
                    if back_rect.collidepoint(event.pos):
                        # back_rect es "CONTINUAR SIN IA" cuando hay ONNX
                        return None

                if state == "no_avx2" and event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return None

                if state == "tier0_warning" and event.type == pygame.MOUSEBUTTONDOWN:
                    if action_rect.collidepoint(event.pos):
                        # Entendido: pasar a resultado
                        result_start = time.monotonic()
                        state = "result"

                if state == "tier0_warning" and event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN:
                        result_start = time.monotonic()
                        state = "result"

                if state == "cleanup" and event.type == pygame.MOUSEBUTTONDOWN:
                    if action_rect.collidepoint(event.pos):
                        # Eliminar modelos no usados
                        for fname, _ in unused_models:
                            delete_llm_model(fname)
                        return "selected"
                    if back_rect.collidepoint(event.pos):
                        # Conservar modelos
                        return "selected"

                if state == "cleanup" and event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return "selected"

            clock.tick(30)

    # ----------------------------------------------------------
    # Tier row geometry
    # ----------------------------------------------------------

    _TIER_ROW_Y_START = 130  # offset desde inner_y
    _TIER_ROW_HEIGHT = 44
    _TIER_ROW_WIDTH = WINDOW_WIDTH - 2 * ZX_BORDER_WIDTH - 2 * ZX_TERMINAL_PADDING_X

    def _tier_row_rect(self, x_start: int, idx: int) -> pygame.Rect:
        """Rectangulo clickeable de una fila de tier."""
        y = ZX_BORDER_TOP_HEIGHT + self._TIER_ROW_Y_START + idx * self._TIER_ROW_HEIGHT
        return pygame.Rect(x_start, y, self._TIER_ROW_WIDTH, self._TIER_ROW_HEIGHT)

    # ----------------------------------------------------------
    # Sub-draws
    # ----------------------------------------------------------

    def _draw_selecting(
        self,
        x_start: int,
        y: int,
        mouse_pos: tuple[int, int],
        evaluations: list[tuple[Any, Any]],
        selected_idx: int,
        installed_set: set[str],
        system_info: Any,
    ) -> int:
        """Dibuja el estado SELECTING: info sistema + 5 filas de tier."""
        # Cabecera
        hdr = self.font.render("(C) 2025 JGF", False, ZX_WHITE)
        self.screen.blit(hdr, (x_start, y))
        y += ZX_TERMINAL_LINE_HEIGHT

        title = self.font.render("SELECTOR DE MODELO LLM", False, ZX_CYAN_BRIGHT)
        self.screen.blit(title, (x_start, y))
        y += ZX_TERMINAL_LINE_HEIGHT + 4

        # Info del sistema
        if system_info is not None:
            info_text = (
                f"RAM: {system_info.total_ram_gb:.0f} GB | "
                f"GPU: {system_info.gpu_name} ({system_info.gpu_type.upper()}) | "
                f"Disco: {system_info.disk_free_gb:.0f} GB libres"
            )
            info_label = self.small_font.render(info_text, False, ZX_GRAY_LIGHT)
            self.screen.blit(info_label, (x_start, y))
        y += ZX_TERMINAL_LINE_HEIGHT + 4

        # Filas de tier
        row_rect = pygame.Rect(0, 0, 0, 0)
        for idx, (tier, rec) in enumerate(evaluations):
            row_rect = self._tier_row_rect(x_start, idx)
            row_y = row_rect.y

            # Highlight si seleccionado
            if idx == selected_idx:
                pygame.draw.rect(self.screen, (30, 30, 60), row_rect)
                pygame.draw.rect(self.screen, ZX_CYAN, row_rect, 1)
            elif row_rect.collidepoint(mouse_pos):
                pygame.draw.rect(self.screen, (20, 20, 40), row_rect)

            color = self._COLORS.get(rec.value, ZX_WHITE)
            label_text = self._LABELS.get(rec.value, "")

            # Indicador de color (cuadradito)
            pygame.draw.rect(self.screen, color, (x_start + 4, row_y + 12, 12, 12))

            # Nombre del tier
            name_text = f"{tier.display_name} ({tier.model_size_label})"
            name_label = self.font.render(name_text, False, ZX_WHITE)
            self.screen.blit(name_label, (x_start + 22, row_y + 4))

            # Estado: Instalado / Recomendado / Justo / No recomendado
            is_installed = tier.filename in installed_set
            if is_installed:
                status_text = "Instalado"
                status_color = ZX_GREEN_BRIGHT
            else:
                status_text = label_text
                status_color = color

            status_label = self.small_font.render(status_text, False, status_color)
            self.screen.blit(status_label, (x_start + 22, row_y + 26))

        # Nota al pie
        y = row_rect.y + self._TIER_ROW_HEIGHT + 8
        note = self.small_font.render(
            "Modelos mas grandes = narraciones mas creativas y coherentes",
            False, ZX_GRAY_DARK,
        )
        self.screen.blit(note, (x_start, y))
        y += ZX_TERMINAL_LINE_HEIGHT

        # Aviso de RAM disponible baja (unified memory)
        if system_info is not None and system_info.unified_memory:
            used_pct = 1.0 - (system_info.available_ram_gb / system_info.total_ram_gb)
            if used_pct >= 0.75:
                warn_text = (
                    "! Uso de RAM elevado: cierra aplicaciones "
                    "mientras ejecutes PongIA"
                )
                warn_surf = self.small_font.render(warn_text, False, ZX_RED_BRIGHT)
                wr = warn_surf.get_rect(centerx=WINDOW_WIDTH // 2, top=y + 4)
                self.screen.blit(warn_surf, wr)
                y = wr.bottom

        return y

    def _draw_downloading(
        self,
        x_start: int,
        y: int,
        status: Any,
        lock: threading.Lock,
    ) -> int:
        """Dibuja el estado DOWNLOADING con barra de progreso."""
        hdr = self.font.render("(C) 2025 JGF", False, ZX_WHITE)
        self.screen.blit(hdr, (x_start, y))
        y += ZX_TERMINAL_LINE_HEIGHT

        title = self.font.render("DESCARGANDO MODELO LLM", False, ZX_CYAN_BRIGHT)
        self.screen.blit(title, (x_start, y))
        y += ZX_TERMINAL_LINE_HEIGHT * 2

        with lock:
            name = status.name
            progress = status.progress
            status_text = status.status_text

        name_label = self.font.render(name, False, ZX_WHITE)
        self.screen.blit(name_label, (x_start, y))
        y += ZX_TERMINAL_LINE_HEIGHT

        # Estado
        if "Descargando" in status_text:
            color = ZX_CYAN_BRIGHT
        elif "Instalado" in status_text:
            color = ZX_GREEN_BRIGHT
        elif "Error" in status_text:
            color = ZX_RED_BRIGHT
        else:
            color = ZX_YELLOW

        st_label = self.font.render(f"  Estado: {status_text}", False, color)
        self.screen.blit(st_label, (x_start, y))
        y += ZX_TERMINAL_LINE_HEIGHT

        # Barra de progreso
        if progress != 0.0:
            bar = ZXDownloadScreen._progress_bar(progress)
            bar_label = self.font.render(f"  {bar}", False, ZX_GREEN_BRIGHT)
            self.screen.blit(bar_label, (x_start, y))
        y += ZX_TERMINAL_LINE_HEIGHT

        return y

    def _draw_no_avx2_offer(
        self,
        x_start: int,
        y: int,
        action_rect: pygame.Rect,
        back_rect: pygame.Rect,
        mouse_pos: tuple[int, int],
        system_info: Any,
        onnx_available: bool,
        onnx_installed: bool,
        onnx_viable: bool,
    ) -> None:
        """Aviso de CPU sin AVX2 con oferta de modelo alternativo ONNX."""
        hdr = self.font.render("(C) 2025 JGF", False, ZX_WHITE)
        self.screen.blit(hdr, (x_start, y))
        y += ZX_TERMINAL_LINE_HEIGHT

        title = self.font.render("CPU NO COMPATIBLE CON IA", False, ZX_RED_BRIGHT)
        self.screen.blit(title, (x_start, y))
        y += ZX_TERMINAL_LINE_HEIGHT * 2

        cpu_name = system_info.cpu_name if system_info else "Desconocida"

        if onnx_viable and onnx_available:
            # Oferta de fallback ONNX
            lines = [
                "Tu procesador no soporta instrucciones AVX2,",
                "necesarias para los modelos principales.",
                "",
                f"Tu CPU: {cpu_name}",
                "",
                "Hay un modelo alternativo disponible (DistilGPT-2)",
                "que funciona en tu hardware. La narracion sera",
                "mas basica pero funcional (~87 MB de descarga).",
            ]
        elif onnx_viable and not onnx_available:
            # ONNX viable pero onnxruntime no instalado
            lines = [
                "Tu procesador no soporta instrucciones AVX2.",
                "",
                f"Tu CPU: {cpu_name}",
                "",
                "Existe un modelo alternativo, pero requiere",
                "el modulo 'onnxruntime' que no esta instalado.",
                "Instala con: pip install onnxruntime",
                "",
                "El juego funcionara sin narracion IA.",
            ]
        else:
            # Sin fallback posible
            lines = [
                "Tu procesador no soporta instrucciones AVX2,",
                "necesarias para ejecutar los modelos de IA.",
                "",
                f"Tu CPU: {cpu_name}",
                "",
                "El juego funcionara normalmente, pero la",
                "narracion por IA no estara disponible.",
            ]

        for line in lines:
            if line:
                color = ZX_WHITE
                if line.startswith("Tu CPU:"):
                    color = ZX_YELLOW
                elif line.startswith("Instala con:"):
                    color = ZX_CYAN_BRIGHT
                label = self.small_font.render(line, False, color)
                self.screen.blit(label, (x_start, y))
            y += ZX_TERMINAL_LINE_HEIGHT

        if onnx_viable and onnx_available:
            # Boton principal: descargar o usar modelo ONNX
            if onnx_installed:
                btn_label = "USAR MODELO ALTERNATIVO"
            else:
                btn_label = "DESCARGAR MODELO (~87 MB)"
            self._draw_screen_button(
                action_rect, btn_label, mouse_pos,
                text_color=ZX_GREEN_BRIGHT,
                bg_normal=(0, 85, 0),
                bg_hover=(0, 120, 0),
                border_color=ZX_GREEN_BRIGHT,
            )
            # Boton secundario: continuar sin IA
            self._draw_screen_button(
                back_rect, "CONTINUAR SIN IA", mouse_pos,
                text_color=ZX_RED_BRIGHT,
                bg_normal=(85, 0, 0),
                bg_hover=(120, 0, 0),
                border_color=ZX_RED_BRIGHT,
            )
        else:
            # Solo boton de continuar sin IA
            self._draw_screen_button(
                action_rect, "CONTINUAR SIN IA", mouse_pos,
                text_color=ZX_RED_BRIGHT,
                bg_normal=(85, 0, 0),
                bg_hover=(120, 0, 0),
                border_color=ZX_RED_BRIGHT,
            )

    def _draw_onnx_downloading(
        self,
        x_start: int,
        y: int,
        status: Any,
        lock: Any,
    ) -> None:
        """Dibuja progreso de descarga del modelo ONNX."""
        hdr = self.font.render("(C) 2025 JGF", False, ZX_WHITE)
        self.screen.blit(hdr, (x_start, y))
        y += ZX_TERMINAL_LINE_HEIGHT

        title = self.font.render("DESCARGANDO MODELO ALTERNATIVO", False, ZX_CYAN_BRIGHT)
        self.screen.blit(title, (x_start, y))
        y += ZX_TERMINAL_LINE_HEIGHT * 2

        with lock:
            progress = status.progress
            status_text = status.status_text

        label = self.small_font.render(status_text, False, ZX_WHITE)
        self.screen.blit(label, (x_start, y))
        y += ZX_TERMINAL_LINE_HEIGHT * 2

        # Barra de progreso
        bar_width = WINDOW_WIDTH - 2 * ZX_BORDER_WIDTH - 2 * ZX_TERMINAL_PADDING_X
        bar_height = 16
        bar_x = x_start
        bar_y = y

        # Fondo de la barra
        pygame.draw.rect(self.screen, (40, 40, 40), (bar_x, bar_y, bar_width, bar_height))

        if progress > 0:
            fill_width = int(bar_width * min(progress, 1.0))
            pygame.draw.rect(self.screen, ZX_GREEN_BRIGHT, (bar_x, bar_y, fill_width, bar_height))
        elif progress < 0:
            # Indeterminado: barra animada
            import time as _time
            t = _time.monotonic() % 2.0
            pos = int((t / 2.0) * bar_width)
            w = bar_width // 4
            pygame.draw.rect(self.screen, ZX_CYAN_BRIGHT, (bar_x + pos, bar_y, w, bar_height))

        # Borde de la barra
        pygame.draw.rect(self.screen, ZX_WHITE, (bar_x, bar_y, bar_width, bar_height), 1)

        y += bar_height + ZX_TERMINAL_LINE_HEIGHT
        hint = self.small_font.render("Espera mientras se descarga el modelo...", False, ZX_GRAY_LIGHT)
        self.screen.blit(hint, (x_start, y))

    def _draw_tier0_warning(
        self,
        x_start: int,
        y: int,
        action_rect: pygame.Rect,
        mouse_pos: tuple[int, int],
    ) -> None:
        """Aviso de calidad limitada tras pasar benchmark con tier 0."""
        hdr = self.font.render("(C) 2025 JGF", False, ZX_WHITE)
        self.screen.blit(hdr, (x_start, y))
        y += ZX_TERMINAL_LINE_HEIGHT

        title = self.font.render("MODELO DE EMERGENCIA", False, ZX_YELLOW)
        self.screen.blit(title, (x_start, y))
        y += ZX_TERMINAL_LINE_HEIGHT * 2

        lines = [
            "Tu hardware no soporta los modelos principales.",
            "Se ha seleccionado un modelo minimo (1.5B parametros).",
            "",
            "La calidad de las narraciones sera limitada:",
            "  - Frases menos naturales y mas repetitivas",
            "  - Menor coherencia con el contexto del partido",
            "",
            "Puedes jugar igualmente, pero la experiencia",
            "de la IA narradora no sera optima.",
        ]
        for line in lines:
            if line:
                color = ZX_WHITE if not line.startswith("  -") else ZX_GRAY_LIGHT
                label = self.small_font.render(line, False, color)
                self.screen.blit(label, (x_start, y))
            y += ZX_TERMINAL_LINE_HEIGHT

        self._draw_screen_button(
            action_rect, "ENTENDIDO", mouse_pos,
            text_color=ZX_YELLOW,
            bg_normal=(85, 85, 0),
            bg_hover=(120, 120, 0),
            border_color=ZX_YELLOW,
        )

    def _draw_result(
        self,
        x_start: int,
        y: int,
        text: str,
        color: tuple[int, int, int],
        result: Any,
    ) -> None:
        """Dibuja la pantalla de resultado del benchmark."""
        hdr = self.font.render("(C) 2025 JGF", False, ZX_WHITE)
        self.screen.blit(hdr, (x_start, y))
        y += ZX_TERMINAL_LINE_HEIGHT

        title = self.font.render("RESULTADO DEL BENCHMARK", False, ZX_CYAN_BRIGHT)
        self.screen.blit(title, (x_start, y))
        y += ZX_TERMINAL_LINE_HEIGHT * 2

        result_label = self.font.render(text, False, color)
        self.screen.blit(result_label, (x_start, y))
        y += ZX_TERMINAL_LINE_HEIGHT * 2

        info = self.small_font.render("Volviendo a la pantalla principal...", False, ZX_GRAY_LIGHT)
        self.screen.blit(info, (x_start, y))

    def _draw_cleanup(
        self,
        x_start: int,
        y: int,
        unused: list[tuple[str, float]],
        total_gb: float,
        action_rect: pygame.Rect,
        back_rect: pygame.Rect,
        mouse_pos: tuple[int, int],
    ) -> None:
        """Dibuja dialogo de limpieza de modelos no usados."""
        hdr = self.font.render("(C) 2025 JGF", False, ZX_WHITE)
        self.screen.blit(hdr, (x_start, y))
        y += ZX_TERMINAL_LINE_HEIGHT

        title = self.font.render("MODELOS SIN USAR", False, ZX_YELLOW)
        self.screen.blit(title, (x_start, y))
        y += ZX_TERMINAL_LINE_HEIGHT * 2

        msg = self.font.render(
            f"Hay {len(unused)} modelo(s) sin usar ({total_gb:.1f} GB):",
            False, ZX_WHITE,
        )
        self.screen.blit(msg, (x_start, y))
        y += ZX_TERMINAL_LINE_HEIGHT + 4

        for fname, size_gb in unused:
            line = self.small_font.render(
                f"  - {fname}  ({size_gb:.1f} GB)", False, ZX_GRAY_LIGHT,
            )
            self.screen.blit(line, (x_start, y))
            y += ZX_TERMINAL_LINE_HEIGHT

        y += ZX_TERMINAL_LINE_HEIGHT
        hint = self.small_font.render(
            "Eliminar libera espacio. Conservar permite cambiar rapido.",
            False, ZX_GRAY_DARK,
        )
        self.screen.blit(hint, (x_start, y))

        # Botones
        self._draw_screen_button(
            action_rect, "ELIMINAR", mouse_pos,
            text_color=ZX_RED_BRIGHT,
            bg_normal=(85, 0, 0),
            bg_hover=ZX_RED_DARK,
            border_color=ZX_RED_BRIGHT,
        )
        self._draw_screen_button(
            back_rect, "CONSERVAR", mouse_pos,
            text_color=ZX_GREEN_BRIGHT,
            bg_normal=(0, 85, 0),
            bg_hover=ZX_GREEN_DARK,
            border_color=ZX_GREEN_BRIGHT,
        )

    def _draw_screen_button(
        self,
        rect: pygame.Rect,
        text: str,
        mouse_pos: tuple[int, int],
        *,
        text_color: tuple[int, int, int],
        bg_normal: tuple[int, int, int],
        bg_hover: tuple[int, int, int],
        border_color: tuple[int, int, int],
    ) -> None:
        """Dibuja un boton en la pantalla del selector."""
        hovering = rect.collidepoint(mouse_pos)
        bg = bg_hover if hovering else bg_normal
        pygame.draw.rect(self.screen, bg, rect)
        pygame.draw.rect(self.screen, border_color, rect, 2)
        label = self.btn_font.render(text, False, text_color)
        label_rect = label.get_rect(center=rect.center)
        self.screen.blit(label, label_rect)
