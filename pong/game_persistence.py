"""
pong/game_persistence.py -- Mixin con lógica de guardado, resumen y reinicio.

Extraído de game.py para reducir su tamaño. La clase Game hereda
de GamePersistenceMixin para obtener estos métodos.
"""

from __future__ import annotations

import subprocess
import sys
import time
from typing import TYPE_CHECKING, Any

import pygame

from pong.config.gameplay import PADDLE_HEIGHT
from pong.config.layout import GAME_AREA_HEIGHT
from pong.config.narrator import SUMMARY_MIN_REASONING_SECONDS
from pong.config.ui_end_screen import END_SCREEN_COPY_STATUS_SECONDS
from pong.emotional_state import EmotionalState
from pong.game_state import MatchState, UIState
from pong.question_system import QuestionSystem
from pong.save_manager import load_history, save_session

if TYPE_CHECKING:
    from pong.achievements import AchievementEngine
    from pong.entities import Ball, Paddle
    from pong.protocols import NarrationBridgeProtocol, SoundManagerProtocol
    from pong.renderer import Renderer
    from pong.rpg_engine import RPGState


class GamePersistenceMixin:
    """Métodos de guardado, exportación y reinicio, usados por Game vía herencia."""

    # -- Atributos declarados en Game, visibles aquí para mypy --
    match: MatchState
    ui: UIState
    terminal_log_lines: list[str]
    game_end_time: float | None
    game_start_time: float
    _cached_stats_data: dict[str, Any] | None
    paused: bool
    match_summary_text: str | None
    match_summary_requested: bool
    match_summary_start_time: float | None
    _displayed_summary_progress: float
    game_saved: bool
    new_records: list[str]
    records: dict[str, Any]
    player: Paddle
    computer: Paddle
    computer_home_x: int
    ball: Ball
    emotional_state: EmotionalState
    emotional_target: EmotionalState
    emotion_active: bool
    _player_positions: list[int]
    _player_sample_counter: int
    _player_idle_score: float
    questions: QuestionSystem
    narration: NarrationBridgeProtocol
    achievements: AchievementEngine
    sounds: SoundManagerProtocol
    rpg: RPGState
    imagegen_unlocked: bool
    imagegen_active: bool
    _last_imagegen_time: float
    renderer: Renderer

    def _log(self, category: str, message: str) -> None:
        raise NotImplementedError  # Provided by Game

    def _emit_terminal_line(self, message: str = "") -> None:
        raise NotImplementedError  # Provided by Game

    @staticmethod
    def _format_elapsed(total_seconds: float) -> str:
        raise NotImplementedError  # Provided by Game

    def _prepare_match(self) -> None:
        raise NotImplementedError  # Provided by Game

    def _sync_local_records_to_peer_network(self) -> None:
        raise NotImplementedError  # Provided by Game

    # _rpg_get_save_data, _init_rpg, _rpg_apply_modifiers: GameRPGMixin
    # (must appear AFTER GameRPGMixin in MRO)

    def _set_copy_status(self, message: str) -> None:
        """
        Actualiza el mensaje temporal del botón copiar.

        Args:
            message: Texto breve de estado para la pantalla final.
        """
        self.ui.copy_status_text = message
        self.ui.copy_status_expires_at = (
            time.monotonic() + END_SCREEN_COPY_STATUS_SECONDS
        )

    def _build_terminal_export_text(self) -> str:
        """
        Construye el texto completo que se copiará al portapapeles.

        Returns:
            String con todas las líneas emitidas por este proceso de juego.
        """
        if not self.terminal_log_lines:
            return "(sin logs)"
        return "\n".join(self.terminal_log_lines)

    @staticmethod
    def _copy_text_to_clipboard(text: str) -> tuple[bool, str]:
        """
        Copia texto al portapapeles con varios métodos de respaldo.

        Orden: pygame.scrap -> utilidad nativa del sistema.

        Args:
            text: Contenido a copiar.

        Returns:
            tuple[bool, str]: (True, "") si copia bien; (False, error) si falla.
        """
        data = text.encode("utf-8")

        try:
            if not pygame.scrap.get_init():
                pygame.scrap.init()
            pygame.scrap.put(pygame.SCRAP_TEXT, data)
            return True, ""
        except (pygame.error, AttributeError, OSError):
            pass

        commands = []
        if sys.platform == "darwin":
            commands = [["pbcopy"]]
        elif sys.platform.startswith("win"):
            commands = [["cmd", "/c", "clip"]]
        else:
            commands = [
                ["wl-copy"],
                ["xclip", "-selection", "clipboard"],
                ["xsel", "--clipboard", "--input"],
            ]

        for command in commands:
            try:
                subprocess.run(command, input=data, check=True)
                return True, ""
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue

        return False, "No se pudo acceder al portapapeles."

    def _copy_terminal_logs(self) -> None:
        """
        Copia los logs acumulados a portapapeles y deja feedback visual.
        """
        payload = self._build_terminal_export_text()
        copied, error = self._copy_text_to_clipboard(payload)
        if copied:
            self._log("COPIA", f"Se copiaron {len(payload)} caracteres al portapapeles.")
            self._set_copy_status("Logs copiados.")
        else:
            self._log("COPIA", f"Fallo al copiar logs: {error}")
            self._set_copy_status("No se pudo copiar.")

    # --------------------------------------------------------
    # Resumen final
    # --------------------------------------------------------

    def _print_end_summary(self) -> None:
        """Imprime por terminal toda la información de la pantalla final."""
        elapsed_total = (
            self.game_end_time or time.monotonic()
        ) - self.game_start_time

        self._emit_terminal_line()
        self._emit_terminal_line("=" * 60)
        self._emit_terminal_line("FIN DE PARTIDA \u2014 Resumen completo")
        self._emit_terminal_line("=" * 60)
        self._emit_terminal_line(
            f"Sets finales: Jugador {self.match.score.player_sets} - "
            f"Ordenador {self.match.score.computer_sets}"
        )
        self._emit_terminal_line(
            f"Juegos del ultimo set: Jugador {self.match.score.player_games} - "
            f"Ordenador {self.match.score.computer_games}"
        )
        self._emit_terminal_line(f"Tiempo total: {self._format_elapsed(elapsed_total)}")
        self._emit_terminal_line()

        self._emit_terminal_line("--- EVENTOS DE PUNTO ---")
        if not self.match.score_timeline:
            self._emit_terminal_line("  Sin puntos registrados.")
        else:
            for point in self.match.score_timeline:
                stamp = self._format_elapsed(point["elapsed_seconds"])
                self._emit_terminal_line(
                    f"  [{stamp}] {point['description']} -> {point['scoreboard']}"
                )
        self._emit_terminal_line()

        self._emit_terminal_line("--- HISTORIAL DE MENSAJES LLM ---")
        if not self.narration.narration_log:
            self._emit_terminal_line("  Sin mensajes de narrador registrados.")
        else:
            for entry in self.narration.narration_log:
                stamp = self._format_elapsed(entry["elapsed_seconds"])
                self._emit_terminal_line(
                    f"  [{stamp}] ({entry['event_label']}, "
                    f"{entry['scoreboard']}) {entry['text']}"
                )
        self._emit_terminal_line()

        self._emit_terminal_line("--- MEMORIA FINAL DEL LLM ---")
        if not self.narration.narrator.memory:
            self._emit_terminal_line("  Sin memoria final.")
        else:
            for index, turn in enumerate(
                self.narration.narrator.memory, start=1
            ):
                marker = turn.get("scoreboard")
                if not marker:
                    player_score = turn.get("player_score", "?")
                    computer_score = turn.get("computer_score", "?")
                    marker = f"{player_score}-{computer_score}"
                self._emit_terminal_line(
                    f"  {index}. Evento={turn['event_label']} | "
                    f"Jugada={turn['last_play']} | "
                    f"Marcador={marker} | "
                    f"Narracion={turn['narration']}"
                )
        self._emit_terminal_line()

        self._emit_terminal_line("--- HISTORIAL DE DIALOGO ---")
        if not self.questions.dialogue_history:
            self._emit_terminal_line("  Sin preguntas realizadas.")
        else:
            for i, dialogue in enumerate(self.questions.dialogue_history, 1):
                stamp = self._format_elapsed(dialogue.elapsed_seconds)
                self._emit_terminal_line(f"  {i}. [{stamp}] P: {dialogue.question}")
                self._emit_terminal_line(f"     R: {dialogue.answer}")
        self._emit_terminal_line("=" * 60)

    def _request_match_summary(self) -> None:
        """
        Construye los datos del partido y solicita al LLM un resumen.

        Se llama una sola vez al entrar en la pantalla de fin de partida.
        """
        if self.match_summary_requested:
            return
        self.match_summary_requested = True
        self.match_summary_start_time = time.monotonic()

        elapsed_total = (
            self.game_end_time or time.monotonic()
        ) - self.game_start_time

        # Determinar ganador
        if self.match.score.player_sets > self.match.score.computer_sets:
            winner = "el Jugador"
        else:
            winner = "el Ordenador"

        # Calcular puntos totales y rachas máximas
        player_pts_total = 0
        computer_pts_total = 0
        max_player_streak = 0
        max_computer_streak = 0
        current_player_streak = 0
        current_computer_streak = 0

        for point in self.match.score_timeline:
            desc = point["description"].lower()
            if "jugador" in desc:
                player_pts_total += 1
                current_player_streak += 1
                current_computer_streak = 0
                max_player_streak = max(max_player_streak, current_player_streak)
            elif "ordenador" in desc:
                computer_pts_total += 1
                current_computer_streak += 1
                current_player_streak = 0
                max_computer_streak = max(max_computer_streak, current_computer_streak)

        # Seleccionar narraciones destacadas (hasta 6, espaciadas)
        highlights = []
        if self.narration.narration_log:
            log = self.narration.narration_log
            step = max(1, len(log) // 6)
            for i in range(0, len(log), step):
                entry = log[i]
                highlights.append(
                    f"[{self._format_elapsed(entry['elapsed_seconds'])}] "
                    f"{entry['text']}"
                )
            highlights = highlights[:6]

        match_data = {
            "winner": winner,
            "final_sets": (
                f"{self.match.score.player_sets}-{self.match.score.computer_sets}"
            ),
            "final_games_last_set": (
                f"{self.match.score.player_games}-{self.match.score.computer_games}"
            ),
            "elapsed_text": self._format_elapsed(elapsed_total),
            "total_points": player_pts_total + computer_pts_total,
            "player_points_total": player_pts_total,
            "computer_points_total": computer_pts_total,
            "longest_streak_player": max_player_streak,
            "longest_streak_computer": max_computer_streak,
            "dialogue_summary": self.questions.get_dialogue_summary(),
            "dialogue_essence": self.questions.get_dialogue_essence(),
            "dialogue_count": len(self.questions.dialogue_history),
            "narration_highlights": (
                "\n".join(highlights) if highlights else "(sin narraciones)"
            ),
            "min_reflection_seconds": (
                SUMMARY_MIN_REASONING_SECONDS
                if self.narration.narrator.enabled
                else 0.0
            ),
        }

        self.narration.request_match_summary(match_data)

    # --------------------------------------------------------
    # Guardado
    # --------------------------------------------------------

    def _save_game(self) -> None:
        """
        Guarda la partida actual en el historial JSON.

        Se llama una sola vez cuando el resumen del LLM está listo.
        Calcula los records y detecta cuáles son nuevos.
        """
        if self.game_saved:
            return
        self.game_saved = True

        elapsed_total = (
            self.game_end_time or time.monotonic()
        ) - self.game_start_time

        # Calcular puntos totales y rachas
        player_pts = 0
        computer_pts = 0
        max_streak = 0
        current_streak = 0
        for point in self.match.score_timeline:
            desc = point["description"].lower()
            if "jugador" in desc:
                player_pts += 1
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            elif "ordenador" in desc:
                computer_pts += 1
                current_streak = 0

        winner = (
            "jugador"
            if self.match.score.player_sets > self.match.score.computer_sets
            else "ordenador"
        )

        session_data = {
            "winner": winner,
            "player_sets": self.match.score.player_sets,
            "computer_sets": self.match.score.computer_sets,
            "player_games": self.match.score.player_games,
            "computer_games": self.match.score.computer_games,
            "player_points_total": player_pts,
            "computer_points_total": computer_pts,
            "elapsed_seconds": round(elapsed_total, 1),
            "max_rally": self.match.max_rally_hits,
            "longest_player_streak": max_streak,
            "point_differential": player_pts - computer_pts,
            "llm_summary": self.match_summary_text or "",
        }

        # --- Comprobar logros de fin de partido ---
        history = load_history()
        session_index = len(history["sessions"])
        new_achs = self.achievements.check_post_match(
            session_data, session_index
        )
        # Comprobar logros de diálogo (si hubo al menos 3 preguntas)
        new_achs.extend(
            self.achievements.check_dialogue_achievements(
                self.questions.dialogue_history, session_index
            )
        )
        if new_achs:
            self.sounds.play_achievement()
            for aid in new_achs:
                self._log(
                    "LOGRO",
                    f"Desbloqueado: {self.achievements.definitions[aid].name}",
                )

        # Persistir con logros, estadísticas de carrera y RPG
        rpg_data = self._rpg_get_save_data()  # type: ignore[attr-defined]
        self.records, self.new_records, newly_unlocked = save_session(
            session_data,
            achievements=self.achievements.get_save_data(),
            career_stats=self.achievements.get_career_stats_data(),
            rpg_data=rpg_data,
        )
        self._sync_local_records_to_peer_network()

        if self.new_records:
            self._log(
                "RECORD",
                f"Nuevos records: {', '.join(self.new_records)}",
            )

        # Comprobar desbloqueo de fases
        if "imagegen" in newly_unlocked:
            self.imagegen_unlocked = True
            self._log("FASE", "Fase visual generativa desbloqueada")
        if "rpg" in newly_unlocked:
            self.rpg.rpg_unlocked = True
            self._log("FASE", "Modo RPG desbloqueado!")

    # --------------------------------------------------------
    # Reinicio de partida
    # --------------------------------------------------------

    def _restart_match(self) -> None:
        """
        Reinicia la partida actual sin cerrar la aplicación.

        Se mantiene el narrador cargado para evitar tiempos de espera largos,
        pero se limpia todo el estado del partido (marcador, timeline, preguntas,
        resumen final y logs temporales de pantalla).
        """
        if self.ui.showing_end_screen and not self.game_saved:
            self._save_game()

        # Resetear estado agrupado
        self.match = MatchState()
        self.ui = UIState()

        self._cached_stats_data = None
        self.paused = False
        self.game_start_time = time.monotonic()
        self.game_end_time = None
        self.match_summary_text = None
        self.match_summary_requested = False
        self.match_summary_start_time = None
        self._displayed_summary_progress = 0.0
        self.game_saved = False
        self.new_records = []

        center_y = GAME_AREA_HEIGHT // 2 - PADDLE_HEIGHT // 2
        self.player.rect.y = center_y
        if hasattr(self, "computer_home_x") and hasattr(self.computer.rect, "x"):
            self.computer.rect.x = self.computer_home_x
        self.computer.rect.y = center_y
        self.ball.reset()

        self.emotional_state = EmotionalState()
        self.emotional_target = EmotionalState()
        self.emotion_active = False
        self._player_positions = []
        self._player_sample_counter = 0
        self._player_idle_score = 0.0

        self.narration.reset_match_state()
        self._prepare_match()

        self.achievements.pending_notifications.clear()
        self.achievements.set_notification_start(None)

        # Resetear fase visual generativa (el modelo permanece cargado)
        self.imagegen_active = False
        self._last_imagegen_time = 0.0
        self.renderer.clear_background_image()
        # Recargar estado de desbloqueo (puede haberse desbloqueado en la partida anterior)
        _history = load_history()
        self.imagegen_unlocked = "imagegen" in _history.get("phases_unlocked", {})

        # Recargar estado RPG (conserva progreso entre partidas)
        self._init_rpg()  # type: ignore[attr-defined]

        self._log("PARTIDA", "Nueva partida iniciada.")
