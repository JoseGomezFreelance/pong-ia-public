"""
pong/game.py -- Clase principal que orquesta el juego.

Este es el "director de orquesta" del juego. No hace las cosas el mismo,
sino que coordina a los demas modulos:
- entities.py → mueve paletas y pelota
- scoring.py  → lleva el marcador
- narration_bridge.py → pide narracion al narrador IA
- renderer.py → dibuja todo en pantalla
- sound.py    → reproduce efectos de sonido
- music.py    → sintetiza el tema MIDI con ondas cuadradas ZX Spectrum

El bucle principal (run) repite 60 veces por segundo:
  1. Leer teclado (handle_input)
  2. Actualizar logica (update)
  3. Dibujar pantalla (draw)
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import pygame

from pong.config.gameplay import (
    AGENT_MODE_SPEED_MULTIPLIER,
    EMOTION_LERP_FACTOR,
    FPS,
    GAME_POINTS_TO_WIN,
    MATCH_SETS_TO_WIN,
    PADDLE_HEIGHT,
    PADDLE_MARGIN,
    PADDLE_WIDTH,
    PLAYER_TRACK_WINDOW,
    SET_GAMES_TO_WIN,
)
from pong.config.layout import GAME_AREA_HEIGHT, WINDOW_HEIGHT, WINDOW_WIDTH
from pong.config.media import (
    IMAGEGEN_INTERVAL_SECONDS,
    IMAGEGEN_MATCH_ACTIVATE_SECONDS,
    MUSIC_REMIX_START,
    MUSIC_START_SECONDS,
)
from pong.config.ui_achievements import ACHIEVEMENT_POPUP_DURATION
from pong.config.ui_end_screen import SUMMARY_PROGRESS_LERP_FACTOR
from pong.config.version import APP_VERSION

from pong.achievements import AchievementEngine
from pong.emotional_state import EmotionalState
from pong.entities import Ball, Paddle
from pong.perf import PerformanceMetrics
from pong.game_ai import GameAIMixin
from pong.game_imagegen import GameImagegenMixin
from pong.game_persistence import GamePersistenceMixin
from pong.game_rpg import GameRPGMixin
from pong.game_state import MatchState, UIState, create_subsystems
from pong.question_system import QuestionSystem
from pong.renderer import Renderer
from pong.save_manager import (
    _write_history,
    compute_derived_stats,
    get_player_profile,
    load_history,
    open_saves_folder,
)
from pong.scoring import apply_point
from pong.splash import ZXTerminal, ZXTitleScreen
from pong.theme import ThemeManager

from pong.protocols import (
    MusicEngineProtocol,
    NarrationBridgeProtocol,
    SoundManagerProtocol,
)

if TYPE_CHECKING:
    from pong.harness import HeadlessConfig
    from pong.image_generator import ImageGenerator


class Game(GameAIMixin, GameRPGMixin, GamePersistenceMixin, GameImagegenMixin):
    """
    Clase principal que controla todo el juego.

    Crea la ventana, las entidades, el marcador, el narrador y el renderer.
    Luego ejecuta el bucle principal donde se procesan inputs, se actualiza
    la logica y se dibuja cada frame.

    Para entender el flujo del juego, empieza leyendo el metodo run().
    """

    def __init__(self, headless_config: HeadlessConfig | None = None) -> None:
        """
        Inicializa pygame y todos los componentes del juego.

        Args:
            headless_config: Si se pasa un HeadlessConfig, el juego arranca
                en modo headless (sin ventana, sin audio, subsistemas
                opcionales desactivados). Usado por GameHarness para testing.
        """
        self._headless: HeadlessConfig | None = headless_config
        _hl = self._headless

        # --- Pygame ---
        pygame.init()
        self.screen: pygame.Surface = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption(f"Pong \u2014 {APP_VERSION}")
        # Icono de la ventana
        try:
            from pathlib import Path as _P
            _img_dir = _P(__file__).resolve().parent.parent / "assets" / "images"
            for _ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
                _icon = _img_dir / f"icon{_ext}"
                if _icon.exists():
                    pygame.display.set_icon(pygame.image.load(str(_icon)))
                    break
        except Exception:
            pass
        self.clock: pygame.time.Clock = pygame.time.Clock()

        # --- Estado agrupado ---
        self.running: bool = True
        self.paused: bool = False
        self.agent_mode: bool = False
        self._speed_mult: float = 1.0
        self.match: MatchState = MatchState()
        self.ui: UIState = UIState()
        self.perf: PerformanceMetrics = PerformanceMetrics()
        self.game_start_time: float = time.monotonic()
        self.game_end_time: float | None = None
        self.match_summary_text: str | None = None
        self.match_summary_requested: bool = False
        self.match_summary_start_time: float | None = None
        self._displayed_summary_progress: float = 0.0
        self._cached_stats_data: dict[str, Any] | None = None
        self._player_profile: dict[str, str] = get_player_profile(load_history())
        self._leaderboard_entries: dict[str, list[Any]] = {}
        self._peer_network: Any = None  # PeerNetwork | None (lazy import)
        self._leaderboard_last_refresh: float = 0
        self._p2p_last_backup_digest: str = ""
        self.terminal_log_lines: list[str] = []

        # --- Entidades ---
        player_x = PADDLE_MARGIN
        computer_x = WINDOW_WIDTH - PADDLE_MARGIN - PADDLE_WIDTH
        center_y = GAME_AREA_HEIGHT // 2 - PADDLE_HEIGHT // 2
        self.player: Paddle = Paddle(player_x, center_y)
        self.computer: Paddle = Paddle(computer_x, center_y)
        self.computer_home_x: int = computer_x
        self.ball: Ball = Ball()

        # --- Estado emocional de la IA ---
        self.emotional_state: EmotionalState = EmotionalState()
        self.emotional_target: EmotionalState = EmotionalState()
        self.emotion_active: bool = False

        # --- Tracking de actividad del jugador ---
        self._player_positions: list[int] = []
        self._player_sample_counter: int = 0
        self._player_idle_score: float = 0.0

        # --- Renderer y tema ---
        self.renderer: Renderer = Renderer(self.screen)
        self.theme: ThemeManager = ThemeManager()

        # --- Terminal de carga (si no es headless) ---
        if _hl is None or not _hl.skip_splash:
            terminal = ZXTerminal(self.screen)
            terminal.play_boot_beep()
        else:
            terminal = None

        # --- Fase visual generativa ---
        self._init_imagegen_phase(terminal)

        total_steps = (9 if self.imagegen_unlocked else 8) if terminal else 0

        if terminal:
            terminal.add_line("Inicializando motor de juego...")
            terminal.render(0, total_steps)
            terminal.update_last_line("Motor de juego inicializado")
            terminal.add_line("Entidades y marcador listos")
            terminal.render(1, total_steps)

        # --- Subsistemas (sonido, musica, narracion) ---
        _step = [2]  # mutable para el closure

        def _progress(msg: str) -> None:
            if terminal:
                terminal.add_line(msg) if _step[0] in (2, 3, 5) else terminal.update_last_line(msg)
                terminal.render(_step[0], total_steps)
                _step[0] += 1

        self.sounds: SoundManagerProtocol
        self.music: MusicEngineProtocol
        self.narration: NarrationBridgeProtocol
        self.sounds, self.music, self.narration = create_subsystems(
            _hl, self.perf, self._log,
            progress_fn=_progress if terminal else None,
        )

        # --- Descarga del modelo de difusion (si desbloqueado) ---
        if (_hl is None or _hl.enable_imagegen) and self.imagegen_unlocked:
            from pong.image_generator import is_model_cached, ensure_models_downloaded

            _next_step = 7
            if not is_model_cached():
                if terminal:
                    terminal.add_line("Descargando modelo de difusion...")
                    terminal.render(_next_step, total_steps)

                def _dl_progress(msg: str) -> None:
                    if terminal:
                        terminal.update_last_line(msg)
                        terminal.render(_next_step, total_steps)

                ensure_models_downloaded(progress_callback=_dl_progress)
            else:
                if terminal:
                    terminal.add_line("Modelo de difusion: en cache")
                    terminal.render(_next_step, total_steps)

        # --- Preparar partida (preguntas, logros, narracion inicial) ---
        if terminal:
            terminal.add_line("Preparando partida...")
            terminal.render(7 if not self.imagegen_unlocked else 8, total_steps)

        self._prepare_match()

        if terminal:
            terminal.add_line(
                f"Formato: {GAME_POINTS_TO_WIN} pts/juego, "
                f"{SET_GAMES_TO_WIN} juegos/set, "
                f"{MATCH_SETS_TO_WIN} sets/partido"
            )
            terminal.add_line("Listo!")
            terminal.render(total_steps, total_steps)
            pygame.time.wait(600)

        # --- Portada pixel art ZX Spectrum ---
        if _hl is None or not _hl.skip_splash:
            # Aviso one-time sobre integridad del guardado
            _pre_history = load_history()
            _show_notice = not _pre_history.get("_integrity_notice_shown", False)
            if _show_notice:
                _pre_history["_integrity_notice_shown"] = True
                _write_history(_pre_history)

            title_screen = ZXTitleScreen(
                self.screen, show_integrity_notice=_show_notice,
            )
            title_screen.build()
            while True:
                choice = title_screen.display()
                if choice == "play":
                    break
                if choice == "play_agent":
                    self.agent_mode = True
                    break
                if choice == "install":
                    from pong.splash import ZXDownloadScreen

                    download_screen = ZXDownloadScreen(self.screen)
                    download_screen.run()
                    self.narration.narrator.reload_llm()

        # Resetear el reloj del partido: el tiempo empieza al pulsar JUGAR
        self.game_start_time = time.monotonic()
        self.questions.reset_timers(self.game_start_time)

        # --- Logs de inicializacion ---
        self._emit_init_logs()

    # --------------------------------------------------------
    # Preparacion de partida
    # --------------------------------------------------------

    def _prepare_match(self) -> None:
        """
        Prepara sistemas de preguntas, logros y narracion inicial.

        Se usa tanto en __init__ como indirectamente desde _restart_match().
        """
        self.questions: QuestionSystem = QuestionSystem(self.game_start_time)
        self.narration.request_reformulation(
            self.questions.selected_initial_question
        )

        history: dict[str, Any] = load_history()
        self.records: dict[str, Any] = history.get("records", {})
        self.new_records: list[str] = []
        self.game_saved: bool = False

        self.achievements: AchievementEngine = AchievementEngine()
        self.achievements.load_from_history(history)
        self.achievements.start_match()

        # --- RPG ---
        self._init_rpg()

        game_state = self.narration.build_game_state(
            "inicio", self.match.score, self.ball, self.match.rally_hits,
            self.match.last_play, 0.0,
        )
        self.narration.request("inicio", game_state, priority=True)

    # --------------------------------------------------------
    # Logging
    # --------------------------------------------------------

    def _emit_terminal_line(self, message: str = "") -> None:
        """
        Escribe una linea en terminal y la guarda para exportacion.

        Args:
            message: Texto a imprimir (linea vacia si no se pasa nada).
        """
        line = str(message)
        self.terminal_log_lines.append(line)
        print(line)

    def _emit_init_logs(self) -> None:
        """Emite los logs de cabecera tras inicializar todos los sistemas."""
        self._emit_terminal_line("=" * 60)
        self._emit_terminal_line(f"PONG \u2014 {APP_VERSION} \u2014 Log de depuracion")
        self._emit_terminal_line("=" * 60)
        self._emit_terminal_line(f"Narrador: {self.narration.narrator.status_message}")
        self._emit_terminal_line(
            f"Musica: {'tema cargado' if self.music.loaded else 'no disponible'}"
        )
        self._emit_terminal_line(
            f"Formato: {GAME_POINTS_TO_WIN} pts/juego, "
            f"{SET_GAMES_TO_WIN} juegos/set, "
            f"{MATCH_SETS_TO_WIN} sets/partido"
        )
        self._emit_terminal_line("-" * 60)

    def _log(self, category: str, message: str) -> None:
        """
        Imprime un mensaje de log por terminal con timestamp relativo.

        Args:
            category: Tipo de evento (PUNTO, JUEGO, SET, RALLY, LLM...).
            message:  Texto del mensaje.
        """
        elapsed = time.monotonic() - self.game_start_time
        stamp = self._format_elapsed(elapsed)
        self._emit_terminal_line(f"[{stamp}] [{category:<8s}] {message}")

    @staticmethod
    def _format_elapsed(total_seconds: float) -> str:
        """
        Convierte segundos a formato mm:ss para logs.

        Args:
            total_seconds: Tiempo en segundos.

        Returns:
            String en formato "02:35".
        """
        seconds = max(0, int(total_seconds))
        minutes = seconds // 60
        remaining = seconds % 60
        return f"{minutes:02d}:{remaining:02d}"

    # --------------------------------------------------------
    # Entrada del teclado
    # --------------------------------------------------------

    def handle_input(self) -> None:
        """
        Procesa la entrada del teclado y eventos del sistema.

        Controles:
        - Flechas arriba/abajo: mover la paleta del jugador.
        - ESC: mostrar pantalla de depuracion (o salir si ya esta visible).
        - En pantalla final: flechas arriba/abajo para scroll.
        - En pantalla final: click en "copiar" para copiar logs al portapapeles.
        - En pantalla final: click en "Jugar otra vez" para reiniciar partido.
        """
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_p and not self.ui.showing_end_screen:
                    self.paused = not self.paused
                if event.key == pygame.K_ESCAPE:
                    if not self.ui.showing_end_screen:
                        self.ui.showing_end_screen = True
                        self.game_end_time = time.monotonic()
                        self.music.stop()
                        self._print_end_summary()
                        self._request_match_summary()
                    elif self.ui.showing_alias_prompt:
                        self.ui.showing_alias_prompt = False
                    elif self.ui.showing_p2p_connecting:
                        self.ui.showing_p2p_connecting = False
                    elif self.ui.showing_leaderboard_screen:
                        self.ui.showing_leaderboard_screen = False
                        self.ui.leaderboard_screen_scroll = 0
                    elif self.ui.showing_skills_screen:
                        self.ui.showing_skills_screen = False
                        self.ui.skills_screen_scroll = 0
                    elif self.ui.showing_ascension_screen:
                        # No se puede salir con ESC: la ascension es irreversible
                        pass
                    elif self.ui.showing_ascension_confirm:
                        self.ui.showing_ascension_confirm = False
                    elif self.ui.showing_achievements_screen:
                        self.ui.showing_achievements_screen = False
                        self.ui.achievements_screen_scroll = 0
                    elif self.ui.showing_debug_screen:
                        self.ui.showing_debug_screen = False
                        self.ui.debug_screen_scroll = 0
                    else:
                        self.running = False
                # Entrada de texto para alias prompt
                if self.ui.showing_alias_prompt:
                    from pong.config.ui_leaderboard import ALIAS_MAX_LENGTH
                    if event.key == pygame.K_BACKSPACE:
                        self.ui.alias_input_text = self.ui.alias_input_text[:-1]
                    elif event.key == pygame.K_RETURN:
                        if self.ui.alias_input_text.strip():
                            from pong.save_manager import set_player_alias
                            self._player_profile = set_player_alias(
                                self.ui.alias_input_text.strip(),
                            )
                            self.ui.showing_alias_prompt = False
                            self._enter_p2p_connecting()
                    elif event.unicode and len(self.ui.alias_input_text) < ALIAS_MAX_LENGTH:
                        ch = event.unicode
                        if ch.isprintable() and ch not in ('\t', '\n', '\r'):
                            self.ui.alias_input_text += ch

                if self.ui.showing_end_screen and event.key == pygame.K_UP:
                    if self.ui.showing_leaderboard_screen:
                        self.ui.leaderboard_screen_scroll = max(
                            0, self.ui.leaderboard_screen_scroll - 1,
                        )
                    elif self.ui.showing_skills_screen:
                        self.ui.skills_screen_scroll = max(
                            0, self.ui.skills_screen_scroll - 30,
                        )
                    elif self.ui.showing_ascension_screen:
                        self.ui.ascension_screen_scroll = max(
                            0, self.ui.ascension_screen_scroll - 30,
                        )
                    elif self.ui.showing_achievements_screen:
                        self.ui.achievements_screen_scroll = max(
                            0, self.ui.achievements_screen_scroll - 1,
                        )
                    elif self.ui.showing_debug_screen:
                        self.ui.debug_screen_scroll = max(
                            0, self.ui.debug_screen_scroll - 1,
                        )
                if self.ui.showing_end_screen and event.key == pygame.K_DOWN:
                    if self.ui.showing_leaderboard_screen:
                        self.ui.leaderboard_screen_scroll += 1
                    elif self.ui.showing_skills_screen:
                        self.ui.skills_screen_scroll += 30
                    elif self.ui.showing_ascension_screen:
                        self.ui.ascension_screen_scroll += 30
                    elif self.ui.showing_achievements_screen:
                        self.ui.achievements_screen_scroll += 1
                    elif self.ui.showing_debug_screen:
                        self.ui.debug_screen_scroll += 1
            if (
                self.ui.showing_end_screen
                and event.type == pygame.MOUSEBUTTONDOWN
                and event.button == 1
            ):
                if self.ui.showing_alias_prompt:
                    # Click en prompt de alias
                    if (self.renderer.alias_accept_button_rect
                            and self.renderer.alias_accept_button_rect.collidepoint(event.pos)
                            and self.ui.alias_input_text.strip()):
                        from pong.save_manager import set_player_alias
                        self._player_profile = set_player_alias(
                            self.ui.alias_input_text.strip(),
                        )
                        self.ui.showing_alias_prompt = False
                        self._enter_p2p_connecting()
                elif self.ui.showing_p2p_connecting:
                    # Click en boton "Continuar" de pantalla P2P
                    self._handle_p2p_continue_click(event.pos)
                elif self.ui.showing_leaderboard_screen:
                    # Click en pantalla de rankings
                    if (self.renderer.ranking_back_button_rect
                            and self.renderer.ranking_back_button_rect.collidepoint(event.pos)):
                        self.ui.showing_leaderboard_screen = False
                        self.ui.leaderboard_screen_scroll = 0
                    else:
                        for i, tab_rect in enumerate(self.renderer.ranking_tab_rects):
                            if tab_rect.collidepoint(event.pos):
                                self.ui.leaderboard_active_tab = i
                                self.ui.leaderboard_screen_scroll = 0
                                break
                elif self.ui.showing_skills_screen:
                    # Click en pantalla de habilidades
                    if (self.renderer.skills_back_button_rect
                            and self.renderer.skills_back_button_rect.collidepoint(event.pos)):
                        self.ui.showing_skills_screen = False
                        self.ui.skills_screen_scroll = 0
                    else:
                        # Comprobar click en botones de compra
                        for skill_id, buy_rect in self.renderer.skill_buy_rects:
                            if buy_rect.collidepoint(event.pos):
                                if self.rpg.buy_skill(skill_id):
                                    self._log("RPG", f"Habilidad comprada: {skill_id}")
                                    self._rpg_apply_modifiers()
                                    self._rpg_persist_now()
                                break
                elif self.ui.showing_ascension_screen:
                    # Click en pantalla de ascension (sin boton volver)
                    if (self.renderer.ascension_confirm_button_rect
                          and self.renderer.ascension_confirm_button_rect.collidepoint(event.pos)
                          and self.rpg.can_ascend()):
                        self.rpg.perform_ascension()
                        self._rpg_apply_modifiers()
                        self._log("RPG", f"Ascension completada! Ascension #{self.rpg.ascension_count}")
                        self._rpg_persist_now()
                        self.ui.showing_ascension_screen = False
                        self.ui.ascension_screen_scroll = 0
                        # Mostrar pantalla de titulo para subrayar el peso
                        # de la ascension (el jugador debe pulsar "Jugar")
                        title_screen = ZXTitleScreen(self.screen)
                        title_screen.build()
                        while True:
                            choice = title_screen.display()
                            if choice == "play":
                                break
                            if choice == "play_agent":
                                self.agent_mode = True
                                break
                            if choice == "install":
                                from pong.splash import ZXDownloadScreen
                                download_screen = ZXDownloadScreen(self.screen)
                                download_screen.run()
                                self.narration.narrator.reload_llm()
                        self._restart_match()
                    else:
                        # Comprobar click en botones de compra de ascension
                        for skill_id, buy_rect in self.renderer.ascension_buy_rects:
                            if buy_rect.collidepoint(event.pos):
                                if self.rpg.buy_ascension_skill(skill_id):
                                    self._log("RPG", f"Habilidad de ascension comprada: {skill_id}")
                                    self._rpg_apply_modifiers()
                                    self._rpg_persist_now()
                                break
                elif self.ui.showing_ascension_confirm:
                    # Click en dialogo de confirmacion de ascension
                    # (bloquea todos los clicks del end screen)
                    if (self.renderer.ascension_dialog_accept_rect
                            and self.renderer.ascension_dialog_accept_rect.collidepoint(event.pos)):
                        self.ui.showing_ascension_confirm = False
                        self.ui.showing_ascension_screen = True
                        self.ui.ascension_screen_scroll = 0
                    elif (self.renderer.ascension_dialog_cancel_rect
                          and self.renderer.ascension_dialog_cancel_rect.collidepoint(event.pos)):
                        self.ui.showing_ascension_confirm = False
                    # else: click fuera del dialogo → ignorar
                elif self.ui.showing_achievements_screen:
                    if self.renderer.achievements_back_button_rect.collidepoint(
                        event.pos,
                    ):
                        self.ui.showing_achievements_screen = False
                        self.ui.achievements_screen_scroll = 0
                elif self.ui.showing_debug_screen:
                    if self.renderer.debug_back_button_rect.collidepoint(
                        event.pos,
                    ):
                        self.ui.showing_debug_screen = False
                        self.ui.debug_screen_scroll = 0
                elif self.renderer.copy_button_rect.collidepoint(event.pos):
                    self._copy_terminal_logs()
                elif self.renderer.restart_button_rect.collidepoint(event.pos):
                    self._restart_match()
                elif self.renderer.export_button_rect.collidepoint(event.pos):
                    open_saves_folder()
                elif (self.renderer.logros_button_rect
                      and self.renderer.logros_button_rect.collidepoint(
                          event.pos)):
                    self.ui.showing_achievements_screen = True
                    self.ui.achievements_screen_scroll = 0
                    self._cached_stats_data = compute_derived_stats(
                        load_history(),
                    )
                elif (self.renderer.ranking_button_rect
                      and self.renderer.ranking_button_rect.collidepoint(
                          event.pos)):
                    if self._player_profile.get("alias"):
                        self._enter_p2p_connecting()
                    else:
                        self.ui.showing_alias_prompt = True
                        self.ui.alias_input_text = ""
                elif (self.renderer.skills_button_rect
                      and self.renderer.skills_button_rect.collidepoint(
                          event.pos)):
                    self.ui.showing_skills_screen = True
                    self.ui.skills_screen_scroll = 0
                elif (self.renderer.ascension_button_rect
                      and self.renderer.ascension_button_rect.collidepoint(
                          event.pos)):
                    self.ui.showing_ascension_confirm = True
                elif (self.renderer.debug_button_rect
                      and self.renderer.debug_button_rect.collidepoint(
                          event.pos)):
                    self.ui.showing_debug_screen = True
                    self.ui.debug_screen_scroll = 0

        # Movimiento continuo con teclas mantenidas
        if self.ui.showing_end_screen:
            return
        keys = pygame.key.get_pressed()
        if keys[pygame.K_UP]:
            self.player.move_up(self._speed_mult)
        if keys[pygame.K_DOWN]:
            self.player.move_down(self._speed_mult)

    # --------------------------------------------------------
    # Logica principal (update)
    # --------------------------------------------------------

    def update(self) -> None:
        """
        Actualiza toda la logica del juego en cada frame.

        Orden:
        1. Recoger narraciones y preguntas pendientes del hilo de fondo.
        2. Comprobar si es momento de hacer una pregunta.
        3. Actualizar bullet time y respuesta del jugador.
        4. Mover pelota y paleta de la IA (con multiplicador de velocidad).
        5. Detectar colisiones.
        6. Comprobar si alguien anoto.
        7. Pedir narracion periodica si toca.
        """
        # --- Recoger narracion pendiente ---
        if self.narration.has_pending():
            self.narration.consume_pending()

        # --- Recoger pregunta pendiente del LLM ---
        pending_q = self.narration.consume_pending_question()
        if pending_q is not None:
            self.questions.set_pending_question(pending_q)
            if not self.questions.first_question_ready:
                self.questions.first_question_ready = True
                self._log("PREGUNTA", f"Primera pregunta lista: \"{pending_q}\"")

        # --- Recoger perfil emocional pendiente ---
        pending_emotion = self.narration.consume_pending_emotion()
        if pending_emotion is not None:
            self.emotional_target = pending_emotion
            if not self.emotion_active:
                self.emotion_active = True
                self._log("EMOCION", "Sistema emocional activado")

        # --- Recoger resumen de partido pendiente ---
        if self.ui.showing_end_screen and self.match_summary_text is None:
            pending_summary = self.narration.consume_pending_summary()
            if pending_summary is not None:
                clean_summary = pending_summary.strip().strip("«»\"'`")
                if not clean_summary:
                    clean_summary = "(sin resumen disponible)"
                self.match_summary_text = clean_summary
                self._log(
                    "RESUMEN",
                    f"Resumen final: «{clean_summary}»",
                )
                self._save_game()

        if (
            self.ui.copy_status_text
            and time.monotonic() >= self.ui.copy_status_expires_at
        ):
            self.ui.copy_status_text = ""

        # --- Actualizar tema de colores (antes del early return para que
        #     la pantalla final tambien tenga colores emocionales) ---
        elapsed = time.monotonic() - self.game_start_time
        is_bt = self.questions.is_bullet_time()
        self.theme.update(
            elapsed_time=elapsed,
            emotional_state=self.emotional_state,
            emotion_active=self.emotion_active,
            is_bullet_time=is_bt,
        )

        # --- Actualizar musica (tema MIDI sintetizado) ---
        if elapsed >= MUSIC_START_SECONDS and not self.music.playing:
            self.music.start()
            self.sounds.set_music_mode(True)
            self._log("MUSICA", "Tema principal iniciado")
        if self.music.playing:
            self.music.set_bullet_time(is_bt)
            remix_active = elapsed >= MUSIC_REMIX_START
            self.music.update(
                dt=1.0 / FPS,
                emotional_state=self.emotional_state if remix_active else None,
                emotion_active=remix_active,
                is_bullet_time=is_bt,
            )

        # --- Fase visual generativa (fondo con IA de imagen) ---
        if (
            self.imagegen_unlocked
            and elapsed >= IMAGEGEN_MATCH_ACTIVATE_SECONDS
            and not self.ui.showing_end_screen
        ):
            if not self.imagegen_active:
                self._activate_imagegen()

            if self.imagegen_active and self._imagegen is not None:
                # Consumir prompt enriquecido por el LLM y enviarlo a SD
                enriched = self.narration.consume_pending_image_prompt()
                if enriched is not None:
                    enriched_prompt, negative = enriched
                    self._imagegen.request(enriched_prompt, negative)
                    self._log(
                        "IMAGEGEN",
                        f"Prompt enriquecido enviado a SD: "
                        f"{enriched_prompt[:60]}...",
                    )

                # Consumir imagen generada si hay alguna nueva
                new_surface = self._imagegen.consume()
                if new_surface is not None:
                    self._log(
                        "IMAGEGEN",
                        f"Surface recibida: {new_surface.get_size()}, "
                        f"bg_surface antes: {self.renderer._bg_surface is not None}",
                    )
                    self.renderer.set_background_image(new_surface)

                # Actualizar transicion de crossfade
                self.renderer.update_background_transition(1.0 / FPS)

                # Solicitar nueva imagen cada IMAGEGEN_INTERVAL_SECONDS
                now_ig = time.monotonic()
                if now_ig - self._last_imagegen_time >= IMAGEGEN_INTERVAL_SECONDS:
                    self._request_background_image()
                    self._last_imagegen_time = now_ig

        # --- Gestionar timer de notificacion de logros ---
        if self.achievements.has_notifications():
            if self.achievements.get_notification_start() is None:
                self.achievements.set_notification_start(time.monotonic())
            elif (
                (start_time := self.achievements.get_notification_start()) is not None
                and time.monotonic() - start_time > ACHIEVEMENT_POPUP_DURATION
            ):
                self.achievements.advance_notification()

        if self.ui.showing_end_screen or self.paused:
            return

        # --- RPG: acumular XP por tiempo de juego ---
        self._rpg_update(1.0 / FPS)

        # --- Muestrear posicion del jugador (4 Hz) ---
        self._player_sample_counter += 1
        if self._player_sample_counter >= 15:
            self._player_sample_counter = 0
            self._player_positions.append(self.player.rect.centery)
            if len(self._player_positions) > PLAYER_TRACK_WINDOW:
                self._player_positions.pop(0)

        # --- Comprobar si toca hacer una pregunta ---
        now = time.monotonic()
        if self.questions.should_ask_question(now):
            question = self.questions.pending_question
            if question is not None:
                self.questions.start_question(question, now)
                self._log("PREGUNTA", f"Pregunta activada: \"{question}\"")

        # --- Actualizar bullet time y respuesta ---
        dt_real = 1.0 / FPS
        was_active = self.questions.question_active
        self.questions.update(dt_real, self.player.rect.top)

        # Si la pregunta se acaba de cerrar (bullet time termino)
        if was_active and not self.questions.question_active:
            last_entry = self.questions.dialogue_history[-1]
            self._log(
                "RESPUESTA",
                f"Jugador respondio: {last_entry.answer} "
                f"a \"{last_entry.question}\"",
            )
            # Solicitar la siguiente pregunta al LLM
            self._request_next_question()

        # --- Obtener multiplicador de velocidad ---
        speed_mult = self.questions.get_speed_multiplier()
        if self.agent_mode:
            speed_mult = min(speed_mult, AGENT_MODE_SPEED_MULTIPLIER)
        self._speed_mult = speed_mult

        # --- Interpolar estado emocional suavemente ---
        if self.emotion_active:
            self.emotional_state.lerp_toward(
                self.emotional_target, EMOTION_LERP_FACTOR
            )
            # Registrar mood observado para logros emocionales
            self.achievements.record_mood(self.emotional_state.mood_tag)
            # Comprobar logros de mood inmediatamente tras cada cambio
            self._notify_achievements(
                self.achievements.check_mood(self.emotional_state.mood_tag)
            )

        # --- Ajuste autonomo ante inactividad / exploit ---
        self._apply_autonomous_emotion()

        # --- Mover pelota y paleta de la IA (con multiplicador) ---
        self.ball.update(speed_mult)
        self.update_ai(speed_mult)

        # --- Detectar colisiones con paletas ---
        player_collision = self.ball.check_paddle_collision(self.player)
        computer_collision = self.ball.check_paddle_collision(self.computer)

        if player_collision or computer_collision:
            self.sounds.play_paddle_hit()
            self.match.rally_hits += 1
            if self.match.rally_hits > self.match.max_rally_hits:
                self.match.max_rally_hits = self.match.rally_hits
            self.ball.sync_rally_speed(self.match.rally_hits)
            if player_collision:
                self.match.last_play = "El jugador devolvió la pelota"
                self._log("RALLY", f"Jugador devolvio (#{self.match.rally_hits} en rally)")
                self._rpg_on_player_collision()
            else:
                self.match.last_play = "El ordenador devolvió la pelota"
                self._log("RALLY", f"Ordenador devolvio (#{self.match.rally_hits} en rally)")
            # Comprobar logros de rally inmediatamente tras cada golpe
            self._notify_achievements(
                self.achievements.check_rally(self.match.rally_hits, self.match.max_rally_hits)
            )

        # --- Comprobar si alguien anoto ---
        point_scored = False

        if self.ball.rect.left <= 0:
            # La pelota salio por la izquierda: punto para el ordenador
            point_scored = True
            self._handle_point("computer")
            self.ball.reset()
            self.match.rally_hits = 0
            self.computer.rect.x = self.computer_home_x
        elif self.ball.rect.right >= WINDOW_WIDTH:
            # La pelota salio por la derecha: punto para el jugador
            point_scored = True
            self._handle_point("player")
            self.ball.reset()
            self.match.rally_hits = 0
            self.computer.rect.x = self.computer_home_x

        if self.ui.showing_end_screen:
            return

        # --- Pedir narracion periodica durante rallies ---
        if not point_scored and self.narration.should_request_periodic():
            elapsed = time.monotonic() - self.game_start_time
            game_state = self.narration.build_game_state(
                "juego en curso", self.match.score, self.ball, self.match.rally_hits,
                self.match.last_play, elapsed,
            )
            game_state["dialogue_essence"] = self.questions.get_dialogue_essence()
            self.narration.request("juego en curso", game_state)

    def _notify_achievements(self, new_ids: list[str]) -> None:
        """Reproduce sonido y log para logros recien desbloqueados."""
        if new_ids:
            self.sounds.play_achievement()
            for aid in new_ids:
                self._log(
                    "LOGRO",
                    f"Desbloqueado: {self.achievements.definitions[aid].name}",
                )

    def _handle_point(self, winner: str) -> None:
        """
        Procesa un punto: actualiza marcador, logs, timeline y narracion.

        Llama a apply_point() del modulo scoring para actualizar el marcador,
        y luego registra el evento en logs y timeline.

        Args:
            winner: "player" o "computer".
        """
        elapsed = time.monotonic() - self.game_start_time

        # Snapshot para deteccion de juego perfecto (apply_point resetea puntos)
        pre_player_pts = self.match.score.player_points
        pre_computer_pts = self.match.score.computer_points

        # Track si el computer lidera en juegos del set (para logro de remontada)
        if self.match.score.computer_games > self.match.score.player_games:
            self.achievements._computer_led_in_set = True

        # Aplicar el punto al marcador
        result = apply_point(self.match.score, winner)
        self.match.last_play = result.last_play

        # Registrar en timeline
        self.match.score_timeline.append(
            {
                "elapsed_seconds": elapsed,
                "description": result.last_play,
                "scoreboard": self.match.score.scoreboard_text(),
            }
        )

        # Log por terminal
        streak_info = (
            f" (racha {result.scoring_streak})"
            if result.scoring_streak >= 2
            else ""
        )
        self._log(
            "PUNTO",
            f"{result.last_play}{streak_info} -> {self.match.score.scoreboard_text()}",
        )

        if result.game_won:
            self._log("JUEGO", f"{result.last_play} -> {self.match.score.scoreboard_text()}")
        if result.set_won:
            self._log("SET", f"{result.last_play} -> {self.match.score.scoreboard_text()}")
        if result.match_won:
            self._log("PARTIDO", f"{result.last_play}!")
            self.ui.showing_end_screen = True
            self.game_end_time = time.monotonic()
            self.music.stop()
            self._shutdown_imagegen()
            self._print_end_summary()
            self._request_match_summary()

        # --- RPG: hook de punto anotado ---
        self._rpg_on_point_scored(winner)

        # --- Comprobar logros en tiempo real ---
        achievement_context = {
            "rally_hits": self.match.rally_hits,
            "max_rally_hits": self.match.max_rally_hits,
            "score": self.match.score,
            "point_result": result,
            "pre_player_pts": pre_player_pts,
            "pre_computer_pts": pre_computer_pts,
            "mood_tag": self.emotional_state.mood_tag,
            "elapsed_seconds": elapsed,
            "dialogue_history": self.questions.dialogue_history,
            "winner": winner,
        }
        self._notify_achievements(
            self.achievements.check_realtime(achievement_context)
        )

        # Solicitar narracion con datos del evento
        event_data = {
            "scoring_player": result.scorer_id,
            "point_won": result.point_won,
            "game_won": result.game_won,
            "set_won": result.set_won,
            "match_won": result.match_won,
            "scoring_streak": result.scoring_streak,
        }
        game_state = self.narration.build_game_state(
            result.event_label, self.match.score, self.ball, self.match.rally_hits,
            self.match.last_play, elapsed, event_data=event_data,
        )
        game_state["dialogue_essence"] = self.questions.get_dialogue_essence()
        self.narration.request(result.event_label, game_state, priority=True)

    # --------------------------------------------------------
    # Sistema de preguntas
    # --------------------------------------------------------

    def _request_next_question(self) -> None:
        """
        Solicita al LLM que genere la siguiente pregunta basada en el dialogo.

        Construye el contexto del dialogo y el estado del juego, y encola
        la peticion en el hilo de fondo del NarrationBridge.
        """
        elapsed = time.monotonic() - self.game_start_time
        dialogue_summary = self.questions.get_dialogue_summary()
        game_state = self.narration.build_game_state(
            "juego en curso", self.match.score, self.ball, self.match.rally_hits,
            self.match.last_play, elapsed,
        )
        game_state["dialogue_turns"] = self.questions.get_recent_dialogue_context()
        game_state["question_count"] = len(self.questions.dialogue_history)
        self.narration.request_new_question(dialogue_summary, game_state)

    # --------------------------------------------------------
    # Dibujado
    # --------------------------------------------------------

    def draw(self) -> None:
        """Dibuja el frame actual (juego normal o pantalla de depuracion)."""
        if self.ui.showing_end_screen:
            if self.ui.showing_alias_prompt:
                self.renderer.draw_alias_prompt(
                    current_text=self.ui.alias_input_text,
                    mouse_pos=pygame.mouse.get_pos(),
                )
            elif self.ui.showing_p2p_connecting:
                elapsed = time.monotonic() - self.ui.p2p_connect_start_time
                telemetry = {}
                if self._peer_network is not None:
                    telemetry = self._peer_network.get_telemetry()
                    # Auto-avanzar si se encontraron peers y paso el minimo
                    from pong.config.ui_leaderboard import P2P_CONNECT_MIN_SECONDS
                    if (telemetry.get("active_peers", 0) > 0
                            and elapsed >= P2P_CONNECT_MIN_SECONDS):
                        self._exit_p2p_connecting()
                self.renderer.draw_p2p_connecting(
                    elapsed=elapsed,
                    telemetry=telemetry,
                    mouse_pos=pygame.mouse.get_pos(),
                )
            elif self.ui.showing_leaderboard_screen:
                peer_count = 0
                network_active = False
                p2p_degraded = False
                if self._peer_network is not None:
                    peer_count = self._peer_network.get_peer_count()
                    network_active = True
                    p2p_degraded = getattr(
                        self._peer_network, "_p2p_degraded", False,
                    )
                # Refresco periodico (cada 3s) para captar nuevos peers
                if time.monotonic() - self._leaderboard_last_refresh > 3.0:
                    self._refresh_leaderboard()
                validated_date = self._player_profile.get(
                    "validated_date", "",
                )
                self.ui.leaderboard_screen_scroll = (
                    self.renderer.draw_leaderboard_screen(
                        entries_by_category=self._leaderboard_entries,
                        active_tab=self.ui.leaderboard_active_tab,
                        scroll=self.ui.leaderboard_screen_scroll,
                        mouse_pos=pygame.mouse.get_pos(),
                        peer_count=peer_count,
                        network_active=network_active,
                        validated_date=validated_date,
                        p2p_degraded=p2p_degraded,
                    )
                )
            elif self.ui.showing_skills_screen:
                self.renderer.draw_skills_screen(
                    rpg=self.rpg,
                    scroll=self.ui.skills_screen_scroll,
                    mouse_pos=pygame.mouse.get_pos(),
                )
                pygame.display.flip()
            elif self.ui.showing_ascension_screen:
                self.renderer.draw_ascension_screen(
                    rpg=self.rpg,
                    scroll=self.ui.ascension_screen_scroll,
                    mouse_pos=pygame.mouse.get_pos(),
                )
                pygame.display.flip()
            elif self.ui.showing_achievements_screen:
                self.ui.achievements_screen_scroll = (
                    self.renderer.draw_achievements_screen(
                        achievements=self.achievements,
                        scroll_offset=self.ui.achievements_screen_scroll,
                        mouse_pos=pygame.mouse.get_pos(),
                        colors=self.theme.colors,
                        stats_data=self._cached_stats_data,
                    )
                )
            elif self.ui.showing_debug_screen:
                self.ui.debug_screen_scroll = (
                    self.renderer.draw_debug_screen(
                        score_timeline=self.match.score_timeline,
                        narration_log=self.narration.narration_log,
                        narrator_memory=list(self.narration.narrator.memory),
                        scroll_offset=self.ui.debug_screen_scroll,
                        format_elapsed_fn=self._format_elapsed,
                        mouse_pos=pygame.mouse.get_pos(),
                        colors=self.theme.colors,
                    )
                )
            else:
                elapsed_total = (
                    self.game_end_time or time.monotonic()
                ) - self.game_start_time

                # Calcular progreso del resumen LLM (basado en tokens reales)
                if self.match_summary_text is not None:
                    target = 1.0
                elif self.match_summary_requested:
                    target = self.narration.get_summary_progress()
                else:
                    target = 0.0
                self._displayed_summary_progress += (
                    (target - self._displayed_summary_progress)
                    * SUMMARY_PROGRESS_LERP_FACTOR
                )
                if abs(target - self._displayed_summary_progress) < 0.005:
                    self._displayed_summary_progress = target
                summary_progress = self._displayed_summary_progress

                self.renderer.draw_end_screen(
                    score=self.match.score,
                    elapsed_text=self._format_elapsed(elapsed_total),
                    quit_hint="ESC: salir | Click en 'Jugar otra vez': nuevo partido",
                    summary_text=self.match_summary_text,
                    summary_progress=summary_progress,
                    copy_status_text=self.ui.copy_status_text,
                    mouse_pos=pygame.mouse.get_pos(),
                    colors=self.theme.colors,
                    records=self.records,
                    new_records=self.new_records,
                    achievements=self.achievements,
                    rpg=self.rpg if hasattr(self, 'rpg') else None,
                )
                # Dialogo de confirmacion de ascension (overlay sobre end screen)
                if self.ui.showing_ascension_confirm:
                    self.renderer.draw_ascension_confirm_dialog(
                        mouse_pos=pygame.mouse.get_pos(),
                    )
                    pygame.display.flip()
        else:
            # --- Preparar popup de logro si hay notificacion activa ---
            achievement_popup = None
            if self.achievements.has_notifications():
                start = self.achievements.get_notification_start()
                notif = self.achievements.peek_notification()
                if start is not None and notif is not None:
                    elapsed_popup = time.monotonic() - start
                    achievement_popup = (notif, elapsed_popup)

            self.renderer.draw_game(
                score=self.match.score,
                player=self.player,
                computer=self.computer,
                ball=self.ball,
                narration_text=self.narration.narration_text,
                question_active=self.questions.question_active,
                question_text=self.questions.current_question,
                current_answer=self.questions.current_answer,
                bullet_time_remaining=self.questions.bullet_time_remaining,
                llm_enabled=self.narration.narrator.enabled,
                colors=self.theme.colors,
                paused=self.paused,
                achievement_popup=achievement_popup,
                rpg=self.rpg if hasattr(self, 'rpg') else None,
                extra_balls=self._rpg_extra_balls if hasattr(self, '_rpg_extra_balls') else None,
            )

    # --------------------------------------------------------
    # Leaderboard / P2P
    # --------------------------------------------------------

    def _enter_p2p_connecting(self) -> None:
        """Transiciona a la pantalla de conexion P2P."""
        self.ui.showing_p2p_connecting = True
        self.ui.p2p_connect_start_time = time.monotonic()
        self._start_peer_network()

    def _exit_p2p_connecting(self) -> None:
        """Sale de la pantalla de conexion y abre el leaderboard."""
        self.ui.showing_p2p_connecting = False
        self.ui.showing_leaderboard_screen = True
        self.ui.leaderboard_screen_scroll = 0
        self._refresh_leaderboard()

    def _handle_p2p_continue_click(self, pos: tuple[int, int]) -> None:
        """Maneja click en el boton Continuar de la pantalla de conexion."""
        from pong.config.ui_leaderboard import P2P_CONNECT_MIN_SECONDS
        if (self.renderer.p2p_continue_button_rect
                and self.renderer.p2p_continue_button_rect.collidepoint(pos)):
            elapsed = time.monotonic() - self.ui.p2p_connect_start_time
            peer_count = 0
            if self._peer_network is not None:
                peer_count = self._peer_network.get_peer_count()
            if elapsed >= P2P_CONNECT_MIN_SECONDS or peer_count > 0:
                self._exit_p2p_connecting()

    def _refresh_leaderboard(self) -> None:
        """Recalcula las entries del leaderboard (local + peers remotos).

        Cuando hay peers activos:
        - Guarda el sufijo validado y backup de entries en el save.
        Cuando no hay peers:
        - Carga el backup del save para mostrar datos historicos.
        - Usa el sufijo guardado en vez de ``????``.
        """
        from pong.leaderboard import (
            LeaderboardEntry,
            compute_entries_digest,
            get_local_entries,
            merge_entries,
        )
        from pong.save_manager import get_p2p_backup, save_p2p_validation

        history = load_history()
        local = get_local_entries(history, self._player_profile)
        remote: list[Any] = []
        peer_count = 0
        if self._peer_network is not None:
            remote = self._peer_network.get_peer_entries()
            peer_count = self._peer_network.get_peer_count()

        saved_suffix = self._player_profile.get("validated_suffix", "")

        remote_digest = compute_entries_digest(remote) if remote else ""

        if peer_count > 0 and remote and remote_digest != self._p2p_last_backup_digest:
            # Guardar/actualizar validacion y backup cuando hay entries nuevas
            self._p2p_last_backup_digest = remote_digest
            all_entries = local + remote
            alias = self._player_profile.get("alias", "")
            fp = self._player_profile.get("fingerprint", "")
            suffix = self._compute_local_suffix(all_entries, alias, fp)
            backup = [e.to_dict() for e in remote]
            self._player_profile = save_p2p_validation(suffix, backup)
            saved_suffix = suffix

        # Si no hay peers activos, cargar backup del save como remotos
        if peer_count == 0 and not remote:
            backup_raw = get_p2p_backup(history)
            for raw in backup_raw:
                entry = LeaderboardEntry.from_dict(raw)
                remote.append(entry)

        self._leaderboard_entries = merge_entries(
            local, remote,
            p2p_validated=peer_count > 0,
            saved_suffix=saved_suffix,
        )
        self._leaderboard_last_refresh = time.monotonic()

    @staticmethod
    def _compute_local_suffix(
        entries: list[Any], alias: str, fingerprint: str,
    ) -> str:
        """Calcula el sufijo B64 que le corresponde al jugador local."""
        from pong.leaderboard import _index_to_b64_suffix
        # Recoger fingerprints unicos con el mismo alias, ordenar
        fps = sorted({e.fingerprint for e in entries if e.alias == alias})
        try:
            idx = fps.index(fingerprint)
        except ValueError:
            idx = 0
        return _index_to_b64_suffix(idx)

    def _sync_local_records_to_peer_network(self) -> None:
        """Recalcula y publica los records locales hacia la red P2P activa."""
        if self._peer_network is None or not self._player_profile.get("alias"):
            return
        from pong.leaderboard import get_local_entries

        history = load_history()
        entries = get_local_entries(history, self._player_profile)
        self._peer_network.broadcast_records(entries)

    def _start_peer_network(self) -> None:
        """Arranca la red P2P en background (no bloquea)."""
        if self._peer_network is not None:
            return
        self._p2p_last_backup_digest = ""
        if not self._player_profile.get("alias"):
            return
        try:
            from pong.p2p import PeerNetwork
            from pong.save_manager import SAVE_DIR

            self._peer_network = PeerNetwork(
                profile=self._player_profile,
                cache_path=SAVE_DIR / "known_peers.json",
            )
            # Cargar records ANTES de arrancar hilos (evitar race condition)
            self._sync_local_records_to_peer_network()
            self._peer_network.start()
        except Exception:
            self._peer_network = None

    def _stop_peer_network(self) -> None:
        """Detiene la red P2P."""
        if self._peer_network is not None:
            self._peer_network.stop()
            self._peer_network = None

    # --------------------------------------------------------
    # Bucle principal
    # --------------------------------------------------------

    def run(self) -> None:
        """
        Bucle principal del juego.

        Se repite 60 veces por segundo hasta que el jugador cierra el juego:
        1. Leer teclado.
        2. Actualizar logica.
        3. Dibujar pantalla.
        4. Esperar al siguiente frame (60 FPS).
        """
        try:
            while self.running:
                self.handle_input()
                self.update()
                self.draw()
                self.perf.tick_frame()
                self.clock.tick(FPS)
        finally:
            # Limpieza: detener hilos de fondo y cerrar pygame
            self._stop_peer_network()
            self._shutdown_imagegen()
            self.narration.stop()
            from pathlib import Path
            self.perf.export_json(Path("saves/perf_last.json"))
            self._emit_terminal_line(f"[PERF]   {self.perf.summary_line()}")
            pygame.quit()
            self._emit_terminal_line("[FIN]    Juego cerrado.")
