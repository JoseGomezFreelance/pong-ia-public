"""
pong/renderer.py -- Dibujado de todos los elementos visuales.

Este modulo se encarga de pintar todo lo que ves en pantalla:
- La zona de juego (pelota, paletas, linea central).
- La banda de marcador (arriba).
- La zona de narracion (abajo).
- La pantalla final de depuracion.

La clase Renderer recibe por parametro lo que necesita dibujar
(pantalla, fuentes, marcador, entidades...) en vez de acceder a
variables globales. Asi se puede modificar el dibujado sin tocar
la logica del juego.

Los metodos de pantalla final y galeria de logros estan en mixins
separados para mantener este archivo enfocado en el dibujado del
juego en tiempo real:
- renderer_end_screen.py → EndScreenMixin
- renderer_achievements.py → AchievementsMixin
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from pong.achievements import AchievementDef
    from pong.entities import Ball, Paddle
    from pong.rpg_engine import RPGState
    from pong.scoring import ScoreState

from pong.config.gameplay import PADDLE_HEIGHT
from pong.config.layout import (
    CENTER_DASH_GAP,
    CENTER_DASH_HEIGHT,
    CENTER_DASH_WIDTH,
    GAME_AREA_HEIGHT,
    GAME_AREA_TOP,
    LLM_STATUS_FONT_SIZE,
    NARRATION_FONT_SIZE,
    NARRATION_HEIGHT,
    NARRATION_LINE_SPACING,
    NARRATION_MARGIN_X,
    NARRATION_MAX_VISIBLE_LINES,
    NARRATION_TEXT_OFFSET_Y,
    NARRATION_TOP,
    SCORE_BAND_HEIGHT,
    SCORE_DETAILS_FONT_SIZE,
    SCORE_FONT_SIZE,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
    XP_BAR_HEIGHT,
    XP_BAR_TOP,
)
from pong.config.media import IMAGEGEN_OVERLAY_ALPHA, IMAGEGEN_TRANSITION_SECONDS
from pong.config.narrator import ANSWER_FONT_SIZE, ANSWER_LABEL_X, COLOR_ANSWER_INACTIVE, COUNTDOWN_FONT_SIZE
from pong.config.ui_achievements import ACHIEVEMENT_POPUP_FONT_FLAVOR, ACHIEVEMENT_POPUP_FONT_NAME
from pong.config.ui_end_screen import DEBUG_FONT_SIZE, RECORDS_TABLE_FONT_SIZE, SUMMARY_FONT_SIZE
from pong.theme import ThemeColors

from pong.renderer_end_screen import EndScreenMixin
from pong.renderer_achievements import AchievementsMixin
from pong.renderer_leaderboard import LeaderboardRendererMixin
from pong.renderer_rpg import RPGRendererMixin


class Renderer(LeaderboardRendererMixin, RPGRendererMixin, EndScreenMixin, AchievementsMixin):
    """
    Dibuja todos los elementos visuales del juego en la pantalla.

    Separa la logica de "que dibujar" del "que pasa en el juego".
    El Game le dice al Renderer "dibuja esto" y el Renderer se encarga
    de los detalles de pygame (colores, posiciones, fuentes, etc.).

    Atributos:
        screen:             Superficie principal de pygame.
        font:               Fuente grande para titulos.
        score_details_font: Fuente para el marcador detallado.
        narration_font:     Fuente para el texto de narracion.
        debug_font:         Fuente para la pantalla de depuracion.
    """

    def __init__(self, screen: pygame.Surface) -> None:
        """
        Inicializa el renderer con la pantalla y crea las fuentes.

        Args:
            screen: Superficie de pygame donde se dibuja todo.
        """
        self.screen: pygame.Surface = screen
        self.font: pygame.font.Font = pygame.font.Font(None, SCORE_FONT_SIZE)
        self.score_details_font: pygame.font.Font = pygame.font.Font(None, SCORE_DETAILS_FONT_SIZE)
        self.narration_font: pygame.font.Font = pygame.font.Font(None, NARRATION_FONT_SIZE)
        self.llm_status_font: pygame.font.Font = pygame.font.Font(None, LLM_STATUS_FONT_SIZE)
        self.debug_font: pygame.font.Font = pygame.font.Font(None, DEBUG_FONT_SIZE)
        self.answer_font: pygame.font.Font = pygame.font.Font(None, ANSWER_FONT_SIZE)
        self.countdown_font: pygame.font.Font = pygame.font.Font(None, COUNTDOWN_FONT_SIZE)
        self.summary_font: pygame.font.Font = pygame.font.Font(None, SUMMARY_FONT_SIZE)
        self.copy_button_font: pygame.font.Font = pygame.font.Font(None, 26)
        self.records_font: pygame.font.Font = pygame.font.Font(None, RECORDS_TABLE_FONT_SIZE)
        self.achievement_name_font: pygame.font.Font = pygame.font.Font(None, ACHIEVEMENT_POPUP_FONT_NAME)
        self.achievement_flavor_font: pygame.font.Font = pygame.font.Font(None, ACHIEVEMENT_POPUP_FONT_FLAVOR)
        self.achievement_tile_name_font: pygame.font.Font = pygame.font.Font(None, 20)
        self.achievement_tile_desc_font: pygame.font.Font = pygame.font.Font(None, 16)
        self.achievement_category_font: pygame.font.Font = pygame.font.Font(None, 24)
        self.achievement_progress_font: pygame.font.Font = pygame.font.Font(None, 30)
        self.copy_button_rect: pygame.Rect = self._build_copy_button_rect()
        self.restart_button_rect: pygame.Rect = self._build_restart_button_rect()
        self.export_button_rect: pygame.Rect = self._build_export_button_rect()
        self.logros_button_rect: pygame.Rect | None = None
        self.debug_button_rect: pygame.Rect | None = None
        self.debug_back_button_rect: pygame.Rect = self._build_achievements_back_button_rect()
        self.achievements_back_button_rect: pygame.Rect = self._build_achievements_back_button_rect()

        # --- RPG ---
        self._init_rpg_renderer()

        # --- Leaderboard ---
        self._init_leaderboard_renderer()

        # --- Fondo generativo (fase visual con IA de imagen) ---
        self._bg_surface: pygame.Surface | None = None          # Surface actual del fondo generado
        self._bg_prev_surface: pygame.Surface | None = None     # Surface anterior (para crossfade)
        self._bg_transition_t: float = 1.0      # Progreso de transicion (0.0 -> 1.0)

        # Overlay oscuro cacheado (evita crear Surface nueva cada frame)
        self._bg_overlay = pygame.Surface(
            (WINDOW_WIDTH, GAME_AREA_HEIGHT), pygame.SRCALPHA
        )
        self._bg_overlay.fill((0, 0, 0, IMAGEGEN_OVERLAY_ALPHA))

    # --------------------------------------------------------
    # Fondo generativo
    # --------------------------------------------------------

    def set_background_image(self, surface: pygame.Surface) -> None:
        """Establece una nueva imagen de fondo con transicion suave."""
        self._bg_prev_surface = self._bg_surface
        self._bg_surface = surface
        self._bg_transition_t = 0.0

    def update_background_transition(self, dt: float) -> None:
        """Avanza el crossfade entre imagenes de fondo."""
        if self._bg_transition_t < 1.0:
            self._bg_transition_t = min(
                1.0, self._bg_transition_t + dt / IMAGEGEN_TRANSITION_SECONDS
            )

    def clear_background_image(self) -> None:
        """Elimina la imagen de fondo (vuelve al negro solido)."""
        self._bg_surface = None
        self._bg_prev_surface = None
        self._bg_transition_t = 1.0

    def _draw_generated_background(self, colors: ThemeColors) -> None:
        """Dibuja el fondo generado por IA con crossfade y overlay oscuro."""
        # 1. Fondo negro base (cubre toda la pantalla incluyendo marcador)
        self.screen.fill(colors.background)

        # 2. Crossfade entre imagen anterior y nueva (solo zona de juego)
        if self._bg_transition_t < 1.0:
            if self._bg_prev_surface is not None:
                prev_alpha = int(255 * (1.0 - self._bg_transition_t))
                self._bg_prev_surface.set_alpha(prev_alpha)
                self.screen.blit(self._bg_prev_surface, (0, GAME_AREA_TOP))
            cur_alpha = int(255 * self._bg_transition_t)
            if self._bg_surface is not None:
                self._bg_surface.set_alpha(cur_alpha)
                self.screen.blit(self._bg_surface, (0, GAME_AREA_TOP))
        else:
            if self._bg_surface is not None:
                self._bg_surface.set_alpha(255)
                self.screen.blit(self._bg_surface, (0, GAME_AREA_TOP))

        # 3. Overlay oscuro cacheado para legibilidad de los elementos
        self.screen.blit(self._bg_overlay, (0, GAME_AREA_TOP))

    # --------------------------------------------------------
    # Pantalla de juego
    # --------------------------------------------------------

    def draw_game(self, score: ScoreState, player: Paddle, computer: Paddle,
                  ball: Ball, narration_text: str,
                  question_active: bool = False, question_text: str = "",
                  current_answer: str = "Duda",
                  bullet_time_remaining: float = 0.0,
                  llm_enabled: bool = False,
                  colors: ThemeColors | None = None,
                  paused: bool = False,
                  achievement_popup: tuple[AchievementDef, float] | None = None,
                  rpg: RPGState | None = None,
                  extra_balls: list[Ball] | None = None) -> None:
        """
        Dibuja un frame completo de la pantalla de juego.

        Incluye: fondo negro, marcador, linea central, paletas,
        pelota, zona de narracion, y (opcionalmente) la interfaz de preguntas.

        Args:
            score:                 ScoreState con el marcador actual.
            player:                Paddle del jugador.
            computer:              Paddle del ordenador.
            ball:                  Ball (pelota).
            narration_text:        Texto de narracion actual.
            question_active:       True si hay una pregunta activa.
            question_text:         Texto de la pregunta del narrador.
            current_answer:        Respuesta seleccionada ("Si", "Duda", "No").
            bullet_time_remaining: Segundos restantes de bullet time.
            llm_enabled:           True si el LLM local esta activo y cargado.
            colors:                ThemeColors con los colores del frame actual.
        """
        if colors is None:
            colors = ThemeColors()

        # Fondo: imagen generada por IA o color solido
        if self._bg_surface is not None:
            self._draw_generated_background(colors)
        else:
            self.screen.fill(colors.background)

        self._draw_scores(score, colors)
        self._draw_center_line(colors)
        player.draw(self.screen, y_offset=GAME_AREA_TOP, color=colors.player_paddle)
        computer.draw(self.screen, y_offset=GAME_AREA_TOP, color=colors.computer_paddle)
        ball.draw(self.screen, y_offset=GAME_AREA_TOP, color=colors.ball)

        # Bolas extra (dual instinct)
        if extra_balls:
            for eb in extra_balls:
                eb.draw(self.screen, y_offset=GAME_AREA_TOP, color=colors.ball)

        # Prediccion de trayectoria (habilidad de ascension)
        if rpg is not None and rpg.has_trajectory_prediction():
            self.draw_trajectory_prediction(ball, colors, rpg.get_trajectory_distance())

        # Barra de XP RPG
        if rpg is not None:
            self.draw_xp_bar(rpg, colors)
        else:
            # Zona vacia con fondo de narracion
            narr_bg = colors.narration_bg if colors else (20, 20, 20)
            pygame.draw.rect(
                self.screen, narr_bg,
                (0, XP_BAR_TOP, WINDOW_WIDTH, XP_BAR_HEIGHT),
            )

        # Durante una pregunta activa, la zona de narracion inferior muestra
        # la pregunta en lugar del comentario normal del narrador.
        narration_display_text = (
            question_text if question_active and question_text else narration_text
        )
        self._draw_narration_area(
            narration_display_text, llm_enabled=llm_enabled, colors=colors
        )

        if question_active:
            self._draw_question_ui(current_answer, bullet_time_remaining, colors)

        if paused:
            self._draw_pause_overlay(colors)

        if achievement_popup is not None:
            self.draw_achievement_popup(*achievement_popup)

        pygame.display.flip()

    def _draw_pause_overlay(self, colors: ThemeColors) -> None:
        """Dibuja un overlay semi-transparente con el texto PAUSA centrado."""
        overlay = pygame.Surface((WINDOW_WIDTH, GAME_AREA_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 128))
        self.screen.blit(overlay, (0, GAME_AREA_TOP))

        text = self.font.render("PAUSA", True, colors.score_text)
        text_rect = text.get_rect(
            center=(WINDOW_WIDTH // 2, GAME_AREA_TOP + GAME_AREA_HEIGHT // 2)
        )
        self.screen.blit(text, text_rect)

    def _draw_center_line(self, colors: ThemeColors | None = None) -> None:
        """
        Dibuja la linea punteada central estilo Pong clasico.

        Es la linea vertical del medio de la cancha, hecha de
        pequenos rectangulos blancos separados por huecos.
        """
        if colors is None:
            colors = ThemeColors()
        x = WINDOW_WIDTH // 2 - CENTER_DASH_WIDTH // 2
        y = GAME_AREA_TOP
        game_area_bottom = GAME_AREA_TOP + GAME_AREA_HEIGHT
        while y < game_area_bottom:
            dash_rect = pygame.Rect(x, y, CENTER_DASH_WIDTH, CENTER_DASH_HEIGHT)
            pygame.draw.rect(self.screen, colors.center_line, dash_rect)
            y += CENTER_DASH_HEIGHT + CENTER_DASH_GAP

    def _draw_scores(self, score: ScoreState, colors: ThemeColors | None = None) -> None:
        """
        Dibuja la banda de marcador en la parte superior de la pantalla.

        Muestra sets, juegos y puntos en una sola linea centrada.

        Args:
            score:  ScoreState con el marcador actual.
            colors: ThemeColors con los colores del frame.
        """
        if colors is None:
            colors = ThemeColors()
        # Fondo de la banda de marcador
        score_band = pygame.Rect(0, 0, WINDOW_WIDTH, SCORE_BAND_HEIGHT)
        pygame.draw.rect(self.screen, colors.score_band_bg, score_band)

        # Linea divisoria inferior
        pygame.draw.line(
            self.screen,
            colors.divider,
            (0, SCORE_BAND_HEIGHT),
            (WINDOW_WIDTH, SCORE_BAND_HEIGHT),
            2,
        )

        # Texto del marcador
        score_line = score.display_score_line()
        score_text = self.score_details_font.render(
            score_line, True, colors.score_text
        )
        score_rect = score_text.get_rect(
            centerx=WINDOW_WIDTH // 2,
            centery=SCORE_BAND_HEIGHT // 2,
        )
        self.screen.blit(score_text, score_rect)

    def _draw_narration_area(self, narration_text: str, llm_enabled: bool = False, colors: ThemeColors | None = None) -> None:
        """
        Dibuja la zona de narracion con el comentario del narrador IA.

        El texto se parte en varias lineas si es demasiado largo para
        caber en una sola (word wrapping).

        Args:
            narration_text: String con el texto de narracion actual.
            llm_enabled:   Estado actual del LLM local.
            colors:        ThemeColors con los colores del frame.
        """
        if colors is None:
            colors = ThemeColors()
        # Fondo de la zona de narracion
        narration_rect = pygame.Rect(
            0, NARRATION_TOP, WINDOW_WIDTH, NARRATION_HEIGHT
        )
        pygame.draw.rect(self.screen, colors.narration_bg, narration_rect)

        # Linea divisoria superior
        pygame.draw.line(
            self.screen,
            colors.divider,
            (0, NARRATION_TOP),
            (WINDOW_WIDTH, NARRATION_TOP),
            2,
        )

        # Texto con word wrapping
        max_width = WINDOW_WIDTH - (NARRATION_MARGIN_X * 2)
        lines = self._wrap_text(narration_text, max_width)
        start_y = NARRATION_TOP + NARRATION_TEXT_OFFSET_Y

        for i, line in enumerate(lines[:NARRATION_MAX_VISIBLE_LINES]):
            line_text = self.narration_font.render(line, True, colors.narration_text)
            y = start_y + i * (NARRATION_FONT_SIZE + NARRATION_LINE_SPACING)
            self.screen.blit(line_text, (NARRATION_MARGIN_X, y))

        # Indicador de estado del LLM en la esquina inferior derecha.
        status_text = "LLM ON" if llm_enabled else "LLM off"
        status_surface = self.llm_status_font.render(
            status_text, True, COLOR_ANSWER_INACTIVE
        )
        status_rect = status_surface.get_rect(
            right=WINDOW_WIDTH - NARRATION_MARGIN_X,
            bottom=NARRATION_TOP + NARRATION_HEIGHT - 10,
        )
        self.screen.blit(status_surface, status_rect)

    # --------------------------------------------------------
    # Interfaz de preguntas (Si / Duda / No)
    # --------------------------------------------------------

    def _draw_question_ui(self, current_answer: str, countdown: float, colors: ThemeColors | None = None) -> None:
        """
        Dibuja la interfaz de pregunta: opciones Si/Duda/No y countdown.

        El texto de la pregunta se renderiza en la caja inferior de narracion,
        no en la parte superior del area de juego.

        Las tres opciones se posicionan verticalmente cerca de la paleta del
        jugador, ligeramente fuera del terreno de juego:
        - "Si" justo por encima del area de juego (en la banda de marcador).
        - "Duda" en el centro vertical del area de juego.
        - "No" justo por debajo del area de juego (en la zona de narracion).

        La opcion seleccionada (segun la posicion de la paleta) se muestra
        en el color activo del tema; las demas en gris.

        Args:
            current_answer: "Si", "Duda" o "No" — respuesta seleccionada.
            countdown:      Segundos restantes de bullet time.
            colors:         ThemeColors con los colores del frame.
        """
        if colors is None:
            colors = ThemeColors()
        # --- Opciones Si / Duda / No ---
        # "Si" ligeramente por encima del campo (en la banda de marcador)
        si_screen_y = GAME_AREA_TOP - 20
        # "Duda" en el centro vertical del area de juego
        duda_screen_y = GAME_AREA_TOP + GAME_AREA_HEIGHT // 2
        # "No" ligeramente por debajo del campo (en la zona de narracion)
        no_screen_y = NARRATION_TOP + 8

        options = [
            ("Si", si_screen_y, current_answer == "Si"),
            ("Duda", duda_screen_y, current_answer == "Duda"),
            ("No", no_screen_y, current_answer == "No"),
        ]

        for text, y_pos, is_active in options:
            color = colors.answer_active if is_active else colors.answer_inactive
            label = self.answer_font.render(text, True, color)
            label_rect = label.get_rect(x=ANSWER_LABEL_X, centery=y_pos)
            self.screen.blit(label, label_rect)

        # --- Cuenta regresiva centrada ---
        if countdown > 0:
            countdown_text = f"{countdown:.1f}"
            cd_surface = self.countdown_font.render(
                countdown_text, True, colors.countdown
            )
            cd_rect = cd_surface.get_rect(
                centerx=WINDOW_WIDTH // 2,
                centery=GAME_AREA_TOP + GAME_AREA_HEIGHT - 30,
            )
            self.screen.blit(cd_surface, cd_rect)

    # --------------------------------------------------------
    # Utilidades de texto
    # --------------------------------------------------------

    def _wrap_text(self, text: str, max_width: int, font: pygame.font.Font | None = None) -> list[str]:
        """
        Parte texto largo en varias lineas (word wrapping).

        Divide el texto por palabras y va acumulando en una linea hasta
        que la siguiente palabra no cabe. Entonces empieza una nueva linea.

        Args:
            text:      String a partir en lineas.
            max_width: Ancho maximo en pixeles.
            font:      Fuente para medir el ancho (default: narration_font).

        Returns:
            Lista de strings, cada uno una linea que cabe en max_width.
        """
        if font is None:
            font = self.narration_font
        words = text.split()
        if not words:
            return [""]

        lines = []
        current_line = words[0]
        for word in words[1:]:
            candidate = f"{current_line} {word}"
            if font.size(candidate)[0] <= max_width:
                current_line = candidate
            else:
                lines.append(current_line)
                current_line = word
        lines.append(current_line)
        return lines
