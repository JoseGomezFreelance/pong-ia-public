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
import time

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

    def __init__(self, screen: pygame.Surface) -> None:
        """
        Args:
            screen: Superficie principal de pygame.
        """
        self.screen: pygame.Surface = screen
        self._surface: pygame.Surface | None = None

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

    def display(self) -> str:
        """Muestra la portada con botones JUGAR / INSTALAR MODELOS IA.

        Returns:
            ``"play"`` si el usuario elige jugar,
            ``"install"`` si elige instalar modelos.
        """
        if self._surface is None:
            self.build()

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

            # Estado de cada modelo
            with lock:
                snap = [
                    (s.name, s.size_hint, s.installed, s.progress,
                     s.status_text, s.error)
                    for s in statuses
                ]

            for idx, (name, size, installed, progress, status_text, error) in enumerate(snap):
                # Nombre + tamano
                label = f"{idx + 1}. {name}  {size}"
                self.screen.blit(
                    self.font.render(label, False, ZX_WHITE), (x_start, y),
                )
                y += ZX_TERMINAL_LINE_HEIGHT

                # Estado
                if error:
                    color = ZX_RED_BRIGHT
                elif installed:
                    color = ZX_GREEN_BRIGHT
                elif "Descargando" in status_text:
                    color = ZX_CYAN_BRIGHT
                else:
                    color = ZX_YELLOW

                display_status = status_text
                if installed and not error:
                    display_status = "Instalado"

                st_surf = self.font.render(
                    f"   Estado: {display_status}", False, color,
                )
                self.screen.blit(st_surf, (x_start, y))
                y += ZX_TERMINAL_LINE_HEIGHT

                # Barra de progreso (solo si descargando)
                if not installed and not error and progress != 0.0:
                    bar = self._progress_bar(progress)
                    bar_surf = self.font.render(
                        f"   {bar}", False, ZX_GREEN_BRIGHT,
                    )
                    self.screen.blit(bar_surf, (x_start, y))
                y += ZX_TERMINAL_LINE_HEIGHT

                y += ZX_TERMINAL_LINE_HEIGHT // 2  # separador

            # Espacio total estimado
            total_hint = self.font.render(
                "Espacio total: ~5 GB", False, ZX_GRAY_LIGHT,
            )
            self.screen.blit(total_hint, (x_start, y))

            # Boton de accion
            all_installed = all(s[2] for s in snap)  # installed flag
            any_pending = not all_installed and not downloading

            if completed or all_installed:
                self._draw_screen_button(
                    action_rect, "COMPLETADO", mouse_pos,
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
                    action_rect, "DESCARGAR TODO", mouse_pos,
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
                    if action_rect.collidepoint(event.pos) and any_pending:
                        downloading = True
                        download_thread = threading.Thread(
                            target=run_downloads,
                            args=(statuses, lock),
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
