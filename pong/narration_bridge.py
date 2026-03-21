"""
pong/narration_bridge.py -- Puente entre el juego y el narrador IA.

El narrador IA (LocalNarrator) tarda unos segundos en generar texto porque
ejecuta un modelo de lenguaje. Si lo llamaramos directamente desde el bucle
del juego, el juego se "congelaria" mientras espera.

Para evitar esto, este modulo ejecuta las peticiones de narracion en un
hilo de fondo (background thread). El juego sigue funcionando a 60 FPS
mientras el narrador piensa, y cuando la narracion esta lista, se muestra
en el siguiente frame.

Contiene:
- NarrationBridge: clase que gestiona la cola de peticiones, el hilo
  de fondo, y la publicacion de narraciones al HUD.
"""

from __future__ import annotations

import threading
import time
from queue import Empty, Full, Queue
from typing import Any, Callable

from pong.config.narrator import NARRATION_INTERVAL_SECONDS, SUMMARY_MIN_REASONING_SECONDS
from pong.emotional_state import EmotionalState
from pong.entities import Ball
from pong.narrator import LocalNarrator
from pong.scoring import ScoreState


class NarrationBridge:
    """
    Gestiona la comunicacion asincrona entre el juego y el narrador IA.

    Funciona asi:
    1. El juego llama a request() cuando quiere narracion (punto, rally, etc.).
    2. La peticion se mete en una cola de tamaño 1.
    3. Un hilo de fondo saca la peticion, llama al narrador, y guarda el resultado.
    4. El juego llama a consume_pending() cada frame para recoger el resultado.

    Para eventos importantes (puntos, juegos, sets), se publica un texto
    de respaldo INSTANTANEAMENTE sin esperar al LLM, para que el jugador
    vea la narracion al momento. El LLM genera su version despues.

    Atributos:
        narrator:         Instancia de LocalNarrator.
        narration_text:   Texto de narracion actual mostrado en pantalla.
        narration_log:    Historial de todas las narraciones (para depuracion).
        last_request_time: Timestamp de la ultima peticion (para controlar intervalo).
    """

    def __init__(self, llm_provider: Any | None = None) -> None:
        """Inicializa el narrador, la cola y el hilo de fondo.

        Args:
            llm_provider: Objeto que cumple ``LLMProviderProtocol``.
                          Si es ``None``, se carga el provider por defecto
                          via ``load_llm_provider()``.
        """
        if llm_provider is None:
            from pong.providers import load_llm_provider
            from pong.config.models import load_models_config
            llm_config, _ = load_models_config()
            llm_provider = load_llm_provider(llm_config)
        self.narrator: LocalNarrator = LocalNarrator(llm_provider)

        # Texto que se muestra en pantalla ahora mismo
        self.narration_text: str = "Comienza el duelo. \u00a1Demuestra tus reflejos!"

        # Historial completo de narraciones (para la pantalla de depuracion)
        self.narration_log: list[dict[str, Any]] = []

        # Control de tiempo entre peticiones
        self.last_request_time: float = 0.0

        # --- Mecanismo de threading ---

        # Cola de peticiones con tamaño 1: solo guardamos la peticion mas reciente.
        # Si llega una nueva antes de que se procese la anterior, la anterior se descarta.
        self._requests: Queue[dict[str, Any]] = Queue(maxsize=1)

        # Contador de peticiones para descartar respuestas obsoletas
        self._request_seq: int = 0

        # ID de la ultima peticion prioritaria (para descartar respuestas viejas)
        self._latest_priority_id: int = 0
        self._match_generation: int = 0

        # Narracion pendiente de publicar (producida por el hilo de fondo)
        self._pending: dict[str, Any] | None = None

        # Lock para acceder a _pending de forma segura entre hilos
        self._lock: threading.Lock = threading.Lock()

        # Señal para detener el hilo de fondo limpiamente
        self._stop_event: threading.Event = threading.Event()

        # Funcion de log que se configura desde Game
        self._log_fn: Callable[[str, str], None] | None = None

        # --- Sistema de preguntas ---
        # Cola separada para peticiones de preguntas (no compite con narracion)
        self._question_requests: Queue[dict[str, Any]] = Queue(maxsize=1)
        # Pregunta pendiente de entregar al sistema de preguntas
        self._pending_question: str | None = None
        self._pending_question_generation: int | None = None
        self._question_lock: threading.Lock = threading.Lock()

        # --- Estado emocional de la IA ---
        # Perfil emocional generado junto con la pregunta (puede ser None)
        self._pending_emotion: EmotionalState | None = None
        self._pending_emotion_generation: int | None = None
        self._emotion_lock: threading.Lock = threading.Lock()

        # --- Resumen de fin de partido ---
        self._summary_requests: Queue[dict[str, Any]] = Queue(maxsize=1)
        self._pending_summary: str | None = None
        self._pending_summary_ready_at: float | None = None
        self._pending_summary_generation: int | None = None
        self._summary_lock: threading.Lock = threading.Lock()
        self._summary_progress: float = 0.0

        # --- Enriquecimiento de prompts de imagen ---
        self._image_prompt_requests: Queue[dict[str, Any]] = Queue(maxsize=1)
        self._pending_image_prompt: tuple[str, str] | None = None
        self._pending_image_prompt_generation: int | None = None
        self._image_prompt_lock: threading.Lock = threading.Lock()

        # --- Metricas de rendimiento (opcional) ---
        self._perf: Any = None

    def set_perf(self, perf: Any) -> None:
        """Inyecta el recolector de metricas de rendimiento."""
        self._perf = perf

    def start(self, log_fn: Callable[[str, str], None] | None = None) -> None:
        """
        Arranca el hilo de fondo que procesa las peticiones de narracion.

        Args:
            log_fn: Funcion opcional para imprimir logs (recibe categoria y mensaje).
        """
        self._log_fn = log_fn
        self._thread: threading.Thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Detiene el hilo de fondo y espera a que termine."""
        self._stop_event.set()
        if hasattr(self, "_thread"):
            self._thread.join(timeout=5)

    def reset_match_state(self, opening_text: str | None = None) -> None:
        """
        Limpia el estado temporal para iniciar una partida nueva.

        Args:
            opening_text: Texto inicial opcional para la zona de narracion.
        """
        self._match_generation += 1
        self._latest_priority_id = 0
        self.last_request_time = 0.0
        self.narration_log.clear()
        self.narrator.memory.clear()
        self.narration_text = (
            opening_text
            if opening_text is not None
            else "Comienza el duelo. \u00a1Demuestra tus reflejos!"
        )

        self._drain_queue(self._requests)
        self._drain_queue(self._question_requests)
        self._drain_queue(self._summary_requests)
        self._drain_queue(self._image_prompt_requests)

        with self._lock:
            self._pending = None
        with self._question_lock:
            self._pending_question = None
            self._pending_question_generation = None
        with self._emotion_lock:
            self._pending_emotion = None
            self._pending_emotion_generation = None
        with self._summary_lock:
            self._pending_summary = None
            self._pending_summary_ready_at = None
            self._pending_summary_generation = None
            self._summary_progress = 0.0
        with self._image_prompt_lock:
            self._pending_image_prompt = None
            self._pending_image_prompt_generation = None

    @staticmethod
    def _drain_queue(queue_obj: Queue[Any]) -> None:
        """Vacía una cola sin bloquear; se usa al reiniciar partido."""
        while True:
            try:
                queue_obj.get_nowait()
            except Empty:
                break

    # --------------------------------------------------------
    # Solicitar narracion
    # --------------------------------------------------------

    def request(self, event_label: str, game_state_data: dict[str, Any], priority: bool = False) -> None:
        """
        Solicita una narracion sin bloquear el hilo principal del juego.

        Si es una peticion prioritaria (evento de puntuacion), se publica
        un texto de respaldo INMEDIATAMENTE y se encola la peticion para
        que el LLM genere una version mejor.

        Si la cola esta llena y NO es prioritaria, la peticion se descarta
        silenciosamente (el juego no se congela).

        Args:
            event_label:     Tipo de evento ("punto del jugador", "juego en curso"...).
            game_state_data: Diccionario con el estado completo del juego.
            priority:        True para eventos importantes (puntos, juegos, sets).
        """
        game_state = dict(game_state_data)
        game_state["event_label"] = event_label
        game_state["match_generation"] = self._match_generation

        self._request_seq += 1
        game_state["request_id"] = self._request_seq
        game_state["priority"] = priority

        # Si es prioritaria, vaciar la cola para que esta peticion pase primero
        if priority:
            while True:
                try:
                    self._requests.get_nowait()
                except Empty:
                    break
        elif self._requests.full():
            # Cola llena y no es urgente: descartar
            return

        try:
            now = time.monotonic()
            if priority:
                self._latest_priority_id = game_state["request_id"]

                # Para eventos de puntuacion, publicar respaldo instantaneo
                if self._is_scoring_event(game_state):
                    instant_text = self.narrator._fallback_line(game_state)
                    self.narrator._remember_turn(game_state, instant_text)
                    payload = self._build_payload(game_state, instant_text)
                    self._publish(payload)
                    self.last_request_time = now
                    return

            self._requests.put_nowait(game_state)
            self.last_request_time = now
        except Full:
            pass

    def should_request_periodic(self) -> bool:
        """
        Indica si ya paso suficiente tiempo para pedir narracion periodica.

        Durante un rally (sin puntos), el narrador genera comentarios cada
        NARRATION_INTERVAL_SECONDS segundos automaticamente.

        Returns:
            True si ya toca pedir narracion.
        """
        return (
            time.monotonic() - self.last_request_time
            >= NARRATION_INTERVAL_SECONDS
        )

    # --------------------------------------------------------
    # Solicitar preguntas al LLM
    # --------------------------------------------------------

    def request_reformulation(self, original_question: str) -> None:
        """
        Solicita la reformulacion de una pregunta inicial en el hilo de fondo.

        Args:
            original_question: La pregunta original a reformular.
        """
        try:
            self._question_requests.put_nowait(
                {
                    "type": "reformulate",
                    "original": original_question,
                    "match_generation": self._match_generation,
                }
            )
        except Full:
            pass

    def request_new_question(self, dialogue_summary: str, game_state: dict[str, Any]) -> None:
        """
        Solicita al LLM que genere una nueva pregunta basada en el dialogo.

        Args:
            dialogue_summary: Resumen del dialogo previo (preguntas y respuestas).
            game_state:       Estado actual del juego.
        """
        try:
            # Vaciar la cola (descartar peticion anterior si hay)
            while True:
                try:
                    self._question_requests.get_nowait()
                except Empty:
                    break
            self._question_requests.put_nowait(
                {
                    "type": "generate",
                    "dialogue_summary": dialogue_summary,
                    "game_state": dict(game_state),
                    "match_generation": self._match_generation,
                }
            )
        except Full:
            pass

    def consume_pending_question(self) -> str | None:
        """
        Recoge la pregunta pendiente generada por el hilo de fondo.

        Returns:
            String con la pregunta, o None si no hay ninguna lista.
        """
        with self._question_lock:
            question = self._pending_question
            generation = self._pending_question_generation
            self._pending_question = None
            self._pending_question_generation = None
        if generation is None:
            generation = self._match_generation
        if generation != self._match_generation:
            return None
        return question

    def consume_pending_emotion(self) -> EmotionalState | None:
        """
        Recoge el perfil emocional pendiente generado junto con la pregunta.

        Returns:
            EmotionalState, o None si no hay ninguno listo.
        """
        with self._emotion_lock:
            emotion = self._pending_emotion
            generation = self._pending_emotion_generation
            self._pending_emotion = None
            self._pending_emotion_generation = None
        if generation is None:
            generation = self._match_generation
        if generation != self._match_generation:
            return None
        return emotion

    # --------------------------------------------------------
    # Resumen de fin de partido
    # --------------------------------------------------------

    def request_match_summary(self, match_data: dict[str, Any]) -> None:
        """
        Solicita al LLM que genere un resumen del partido en el hilo de fondo.

        Args:
            match_data: Diccionario con datos completos del partido y dialogo.
        """
        payload = dict(match_data)
        payload["match_generation"] = self._match_generation
        try:
            while True:
                try:
                    self._summary_requests.get_nowait()
                except Empty:
                    break
            self._summary_requests.put_nowait(payload)
        except Full:
            pass

    def consume_pending_summary(self) -> str | None:
        """
        Recoge el resumen pendiente generado por el hilo de fondo.

        Returns:
            String con el resumen, o None si no esta listo.
        """
        with self._summary_lock:
            if self._pending_summary is None:
                return None
            generation = self._pending_summary_generation
            if generation is None:
                generation = self._match_generation
            if generation != self._match_generation:
                self._pending_summary = None
                self._pending_summary_ready_at = None
                self._pending_summary_generation = None
                return None

            ready_at = self._pending_summary_ready_at
            if ready_at is not None and time.monotonic() < ready_at:
                return None

            summary = self._pending_summary
            self._pending_summary = None
            self._pending_summary_ready_at = None
            self._pending_summary_generation = None
            return summary

    def get_summary_progress(self) -> float:
        """Progreso actual de generacion del resumen (0.0-1.0). Thread-safe."""
        with self._summary_lock:
            return self._summary_progress

    def _on_summary_progress(self, tokens_done: int, tokens_max: int) -> None:
        """Callback invocado por el streaming del narrador tras cada token."""
        raw = tokens_done / max(tokens_max, 1)
        with self._summary_lock:
            self._summary_progress = min(raw, 0.98)

    # --------------------------------------------------------
    # Solicitar enriquecimiento de prompt de imagen
    # --------------------------------------------------------

    def request_image_prompt_enrichment(self, base_prompt: str, negative_prompt: str,
                                        context: dict[str, Any]) -> None:
        """
        Solicita al LLM que enriquezca un prompt de imagen en el hilo de fondo.

        Args:
            base_prompt:     Prompt base generado por build_image_prompt().
            negative_prompt: Negative prompt para Stable Diffusion.
            context:         Diccionario con mood_tag, score, rally, etc.
        """
        try:
            self._drain_queue(self._image_prompt_requests)
            self._image_prompt_requests.put_nowait({
                "base_prompt": base_prompt,
                "negative_prompt": negative_prompt,
                "context": dict(context),
                "match_generation": self._match_generation,
            })
        except Full:
            pass

    def consume_pending_image_prompt(self) -> tuple[str, str] | None:
        """
        Recoge el prompt de imagen enriquecido generado por el hilo de fondo.

        Returns:
            Tupla (enriched_prompt, negative_prompt), o None si no hay
            ninguno listo.
        """
        with self._image_prompt_lock:
            result = self._pending_image_prompt
            generation = self._pending_image_prompt_generation
            self._pending_image_prompt = None
            self._pending_image_prompt_generation = None
        if result is None:
            return None
        if generation is None:
            generation = self._match_generation
        if generation != self._match_generation:
            return None
        return result

    # --------------------------------------------------------
    # Consumir narracion pendiente
    # --------------------------------------------------------

    def has_pending(self) -> bool:
        """Comprueba si hay narracion pendiente de forma thread-safe."""
        with self._lock:
            return self._pending is not None

    def consume_pending(self) -> None:
        """
        Recoge la narracion pendiente y la publica en el HUD.

        Se llama desde el hilo principal del juego, una vez por frame.
        Si hay una narracion lista del hilo de fondo, la muestra en pantalla.

        Si la narracion es mas vieja que la ultima peticion prioritaria,
        se descarta (para no sobreescribir un texto ya publicado).
        """
        with self._lock:
            payload = self._pending
            self._pending = None

        if not payload:
            return

        if payload.get("match_generation", self._match_generation) != self._match_generation:
            return

        # Descartar respuestas obsoletas (anteriores a la ultima publicacion prioritaria)
        request_id = payload.get("request_id", 0)
        if request_id < self._latest_priority_id:
            return

        self._publish(payload)

    # --------------------------------------------------------
    # Hilo de fondo
    # --------------------------------------------------------

    def _worker(self) -> None:
        """
        Bucle del hilo de fondo que procesa peticiones de narracion, preguntas
        y resumen de fin de partido.

        Prioridad: resumen > preguntas > narracion.
        El resumen solo ocurre una vez al final del partido.
        """
        while not self._stop_event.is_set():
            # Procesar peticiones de resumen (maxima prioridad, solo una vez)
            try:
                summary_data = self._summary_requests.get_nowait()
                generation = summary_data.get(
                    "match_generation", self._match_generation
                )
                if generation != self._match_generation:
                    continue
                summary_started_at = time.monotonic()
                _t0_summary = time.perf_counter()
                with self._summary_lock:
                    self._summary_progress = 0.0
                summary_text = self.narrator.generate_match_summary_streaming(
                    summary_data,
                    progress_callback=self._on_summary_progress,
                )
                if self._perf:
                    self._perf.record_llm(time.perf_counter() - _t0_summary, "summary")
                if generation != self._match_generation:
                    continue
                elapsed = time.monotonic() - summary_started_at
                min_reasoning = summary_data.get(
                    "min_reflection_seconds", SUMMARY_MIN_REASONING_SECONDS
                )
                try:
                    min_reasoning = max(0.0, float(min_reasoning))
                except (TypeError, ValueError):
                    min_reasoning = SUMMARY_MIN_REASONING_SECONDS
                ready_at = time.monotonic() + max(0.0, min_reasoning - elapsed)
                with self._summary_lock:
                    self._pending_summary = summary_text
                    self._pending_summary_ready_at = ready_at
                    self._pending_summary_generation = generation
                    self._summary_progress = 1.0
                if self._log_fn:
                    preview = summary_text[:80] if summary_text else ""
                    preview = preview.strip().strip("«»\"'`")
                    if preview:
                        self._log_fn(
                            "RESUMEN",
                            f"Resumen generado (preview): «{preview}...»",
                        )
                    else:
                        self._log_fn("RESUMEN", "Resumen generado (vacio).")
            except Empty:
                pass

            # Procesar peticiones de preguntas (prioridad media)
            try:
                q_request = self._question_requests.get_nowait()
                generation = q_request.get(
                    "match_generation", self._match_generation
                )
                if generation != self._match_generation:
                    continue
                question_text = self._process_question_request(q_request)
                if question_text:
                    if generation != self._match_generation:
                        continue
                    with self._question_lock:
                        self._pending_question = question_text
                        self._pending_question_generation = generation
            except Empty:
                pass

            # Procesar peticiones de narracion
            try:
                game_state = self._requests.get(timeout=0.05)
            except Empty:
                game_state = None

            if game_state is not None:
                generation = game_state.get("match_generation", -1)
                if generation == -1:
                    generation = self._match_generation
                if generation == self._match_generation:
                    _t0 = time.perf_counter()
                    narration = self.narrator.commentate(game_state)
                    if self._perf:
                        self._perf.record_llm(time.perf_counter() - _t0, "commentate")
                    if generation == self._match_generation:
                        payload = self._build_payload(game_state, narration)
                        with self._lock:
                            self._pending = payload

            # Procesar peticiones de enriquecimiento de prompt de imagen
            # (prioridad mas baja: solo cuando no hay nada mas urgente)
            try:
                img_request = self._image_prompt_requests.get_nowait()
                generation = img_request.get(
                    "match_generation", self._match_generation
                )
                if generation == self._match_generation:
                    _t0_img = time.perf_counter()
                    enriched = self.narrator.enrich_image_prompt(
                        img_request["base_prompt"],
                        img_request["context"],
                    )
                    if self._perf:
                        self._perf.record_llm(time.perf_counter() - _t0_img, "enrich_image")
                    if generation == self._match_generation:
                        with self._image_prompt_lock:
                            self._pending_image_prompt = (
                                enriched,
                                img_request["negative_prompt"],
                            )
                            self._pending_image_prompt_generation = generation
                        if self._log_fn:
                            self._log_fn(
                                "IMAGEGEN",
                                f"Prompt enriquecido: {enriched[:80]}...",
                            )
            except Empty:
                pass

    def _process_question_request(self, request: dict[str, Any]) -> str | None:
        """
        Procesa una peticion de pregunta (reformulacion o generacion nueva).

        Para generacion nueva, el narrador devuelve (pregunta, emocion).
        La emocion se guarda aparte para que Game la consuma.

        Args:
            request: Diccionario con el tipo de peticion y datos.

        Returns:
            String con la pregunta generada, o None si falla.
        """
        if request["type"] == "reformulate":
            _t0 = time.perf_counter()
            text = self.narrator.reformulate_question(request["original"])
            if self._perf:
                self._perf.record_llm(time.perf_counter() - _t0, "reformulate")
            return text
        elif request["type"] == "generate":
            _t0 = time.perf_counter()
            result = self.narrator.generate_question(
                request["dialogue_summary"],
                request["game_state"],
            )
            if self._perf:
                self._perf.record_llm(time.perf_counter() - _t0, "generate_question")
            # generate_question devuelve (pregunta, emocion)
            question_text, emotion = result
            generation = request.get("match_generation", self._match_generation)
            if emotion is not None:
                with self._emotion_lock:
                    self._pending_emotion = emotion
                    self._pending_emotion_generation = generation
                if self._log_fn:
                    self._log_fn(
                        "EMOCION",
                        f"[{emotion.mood_tag}] agr={emotion.aggressiveness:.2f} "
                        f"est={emotion.stability:.2f} mot={emotion.motivation:.2f}",
                    )
            return question_text
        return None

    # --------------------------------------------------------
    # Construccion y publicacion de payloads
    # --------------------------------------------------------

    def build_game_state(self, event_label: str, score: ScoreState, ball: Ball,
                         rally_hits: int, last_play: str,
                         elapsed_seconds: float,
                         event_data: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Construye el diccionario de estado del juego para el narrador.

        Reune toda la informacion que el narrador necesita en un solo
        diccionario. Esto incluye marcador, posicion de la pelota,
        tiempo transcurrido, y datos del evento (quien anoto, etc.).

        Args:
            event_label:      Tipo de evento.
            score:            ScoreState con el marcador.
            ball:             Ball con posicion y velocidad.
            rally_hits:       Toques de pelota en el rally actual.
            last_play:        Texto de la ultima jugada.
            elapsed_seconds:  Segundos desde el inicio del partido.
            event_data:       Datos adicionales del evento (PointResult, etc.).

        Returns:
            Diccionario con todo el estado del juego.
        """
        game_state = {
            "event_label": event_label,
            "last_play": last_play,
            "player_score": score.player_points,
            "computer_score": score.computer_points,
            "player_point_streak": score.player_point_streak,
            "computer_point_streak": score.computer_point_streak,
            "player_games": score.player_games,
            "computer_games": score.computer_games,
            "player_sets": score.player_sets,
            "computer_sets": score.computer_sets,
            "scoreboard": score.scoreboard_text(),
            "ball_x": ball.rect.centerx,
            "ball_y": ball.rect.centery,
            "ball_speed_x": ball.speed_x,
            "ball_speed_y": ball.speed_y,
            "rally_hits": rally_hits,
            "elapsed_seconds": elapsed_seconds,
            "point_won": False,
            "game_won": False,
            "set_won": False,
            "match_won": False,
            "scoring_player": "",
            "scoring_streak": 0,
        }
        if event_data:
            game_state.update(event_data)
        return game_state

    def _build_payload(self, game_state: dict[str, Any], text: str) -> dict[str, Any]:
        """
        Construye el payload de narracion para el log y el HUD.

        Args:
            game_state: Diccionario con el estado del juego.
            text:       Texto de narracion generado.

        Returns:
            Diccionario con toda la informacion de la narracion.
        """
        return {
            "request_id": game_state.get("request_id", 0),
            "priority": game_state.get("priority", False),
            "match_generation": game_state.get("match_generation", 0),
            "text": text,
            "event_label": game_state["event_label"],
            "elapsed_seconds": game_state["elapsed_seconds"],
            "player_score": game_state["player_score"],
            "computer_score": game_state["computer_score"],
            "player_point_streak": game_state["player_point_streak"],
            "computer_point_streak": game_state["computer_point_streak"],
            "player_games": game_state["player_games"],
            "computer_games": game_state["computer_games"],
            "player_sets": game_state["player_sets"],
            "computer_sets": game_state["computer_sets"],
            "scoreboard": game_state["scoreboard"],
            "point_won": game_state["point_won"],
            "game_won": game_state["game_won"],
            "set_won": game_state["set_won"],
            "match_won": game_state["match_won"],
            "scoring_player": game_state["scoring_player"],
            "memory_snapshot": list(self.narrator.memory),
        }

    def _publish(self, payload: dict[str, Any]) -> None:
        """
        Incorpora la narracion al texto visible y al historial.

        Args:
            payload: Diccionario con la narracion y metadatos.
        """
        text = payload["text"]
        self.narration_text = text
        self.narration_log.append(payload)
        if self._log_fn:
            self._log_fn("LLM", f"({payload['event_label']}) \"{text}\"")

    @staticmethod
    def _is_scoring_event(game_state: dict[str, Any]) -> bool:
        """
        Indica si el evento es de puntuacion (punto, juego, set o partido).

        Los eventos de puntuacion reciben tratamiento especial: se publica
        un texto de respaldo instantaneo sin esperar al LLM.

        Args:
            game_state: Diccionario con el estado del juego.

        Returns:
            True si es un evento de puntuacion.
        """
        return bool(
            game_state.get("point_won")
            or game_state.get("game_won")
            or game_state.get("set_won")
            or game_state.get("match_won")
        )
