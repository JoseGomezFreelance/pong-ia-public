"""
pong/narrator.py -- Narrador deportivo con IA local.

Este modulo usa un proveedor de LLM (LLMProviderProtocol) para generar
comentarios en espanol como si fuera un narrador deportivo de television.

Si el proveedor no esta disponible, el narrador usa frases de respaldo
pre-escritas para que el juego siempre tenga narracion.

Contiene:
- LocalNarrator: la clase que genera los comentarios.

Los metodos de generacion de preguntas y resumen de partido estan en
mixins separados para mantener este archivo enfocado en la narracion
en tiempo real:
- narrator_questions.py → NarratorQuestionsMixin
- narrator_summary.py → NarratorSummaryMixin
"""

from __future__ import annotations

import logging
import random
import re
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)

from pong.exceptions import LLMInferenceError

from pong.narrator_questions import NarratorQuestionsMixin
from pong.narrator_summary import NarratorSummaryMixin


# ============================================================
# NARRADOR LOCAL
# ============================================================

class LocalNarrator(NarratorQuestionsMixin, NarratorSummaryMixin):
    """
    Genera comentarios deportivos usando un proveedor de LLM.

    El narrador recibe el estado del juego (quien anoto, marcador, rally...)
    y produce una frase corta en espanol, como un comentarista de TV.

    La inferencia se delega a un ``LLMProviderProtocol``, lo que permite
    cambiar de modelo (Qwen, Llama, Mistral...) sin modificar este codigo.

    El narrador tiene "memoria" de sus ultimas 10 frases para no repetirse
    y rota entre 8 estilos de narracion para dar variedad.

    Atributos:
        enabled:        True si el proveedor LLM esta operativo.
        _llm:           Proveedor de inferencia LLM.
        memory:         Cola de las ultimas 10 narraciones para evitar repeticion.
        status_message: Texto que describe el estado del narrador para logs.
    """

    def __init__(self, llm: Any) -> None:
        """
        Inicializa el narrador con un proveedor de LLM.

        Args:
            llm: Objeto que cumple ``LLMProviderProtocol``.
        """
        self._llm = llm
        self.enabled: bool = llm.enabled
        self.memory: deque[dict[str, str]] = deque(maxlen=10)
        self.status_message: str = llm.status_message

    def reload_llm(self) -> None:
        """Re-intenta cargar el LLM y sincroniza el estado."""
        self._llm.reload()
        self.enabled = self._llm.enabled
        self.status_message = self._llm.status_message

    # --------------------------------------------------------
    # Metodo principal: generar narracion
    # --------------------------------------------------------

    def commentate(self, game_state: dict[str, Any]) -> str:
        """
        Genera una narracion corta para el estado actual del juego.

        Flujo:
        1. Prepara una frase de respaldo por si el LLM falla.
        2. Si el LLM esta activo, construye el prompt y genera texto.
        3. Limpia y valida el texto generado (_polish_commentary).
        4. Comprueba que no sea demasiado similar a frases recientes.
        5. Guarda la frase en memoria para futuras comparaciones.

        Args:
            game_state: Diccionario con el estado del juego (ver _build_game_state
                        en narration_bridge.py).

        Returns:
            String con la frase de narracion.
        """
        fallback = self._fallback_line(game_state)

        if not self.enabled:
            self._remember_turn(game_state, fallback)
            return fallback

        # --- Construir el prompt para el LLM ---
        history_context = self._format_memory()
        event_focus = self._event_focus(game_state)
        style_hint = self._pick_style_hint()
        dialogue_essence = game_state.get("dialogue_essence", "")

        system_prompt = (
            "Comenta partidos de Pong en espanol como narrador deportivo. "
            "Genera UNA sola frase de 8 a 18 palabras. "
            f"{style_hint} "
        )
        if dialogue_essence:
            system_prompt += (
                "Estas en dialogo con el jugador. "
                "Puedes hacer guinos sutiles a lo que el jugador ha dicho. "
            )
        system_prompt += (
            "Prohibido: inventar resultados, repetir frases anteriores, "
            "usar la palabra Foco, usar coordenadas o datos tecnicos."
        )
        prompt = (
            f"AHORA MISMO: {event_focus}\n"
            f"Jugada: {game_state['last_play']}\n"
            f"Marcador: {game_state['scoreboard']}\n"
            f"Rally: {game_state['rally_hits']} toques\n"
        )
        if dialogue_essence:
            prompt += f"Dialogo con jugador: {dialogue_essence}\n"
        prompt += (
            f"---\n"
            f"Anteriores (NO repetir):\n{history_context}\n"
            f"---\n"
            f"Narra lo de AHORA MISMO en una frase."
        )

        # --- Llamar al LLM ---
        try:
            response = self._llm.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=64,
                temperature=0.85,
                top_p=0.92,
                repeat_penalty=1.18,
                frequency_penalty=0.15,
            )
            content = response["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            err = LLMInferenceError(f"narracion LLM: {exc}")
            err.__cause__ = exc
            logger.error("%s", err, exc_info=True)
            content = ""

        # --- Limpiar y validar la respuesta ---
        narration = self._polish_commentary(content, game_state, fallback)
        if self._is_too_similar(narration) and narration != fallback:
            narration = fallback
        self._remember_turn(game_state, narration)
        return narration

    # --------------------------------------------------------
    # Memoria y contexto
    # --------------------------------------------------------

    def _format_memory(self) -> str:
        """
        Formatea las ultimas 3 narraciones como contexto para el prompt.

        Solo incluye el tipo de evento y el marcador (NO la narracion en si)
        para evitar que el LLM copie frases anteriores.

        Returns:
            String con el historial formateado, o "(vacio)" si no hay memoria.
        """
        if not self.memory:
            return "(vacio)"
        recent_turns = list(self.memory)[-3:]
        lines = []
        for turn in recent_turns:
            lines.append(f"- {turn['event_label']}: {turn['scoreboard']}")
        return "\n".join(lines)

    def _remember_turn(self, game_state: dict[str, Any], narration: str) -> None:
        """
        Guarda un resumen del turno actual en la memoria del narrador.

        Esta memoria sirve para dos cosas:
        1. Dar contexto al LLM en futuras peticiones.
        2. Detectar si una nueva narracion es demasiado similar a las recientes.

        Args:
            game_state: Estado del juego en este momento.
            narration:  La frase que se genero para este turno.
        """
        self.memory.append(
            {
                "event_label": game_state["event_label"],
                "last_play": game_state["last_play"],
                "scoreboard": game_state["scoreboard"],
                "narration": narration,
            }
        )

    # --------------------------------------------------------
    # Generacion de foco del evento (guia para el LLM)
    # --------------------------------------------------------

    def _event_focus(self, game_state: dict[str, Any]) -> str:
        """
        Resume el evento actual con variedad para guiar al modelo.

        En vez de darle al LLM un texto generico, le decimos exactamente
        que esta pasando con varias formulaciones posibles (elegidas al azar)
        para que sus respuestas tambien varien.

        Args:
            game_state: Diccionario con el estado del juego.

        Returns:
            String describiendo el evento actual.
        """
        scorer = self._display_actor(game_state.get("scoring_player"))
        rally = game_state.get("rally_hits", 0)

        if game_state.get("match_won"):
            return random.choice([
                f"{scorer} gano el partido completo.",
                f"Fin del partido, victoria de {scorer}.",
                f"Partido terminado. {scorer} se lleva la victoria.",
            ])
        if game_state.get("set_won"):
            return random.choice([
                f"{scorer} cerro el set.",
                f"Set ganado por {scorer}.",
                f"{scorer} se lleva este set decisivo.",
            ])
        if game_state.get("game_won"):
            return random.choice([
                f"Juego para {scorer}.",
                f"{scorer} gana el juego.",
                f"{scorer} cierra este juego.",
            ])
        if game_state.get("point_won"):
            streak = game_state.get("scoring_streak", 1)
            if streak >= 3:
                return random.choice([
                    f"Punto de {scorer}, lleva {streak} seguidos.",
                    f"{scorer} anota de nuevo, racha de {streak}.",
                    f"Otro punto de {scorer}, van {streak} consecutivos.",
                ])
            return random.choice([
                f"Punto para {scorer}.",
                f"{scorer} anota.",
                f"{scorer} se lleva el punto.",
                f"Punto de {scorer} en este intercambio.",
            ])
        if rally >= 8:
            return random.choice([
                f"Peloteo intenso, ya van {rally} toques sin punto.",
                f"Rally largo de {rally} toques, nadie cede.",
                f"Intercambio de {rally} golpes, mucha tension.",
            ])
        if rally >= 4:
            return random.choice([
                f"Peloteo activo con {rally} toques.",
                f"Rally de {rally} toques en desarrollo.",
                f"Van {rally} toques en este intercambio.",
            ])
        return random.choice([
            "La pelota esta en juego, nadie anoto.",
            "Juego en curso, sin puntos todavia.",
            "Sigue el intercambio, ambos resisten.",
        ])

    # --------------------------------------------------------
    # Frases de respaldo (cuando el LLM no esta disponible)
    # --------------------------------------------------------

    def _fallback_line(self, game_state: dict[str, Any]) -> str:
        """
        Genera una frase de respaldo pre-escrita para el evento actual.

        Estas frases se usan cuando:
        - El modelo LLM no esta instalado.
        - El modelo falla al generar texto.
        - Se necesita respuesta instantanea (eventos de puntuacion).

        Cada tipo de evento tiene varias opciones para dar variedad.

        Args:
            game_state: Diccionario con el estado del juego.

        Returns:
            String con una frase de narracion de respaldo.
        """
        scorer = self._display_actor(game_state.get("scoring_player"))
        rally = game_state.get("rally_hits", 0)
        if game_state.get("match_won"):
            return random.choice([
                f"\u00a1Partido para {scorer}! Supo sostener la presi\u00f3n en el cierre.",
                f"\u00a1Se acab\u00f3! {scorer} se lleva el partido completo.",
                f"\u00a1Victoria definitiva de {scorer} en este partido!",
            ])
        if game_state.get("set_won"):
            return random.choice([
                f"\u00a1Set para {scorer}! Fue m\u00e1s s\u00f3lido en los puntos decisivos.",
                f"\u00a1{scorer} cierra el set con autoridad!",
                f"\u00a1Gran cierre de set por parte de {scorer}!",
            ])
        if game_state.get("game_won"):
            return random.choice([
                f"Juego para {scorer}; este tramo cambia el pulso del partido.",
                f"\u00a1{scorer} se lleva el juego con determinaci\u00f3n!",
                f"Juego cerrado por {scorer}, sigue sumando.",
            ])
        if game_state.get("point_won"):
            streak = game_state.get("scoring_streak", 1)
            if streak >= 3:
                return random.choice([
                    f"\u00a1Punto para {scorer}! Encadena una racha que pesa en el marcador.",
                    f"\u00a1Otro punto de {scorer}! Van {streak} seguidos, impresionante.",
                    f"\u00a1{scorer} no para, ya son {streak} puntos consecutivos!",
                ])
            if streak == 2:
                return random.choice([
                    f"\u00a1Otro punto para {scorer}! Empieza a inclinar este juego.",
                    f"\u00a1{scorer} repite y ya son dos seguidos!",
                ])
            if rally >= 4:
                return random.choice([
                    f"\u00a1Punto para {scorer} tras un intercambio exigente!",
                    f"\u00a1{scorer} se lleva el punto despu\u00e9s de {rally} toques!",
                ])
            return random.choice([
                f"\u00a1Punto para {scorer}, golpe oportuno en el momento justo!",
                f"\u00a1{scorer} anota con precisi\u00f3n!",
                f"\u00a1Buen punto de {scorer}!",
            ])
        if game_state.get("event_label") == "inicio":
            return random.choice([
                "Comienza el duelo. Ritmo alto desde el primer saque.",
                "Arranca el partido, todo por decidirse.",
                "Primer saque del encuentro, comienza la acci\u00f3n.",
            ])
        if rally >= 5:
            return random.choice([
                "Intercambio largo y tenso; nadie regala un cent\u00edmetro.",
                f"Van {rally} toques en este rally, qu\u00e9 intensidad.",
                "Peloteo sostenido, ninguno de los dos cede.",
            ])
        return random.choice([
            "El partido sigue abierto; cada devoluci\u00f3n empieza a tener m\u00e1s peso.",
            "Sigue el intercambio, la tensi\u00f3n no baja.",
            "Ambos lados se mantienen firmes en este tramo.",
        ])

    # --------------------------------------------------------
    # Validacion y limpieza del texto generado por el LLM
    # --------------------------------------------------------

    # Patrones de palabras que el LLM a veces "filtra" del prompt y no deberian
    # aparecer en la narracion final.
    _BANNED_PATTERNS = re.compile(
        r"\b(foco|narrativo|ahora\s+mismo|AHORA|intercambio\s+actual)\b",
        re.IGNORECASE,
    )

    # Palabras que indican que el LLM esta hablando de puntuacion.
    # Se usan para detectar "alucinaciones" (dice que alguien anoto cuando no fue asi).
    _SCORING_WORDS = re.compile(
        r"\b(gana|anota|punto\s+para|marca|se\s+lleva\s+el\s+punto|"
        r"cerr[o\u00f3]\s+el\s+set|gan[o\u00f3]\s+el\s+partido|gan[o\u00f3]\s+el\s+juego)\b",
        re.IGNORECASE,
    )

    def _polish_commentary(self, raw_text: str, game_state: dict[str, Any], fallback: str) -> str:
        """
        Limpia y valida la salida del modelo LLM.

        El LLM a veces genera texto con problemas: palabras del prompt que se
        filtran, datos tecnicos, afirmaciones falsas sobre el marcador, o frases
        demasiado cortas/largas. Esta funcion aplica 7 filtros en cadena para
        garantizar una frase limpia y factualmente correcta.

        Si el texto no pasa alguna validacion, se devuelve la frase de respaldo.

        Args:
            raw_text:   Texto crudo del LLM.
            game_state: Estado del juego (para validar hechos).
            fallback:   Frase de respaldo si la validacion falla.

        Returns:
            String con la narracion limpia, o el fallback.
        """
        cleaned = " ".join((raw_text or "").replace("\n", " ").split())
        cleaned = cleaned.strip(" \"'`")
        if not cleaned:
            return fallback

        # 1. Eliminar palabras prohibidas que se filtraron del prompt
        cleaned = self._BANNED_PATTERNS.sub("", cleaned)
        cleaned = " ".join(cleaned.split())

        # 2. Eliminar datos tecnicos (coordenadas, nombres de variables)
        cleaned = re.sub(
            r"\b[xy]=-?\d+(?:\.\d+)?\b", "", cleaned, flags=re.IGNORECASE
        )
        cleaned = re.sub(
            r"\b(velocidad|ball_[a-z_]+|rally_hits|centerx|centery)\b",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = " ".join(cleaned.split())
        if not cleaned:
            return fallback

        # 3. Guardia factual: no hablar de puntos durante un rally
        is_rally_event = (
            not game_state.get("point_won")
            and not game_state.get("game_won")
            and not game_state.get("set_won")
            and not game_state.get("match_won")
        )
        if is_rally_event and self._SCORING_WORDS.search(cleaned):
            return fallback

        # 4. Guardia factual: no atribuir puntos al jugador equivocado
        if game_state.get("point_won"):
            scoring_player = game_state.get("scoring_player", "")
            if scoring_player == "jugador":
                if re.search(
                    r"\b(ordenador|maquina|CPU|rival)\b.*\b(gana|anota|marca|punto)\b",
                    cleaned,
                    re.IGNORECASE,
                ) or re.search(
                    r"\b(gana|anota|marca|punto)\b.*\b(ordenador|maquina|CPU|rival)\b",
                    cleaned,
                    re.IGNORECASE,
                ):
                    return fallback
            elif scoring_player == "ordenador":
                if re.search(
                    r"\b(jugador|humano)\b.*\b(gana|anota|marca|punto)\b",
                    cleaned,
                    re.IGNORECASE,
                ) or re.search(
                    r"\b(gana|anota|marca|punto)\b.*\b(jugador|humano)\b",
                    cleaned,
                    re.IGNORECASE,
                ):
                    return fallback

        # 5. Verificar longitud (minimo 4 palabras, maximo 22)
        words = cleaned.split()
        if len(words) < 4:
            return fallback
        if len(words) > 22:
            cleaned = " ".join(words[:22]).rstrip(",;:")

        # 6. Completar la frase con puntuacion adecuada
        if not cleaned.endswith((".", "!", "?")):
            last_break = max(
                cleaned.rfind("."), cleaned.rfind("!"), cleaned.rfind("?")
            )
            if last_break > len(cleaned) * 0.5:
                cleaned = cleaned[: last_break + 1]
            elif game_state.get("point_won"):
                cleaned = cleaned.rstrip(".,;:") + "!"
            else:
                cleaned += "."

        # 7. Asegurar enfasis en eventos de puntuacion (terminar con !)
        if game_state.get("point_won") and not cleaned.endswith(("!", "?")):
            cleaned = cleaned.rstrip(".") + "!"

        return cleaned

    # --------------------------------------------------------
    # Utilidades
    # --------------------------------------------------------

    def _display_actor(self, actor: str | None) -> str:
        """
        Normaliza el identificador del actor para mostrarlo bonito.

        Convierte "jugador" → "el Jugador" y "ordenador" → "el Ordenador"
        para que las frases de narracion suenen naturales en espanol.

        Args:
            actor: "jugador", "ordenador" o None.

        Returns:
            String con el nombre formateado para narracion.
        """
        if actor == "jugador":
            return "el Jugador"
        if actor == "ordenador":
            return "el Ordenador"
        return "el lado atacante"

    def _truncate_words(self, text: str, max_words: int) -> str:
        """
        Recorta una frase a un maximo de palabras.

        Args:
            text:      Texto a recortar.
            max_words: Numero maximo de palabras.

        Returns:
            Texto recortado (o el original si ya es suficientemente corto).
        """
        words = text.split()
        if len(words) <= max_words:
            return text
        return " ".join(words[:max_words])

    # Estilos de narracion que se rotan para dar variedad al LLM.
    # Cada estilo cambia el tono de la frase generada.
    _STYLE_HINTS = [
        "Usa tono emocionado.",
        "Usa tono analitico.",
        "Narra con suspenso.",
        "Se breve y directo.",
        "Comenta con energia.",
        "Habla del ritmo de juego.",
        "Menciona la presion del momento.",
        "Destaca la habilidad mostrada.",
    ]

    def _pick_style_hint(self) -> str:
        """
        Selecciona un estilo de narracion aleatorio.

        Se inyecta en el prompt del sistema para que el LLM varie
        el tono de sus respuestas entre "emocionado", "analitico",
        "con suspenso", etc.

        Returns:
            String con la directriz de estilo (ej: "Usa tono emocionado.").
        """
        return random.choice(self._STYLE_HINTS)

    def _is_too_similar(self, new_text: str) -> bool:
        """
        Comprueba si una narracion es demasiado parecida a las recientes.

        Compara las palabras del texto nuevo con las de las ultimas 3
        narraciones. Si mas del 60% de las palabras coinciden, se
        considera "demasiado similar" y se rechaza.

        Args:
            new_text: La narracion candidata a publicar.

        Returns:
            True si es demasiado similar, False si es aceptable.
        """
        if not self.memory:
            return False
        new_words = set(new_text.lower().split())
        for turn in list(self.memory)[-3:]:
            old_words = set(turn["narration"].lower().split())
            if not new_words or not old_words:
                continue
            overlap = len(new_words & old_words) / max(len(new_words), 1)
            if overlap > 0.6:
                return True
        return False
