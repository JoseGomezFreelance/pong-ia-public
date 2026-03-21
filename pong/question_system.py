"""
pong/question_system.py -- Sistema de preguntas y respuestas del narrador.

Este modulo gestiona el dialogo interactivo entre el narrador y el jugador.
Tras un retraso inicial configurable, el narrador hace preguntas de Si/No y el jugador responde
moviendo su paleta: arriba del todo = Si, abajo del todo = No, cualquier
otra posicion = Duda.

Durante la pregunta el juego entra en "bullet time" (camara lenta) para
dar tiempo al jugador a posicionar su paleta.

Contiene:
- DialogueEntry: un turno de dialogo (pregunta + respuesta).
- QuestionSystem: maquina de estados que controla el ciclo de preguntas.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

from pong.config.gameplay import PADDLE_HEIGHT
from pong.config.layout import GAME_AREA_HEIGHT
from pong.config.narrator import (
    ANSWER_THRESHOLD_PX,
    BULLET_TIME_DURATION_SECONDS,
    BULLET_TIME_SPEED_MULTIPLIER,
    INITIAL_QUESTIONS,
    QUESTION_FIRST_DELAY_SECONDS,
    QUESTION_INTERVAL_SECONDS,
)


@dataclass
class DialogueEntry:
    """
    Un turno de dialogo: una pregunta del narrador y la respuesta del jugador.

    Atributos:
        question:        Texto de la pregunta.
        answer:          Respuesta del jugador ("Si", "No" o "Duda").
        elapsed_seconds: Tiempo desde el inicio del partido cuando se pregunto.
    """

    question: str
    answer: str
    elapsed_seconds: float


class QuestionSystem:
    """
    Maquina de estados que controla el ciclo de preguntas del narrador.

    Ciclo:
    1. Al inicio se elige una pregunta al azar y se envia al LLM para
       que la reformule (nunca se hace igual).
    2. Tras el retraso inicial configurado, se activa la pregunta con bullet time.
    3. El jugador responde con la posicion de su paleta.
    4. Se registra la respuesta y se pide al LLM una nueva pregunta.
    5. Tras el intervalo configurado, se repite el ciclo.

    Atributos:
        dialogue_history:      Lista de DialogueEntry con todo el dialogo.
        question_active:       True si hay una pregunta activa en pantalla.
        current_question:      Texto de la pregunta mostrada.
        bullet_time_remaining: Segundos reales restantes de bullet time.
        current_answer:        Respuesta seleccionada actualmente.
        next_question_time:    Timestamp (monotonic) de la siguiente pregunta.
        pending_question:      Proxima pregunta lista del LLM (o None).
        first_question_ready:  True cuando la primera pregunta reformulada esta lista.
    """

    def __init__(self, game_start_time: float) -> None:
        """
        Inicializa el sistema de preguntas.

        Args:
            game_start_time: Valor de time.monotonic() al arrancar el partido.
        """
        self.dialogue_history: list[DialogueEntry] = []
        self.question_active: bool = False
        self.current_question: str = ""
        self.bullet_time_remaining: float = 0.0
        self.current_answer: str = "Duda"
        self.next_question_time: float = game_start_time + QUESTION_FIRST_DELAY_SECONDS
        self.pending_question: str | None = None
        self.first_question_ready: bool = False

        # Pregunta inicial elegida al azar (antes de reformulacion)
        self._selected_initial_question: str = random.choice(INITIAL_QUESTIONS)
        self._game_start_time: float = game_start_time

    def reset_timers(self, new_start_time: float) -> None:
        """Recalibra los timers al nuevo inicio de partida.

        Se llama tras la pantalla de portada/descarga para que el reloj
        del partido empiece desde cero al pulsar JUGAR.
        """
        self._game_start_time = new_start_time
        self.next_question_time = new_start_time + QUESTION_FIRST_DELAY_SECONDS

    @property
    def selected_initial_question(self) -> str:
        """La pregunta inicial elegida al azar (antes de reformulacion por el LLM)."""
        return self._selected_initial_question

    # --------------------------------------------------------
    # Consultas de estado
    # --------------------------------------------------------

    def is_bullet_time(self) -> bool:
        """True si el juego esta en bullet time (camara lenta)."""
        return self.question_active and self.bullet_time_remaining > 0

    def get_speed_multiplier(self) -> float:
        """
        Devuelve el multiplicador de velocidad actual.

        Returns:
            BULLET_TIME_SPEED_MULTIPLIER durante bullet time, 1.0 en condiciones normales.
        """
        if self.is_bullet_time():
            return BULLET_TIME_SPEED_MULTIPLIER
        return 1.0

    def should_ask_question(self, current_time: float) -> bool:
        """
        Comprueba si es momento de hacer una pregunta.

        Solo devuelve True si:
        - No hay pregunta activa.
        - Ya se paso el tiempo programado.
        - Hay una pregunta pendiente lista del LLM.

        Args:
            current_time: Valor actual de time.monotonic().

        Returns:
            True si hay que activar una pregunta.
        """
        if self.question_active:
            return False
        if current_time < self.next_question_time:
            return False
        return self.pending_question is not None

    # --------------------------------------------------------
    # Ciclo de vida de una pregunta
    # --------------------------------------------------------

    def start_question(self, question_text: str, current_time: float) -> None:
        """
        Activa una pregunta: muestra el texto e inicia bullet time.

        Args:
            question_text: La pregunta a mostrar al jugador.
            current_time:  Valor actual de time.monotonic().
        """
        self.question_active = True
        self.current_question = question_text
        self.bullet_time_remaining = BULLET_TIME_DURATION_SECONDS
        self.current_answer = "Duda"

    def update(self, dt_real: float, paddle_top_y: float) -> None:
        """
        Actualiza el estado del bullet time y la respuesta seleccionada.

        Se llama cada frame. dt_real es el tiempo real entre frames
        (no el escalado por bullet time).

        Args:
            dt_real:       Tiempo real transcurrido en segundos (~1/60).
            paddle_top_y:  Posicion rect.top de la paleta del jugador.
        """
        if not self.question_active:
            return

        # Actualizar respuesta segun posicion de la paleta
        self.current_answer = self._determine_answer(paddle_top_y)

        # Decrementar temporizador de bullet time
        self.bullet_time_remaining -= dt_real
        if self.bullet_time_remaining <= 0:
            self.bullet_time_remaining = 0
            self._finalize_answer()

    def _determine_answer(self, paddle_top_y: float) -> str:
        """
        Determina la respuesta segun la posicion vertical de la paleta.

        Umbral estricto: solo "Si" o "No" cuando la paleta esta pegada
        a la pared (dentro de ANSWER_THRESHOLD_PX pixeles del borde).
        Cualquier otra posicion es "Duda".

        Args:
            paddle_top_y: rect.top de la paleta (0 = arriba, 420 = abajo max).

        Returns:
            "Si", "Duda" o "No".
        """
        max_top = GAME_AREA_HEIGHT - PADDLE_HEIGHT
        if paddle_top_y <= ANSWER_THRESHOLD_PX:
            return "Si"
        elif paddle_top_y >= max_top - ANSWER_THRESHOLD_PX:
            return "No"
        else:
            return "Duda"

    def _finalize_answer(self) -> None:
        """
        Cierra la pregunta activa y registra la respuesta en el historial.

        Tambien programa el tiempo de la siguiente pregunta.
        """
        elapsed = time.monotonic() - self._game_start_time
        entry = DialogueEntry(
            question=self.current_question,
            answer=self.current_answer,
            elapsed_seconds=elapsed,
        )
        self.dialogue_history.append(entry)
        self.question_active = False
        self.current_question = ""
        self.pending_question = None
        # Programar la siguiente pregunta
        self.next_question_time = time.monotonic() + QUESTION_INTERVAL_SECONDS

    # --------------------------------------------------------
    # Gestion de preguntas pendientes
    # --------------------------------------------------------

    def set_pending_question(self, question_text: str) -> None:
        """
        Almacena la proxima pregunta preparada por el LLM.

        Args:
            question_text: La pregunta lista para ser mostrada.
        """
        self.pending_question = question_text

    def get_dialogue_summary(self) -> str:
        """
        Genera un resumen del dialogo para incluir en el prompt del LLM.

        Returns:
            String con las preguntas y respuestas anteriores formateadas,
            o "(sin dialogo previo)" si no hay historial.
        """
        if not self.dialogue_history:
            return "(sin dialogo previo)"
        lines = []
        for i, entry in enumerate(self.dialogue_history, 1):
            lines.append(f"{i}. Pregunta: {entry.question}")
            lines.append(f"   Respuesta del jugador: {entry.answer}")
        return "\n".join(lines)

    def get_dialogue_essence(self, limit: int = 3) -> str:
        """
        Resumen compacto del dialogo para inyectar en comentarios del narrador.

        Produce ~15 palabras con la postura del jugador, el tema reciente
        y la ultima respuesta. No usa el LLM, es puro Python.

        Args:
            limit: Maximo de turnos recientes a considerar.

        Returns:
            String corto con la esencia del dialogo, o "" si no hay historial.
        """
        if not self.dialogue_history:
            return ""
        recent = self.dialogue_history[-limit:]
        answers = [e.answer for e in recent]
        yes_c, no_c = answers.count("Si"), answers.count("No")
        if yes_c > no_c:
            stance = "confiado"
        elif no_c > yes_c:
            stance = "esceptico"
        else:
            stance = "indeciso"
        last = recent[-1]
        topic_words = [w for w in last.question.split() if len(w) > 4][:3]
        topic = " ".join(topic_words) if topic_words else "el partido"
        return (
            f"Jugador {stance}. "
            f"Tema reciente: {topic}. "
            f"Ultima respuesta: {last.answer}."
        )

    def get_recent_dialogue_context(self, limit: int = 4) -> list[dict[str, str | int]]:
        """
        Devuelve turnos recientes en formato estructurado para el LLM.

        Args:
            limit: Numero maximo de turnos a devolver (desde el mas reciente).

        Returns:
            Lista de diccionarios con pregunta, respuesta y segundos transcurridos.
        """
        if limit <= 0:
            return []
        turns = self.dialogue_history[-limit:]
        return [
            {
                "question": entry.question,
                "answer": entry.answer,
                "elapsed_seconds": int(entry.elapsed_seconds),
            }
            for entry in turns
        ]
