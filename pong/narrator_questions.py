"""
pong/narrator_questions.py -- Mixin de generacion de preguntas.

Contiene los metodos de generacion de preguntas Si/No para el jugador,
incluyendo extraccion de dialogo, deteccion de similitud, arcos
conversacionales y preguntas de respaldo.
"""

from __future__ import annotations

import logging
import random
import re
from difflib import SequenceMatcher
from typing import Any, TYPE_CHECKING

logger = logging.getLogger(__name__)

from pong.exceptions import LLMInferenceError

if TYPE_CHECKING:
    from pong.emotional_state import EmotionalState


class NarratorQuestionsMixin:
    """Mixin: generacion de preguntas y analisis de dialogo."""

    # -- Atributos declarados en LocalNarrator, visibles aquí para mypy --
    enabled: bool
    _llm: Any

    def _truncate_words(self, text: str, max_words: int) -> str:
        raise NotImplementedError  # Provided by LocalNarrator

    def generate_question(self, dialogue_summary: str, game_state: dict[str, Any]) -> tuple[str, EmotionalState | None]:
        """
        Genera una nueva pregunta basada en el dialogo previo y el estado del juego.

        El LLM crea una pregunta coherente con la conversacion anterior,
        lo que esta pasando en el partido, y el marcador actual. La pregunta
        debe ser de tipo Si/No para que el jugador pueda responder con la paleta.

        Ademas del texto de la pregunta, el LLM emite un perfil emocional
        (agresividad, estabilidad, motivacion) que modula el comportamiento
        de la paleta del ordenador.

        Args:
            dialogue_summary: Resumen formateado del dialogo previo.
            game_state:       Diccionario con el estado del juego.

        Returns:
            Tupla (pregunta: str, emocion: EmotionalState | None).
            Si el LLM falla, devuelve (fallback, None).
        """
        recent_turns = self._extract_recent_dialogue(dialogue_summary, game_state)
        recent_questions = [turn["question"] for turn in recent_turns if turn["question"]]
        fallback = self._fallback_question(game_state, recent_turns)

        if not self.enabled:
            return fallback, None

        scoreboard = game_state.get("scoreboard", "desconocido")
        elapsed = game_state.get("elapsed_seconds", 0)
        elapsed_min = int(elapsed) // 60
        rally = game_state.get("rally_hits", 0)
        question_count = int(game_state.get("question_count", len(recent_turns)))
        last_answer = (
            recent_turns[-1]["answer"] if recent_turns else "Duda"
        )
        arc_hint = self._conversation_arc_hint(question_count)
        reaction_hint = self._reaction_hint(last_answer)
        banned_keywords = self._question_keywords(recent_questions)
        banned_keywords_text = ", ".join(banned_keywords) if banned_keywords else "(ninguna)"
        dialogue_prompt = self._format_recent_dialogue_for_prompt(recent_turns)
        answer_profile = self._answer_profile(recent_turns)

        attempt_hints = [
            "Cambia de angulo frente a la ultima pregunta.",
            "Hazla mas emocional y personal.",
            "Hazla sorprendente o provocadora.",
        ]

        for attempt, attempt_hint in enumerate(attempt_hints):
            system_prompt = (
                "Eres un narrador de Pong que conversa con el jugador. "
                "Genera UNA pregunta de Si/No en espanol (8-20 palabras). "
                "REGLA CLAVE: cada pregunta debe explorar un TEMA DISTINTO "
                "a todas las anteriores.\n"
                "Responde SOLO con JSON valido (sin texto extra):\n"
                '{"pregunta":"...","emocion":{"agresividad":0.5,"estabilidad":0.8,'
                '"motivacion":0.7,"humor":"neutral"}}\n'
                "Guia para emocion (valores 0.0-1.0):\n"
                "- Conversacion tensa/competitiva: agresividad 0.7-1.0, estabilidad alta\n"
                "- Conversacion relajada/amigable: agresividad 0.2-0.4, estabilidad alta\n"
                "- Jugador deprimido/resignado: motivacion 0.0-0.3\n"
                "- Conversacion caotica/absurda: estabilidad 0.0-0.3\n"
                "- Jugador provocador: agresividad alta, motivacion alta\n"
                "- humor: tenso/relajado/deprimido/euforico/erratico/furioso/neutral"
            )
            prompt = (
                f"Conversacion hasta ahora:\n{dialogue_prompt}\n"
                f"---\n"
                f"Perfil de respuestas: {answer_profile}\n"
                f"El jugador acaba de responder: {last_answer}\n"
                f"Reaccion: {reaction_hint}\n"
                f"---\n"
                f"Contexto del partido: {scoreboard}, rally {rally}, "
                f"minuto {elapsed_min}\n"
                f"---\n"
                f"TEMA OBLIGATORIO para esta pregunta: {arc_hint}\n"
                f"Terminos prohibidos (ya usados): {banned_keywords_text}\n"
                f"{attempt_hint}\n"
                f"Genera el JSON:"
            )

            try:
                response = self._llm.chat_completion(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=120,
                    temperature=0.88 + (attempt * 0.08),
                    top_p=0.92,
                    repeat_penalty=1.2,
                    frequency_penalty=0.2,
                )
                content = response["choices"][0]["message"]["content"].strip()

                # Intentar parsear JSON con emocion
                from pong.emotional_state import (
                    parse_emotion_from_llm,
                    parse_question_from_llm,
                )

                question_text = parse_question_from_llm(content)
                emotion = parse_emotion_from_llm(content)

                if question_text:
                    candidate = self._polish_question(question_text, fallback)
                else:
                    # El LLM no devolvio JSON valido; usar texto bruto
                    candidate = self._polish_question(content, fallback)

                if not self._is_question_too_similar(candidate, recent_questions):
                    return candidate, emotion
            except Exception as exc:
                err = LLMInferenceError(f"generando pregunta: {exc}")
                err.__cause__ = exc
                logger.error("%s", err, exc_info=True)

        return fallback, None

    def _extract_recent_dialogue(self, dialogue_summary: str, game_state: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Extrae los ultimos turnos de dialogo desde game_state o resumen plano.

        Args:
            dialogue_summary: Texto con preguntas/respuestas previas.
            game_state: Estado del juego (puede traer turns estructurados).

        Returns:
            Lista normalizada de turnos [{question, answer, elapsed_seconds}].
        """
        turns = []
        raw_turns = game_state.get("dialogue_turns")
        if isinstance(raw_turns, list):
            for raw_turn in raw_turns:
                if not isinstance(raw_turn, dict):
                    continue
                question = str(raw_turn.get("question", "")).strip()
                if not question:
                    continue
                turns.append(
                    {
                        "question": question,
                        "answer": self._normalize_answer(raw_turn.get("answer")),
                        "elapsed_seconds": int(raw_turn.get("elapsed_seconds", 0)),
                    }
                )
        if turns:
            return turns
        return self._parse_dialogue_summary(dialogue_summary)

    def _parse_dialogue_summary(self, dialogue_summary: str) -> list[dict[str, Any]]:
        """
        Parsea el resumen de dialogo para recuperar turnos estructurados.

        Args:
            dialogue_summary: Texto de salida de QuestionSystem.get_dialogue_summary().

        Returns:
            Lista de turnos normalizados.
        """
        if not dialogue_summary or dialogue_summary.strip() == "(sin dialogo previo)":
            return []

        turns = []
        current: dict[str, str] = {}
        for raw_line in dialogue_summary.splitlines():
            line = raw_line.strip()
            q_match = re.match(r"^\d+\.\s*Pregunta:\s*(.+)$", line, re.IGNORECASE)
            if q_match:
                if current.get("question"):
                    turns.append(
                        {
                            "question": current["question"],
                            "answer": self._normalize_answer(current.get("answer")),
                            "elapsed_seconds": 0,
                        }
                    )
                current = {"question": q_match.group(1).strip(), "answer": "Duda"}
                continue

            a_match = re.match(
                r"^Respuesta del jugador:\s*(.+)$", line, re.IGNORECASE
            )
            if a_match and current:
                current["answer"] = a_match.group(1).strip()

        if current.get("question"):
            turns.append(
                {
                    "question": current["question"],
                    "answer": self._normalize_answer(current.get("answer")),
                    "elapsed_seconds": 0,
                }
            )
        return turns

    def _normalize_answer(self, answer: Any) -> str:
        """
        Normaliza respuestas del jugador a Si/No/Duda.
        """
        normalized = str(answer or "").strip().lower()
        if normalized.startswith("s"):
            return "Si"
        if normalized.startswith("n"):
            return "No"
        return "Duda"

    def _answer_profile(self, recent_turns: list[dict[str, Any]]) -> str:
        """
        Resume tendencia de respuestas para usarla como contexto del prompt.
        """
        if not recent_turns:
            return "sin respuestas previas"
        answers = [turn["answer"] for turn in recent_turns]
        total = len(answers)
        yes = answers.count("Si")
        no = answers.count("No")
        doubt = answers.count("Duda")
        last = answers[-1]
        return (
            f"Si={yes}/{total}, No={no}/{total}, Duda={doubt}/{total}, "
            f"ultima={last}"
        )

    # Arcos tematicos por profundidad de conversacion.
    # Cada pregunta explora un tema distinto segun cuantas preguntas se han hecho.
    _CONVERSATION_ARCS = {
        1: [
            "primera impresion personal sobre el rival",
            "sensacion al empezar el partido",
        ],
        2: [
            "consecuencia de lo que acaba de responder",
            "cambio de perspectiva: de lo tactico a lo emocional o viceversa",
        ],
        3: [
            "contradiccion entre lo que dice y lo que muestra el marcador",
            "pregunta sobre el rival en vez de sobre si mismo",
        ],
        "late": [
            "leccion que se lleva de este partido",
            "si cambiaria algo de lo que ha hecho",
            "que le diria a su rival ahora mismo",
            "si el partido revela algo sobre como toma decisiones",
            "momento del partido que mas le ha marcado",
        ],
    }

    def _conversation_arc_hint(self, question_count: int) -> str:
        """
        Selecciona un arco tematico segun la profundidad de la conversacion.

        Args:
            question_count: Numero de preguntas ya realizadas.

        Returns:
            String con el tema sugerido para la siguiente pregunta.
        """
        bucket = self._CONVERSATION_ARCS.get(
            question_count, self._CONVERSATION_ARCS["late"]
        )
        return random.choice(bucket)

    def _reaction_hint(self, last_answer: str) -> str:
        """
        Traduce la ultima respuesta en instruccion de continuidad conversacional.
        """
        if last_answer == "Si":
            return "profundiza la idea con una decision concreta de juego"
        if last_answer == "No":
            return "abre una hipotesis distinta sin repetir la pregunta anterior"
        return "formula una pregunta de claridad para forzar posicion"

    def _format_recent_dialogue_for_prompt(self, recent_turns: list[dict[str, Any]]) -> str:
        """
        Formatea dialogo reciente en una sola cadena compacta.
        """
        if not recent_turns:
            return "(sin dialogo previo)"
        lines = []
        for idx, turn in enumerate(recent_turns, start=1):
            second = int(turn.get("elapsed_seconds", 0))
            lines.append(
                f"{idx}) [{second}s] P: {turn['question']} | R: {turn['answer']}"
            )
        return "\n".join(lines)

    _QUESTION_STOPWORDS = {
        "que", "como", "este", "esta", "esto", "esa", "ese", "aqui", "ahora",
        "momento", "punto", "juego", "partido", "puede", "podria", "crees",
        "sientes", "piensas", "consideras", "ser", "del", "las", "los", "una",
        "uno", "con", "sin", "para", "sobre", "mas", "menos", "cada", "hasta",
        "tiene", "tengo", "tienes", "este", "ese", "tu", "te", "se", "el", "la",
        "si", "no", "duda", "podrias", "deberias", "deberia",
    }

    def _question_keywords(self, questions: list[str]) -> list[str]:
        """
        Extrae terminos relevantes de TODAS las preguntas para evitar repeticiones.
        """
        if not questions:
            return []
        counts: dict[str, int] = {}
        for question in questions:
            for token in self._question_tokens(question):
                counts[token] = counts.get(token, 0) + 1
        sorted_terms = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return [term for term, _ in sorted_terms[:12]]

    def _question_tokens(self, question: str) -> set[str]:
        """
        Tokeniza una pregunta en palabras utiles para comparacion semantica.
        """
        normalized = self._normalize_question_text(question)
        tokens = re.findall(r"[a-z0-9]+", normalized)
        return {
            token for token in tokens
            if len(token) >= 4 and token not in self._QUESTION_STOPWORDS
        }

    def _normalize_question_text(self, question: str) -> str:
        """
        Normaliza texto de pregunta para comparaciones de similitud.
        """
        cleaned = " ".join(str(question or "").lower().replace("\n", " ").split())
        trans_table: dict[int, str | None] = {
            ord("\u00e1"): "a",
            ord("\u00e9"): "e",
            ord("\u00ed"): "i",
            ord("\u00f3"): "o",
            ord("\u00fa"): "u",
            ord("\u00fc"): "u",
            ord("\u00f1"): "n",
            ord("\u00bf"): None,
            ord("?"): None,
        }
        cleaned = cleaned.translate(trans_table)
        cleaned = re.sub(r"[^a-z0-9\s]", "", cleaned)
        return " ".join(cleaned.split())

    # Frases estructurales que producen preguntas repetitivas.
    # Si una frase ya aparecio en una pregunta anterior, se rechaza el candidato.
    _STRUCTURAL_BANS = [
        "punto ganado",
        "ritmo del rally",
        "cambiar el ritmo",
        "influir en el marcador",
        "proximo punto",
        "cambiar el marcador",
    ]

    def _is_question_too_similar(self, candidate: str, recent_questions: list[str]) -> bool:
        """
        Detecta si una nueva pregunta repite forma o contenido reciente.
        """
        if not candidate or not recent_questions:
            return False

        normalized_candidate = self._normalize_question_text(candidate)

        # Rechazar frases estructurales ya usadas en preguntas anteriores
        for ban in self._STRUCTURAL_BANS:
            if ban in normalized_candidate:
                for old_q in recent_questions:
                    if ban in self._normalize_question_text(old_q):
                        return True

        candidate_tokens = self._question_tokens(candidate)
        for old_question in recent_questions[-3:]:
            normalized_old = self._normalize_question_text(old_question)
            if normalized_candidate == normalized_old:
                return True

            ratio = SequenceMatcher(None, normalized_candidate, normalized_old).ratio()
            if ratio >= 0.72:
                return True

            old_tokens = self._question_tokens(old_question)
            if candidate_tokens and old_tokens:
                overlap = len(candidate_tokens & old_tokens) / max(
                    len(candidate_tokens | old_tokens), 1
                )
                if overlap >= 0.56:
                    return True
        return False

    def _polish_question(self, raw_text: str, fallback: str) -> str:
        """
        Limpia texto de pregunta generado por el modelo.
        """
        cleaned = " ".join((raw_text or "").replace("\n", " ").split())
        cleaned = cleaned.strip(" \"'`")
        if not cleaned:
            return fallback

        cleaned = re.sub(
            r"^(pregunta|respuesta|siguiente pregunta)\s*[:\-]\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"^[\-\*\d\.\)\s]+", "", cleaned)
        cleaned = cleaned.strip(" \"'`")
        if not cleaned:
            return fallback

        if "?" in cleaned:
            cleaned = cleaned[: cleaned.find("?") + 1]
        cleaned = cleaned.rstrip(".,!;:")
        if not cleaned.endswith("?"):
            cleaned += "?"

        word_count = len(cleaned.replace("?", "").split())
        if word_count < 8:
            return fallback
        if word_count > 20:
            trimmed = self._truncate_words(cleaned.replace("?", ""), 20)
            cleaned = trimmed.rstrip(".,!;:") + "?"
        return cleaned

    def _fallback_question(self, game_state: dict[str, Any], recent_turns: list[dict[str, Any]]) -> str:
        """
        Genera una pregunta contextual de respaldo evitando repetir recientes.
        """
        recent_questions = [turn["question"] for turn in recent_turns if turn["question"]]
        last_answer = recent_turns[-1]["answer"] if recent_turns else "Duda"
        player_points = int(game_state.get("player_score", 0))
        computer_points = int(game_state.get("computer_score", 0))
        player_streak = int(game_state.get("player_point_streak", 0))
        computer_streak = int(game_state.get("computer_point_streak", 0))
        rally_hits = int(game_state.get("rally_hits", 0))

        candidates = [
            "Ves necesario ajustar tu posicion para leer mejor el siguiente saque?",
            "Crees que conviene arriesgar mas con el primer golpe de este rally?",
            "Sientes que tu plan actual te da ventaja en este tramo del partido?",
        ]

        if abs(player_points - computer_points) <= 1:
            candidates.extend([
                "Con el marcador tan parejo, crees que el proximo punto marcara el ritmo?",
                "Te ves ganando este juego si sostienes la calma en los puntos largos?",
            ])

        if computer_streak >= 2:
            candidates.extend([
                "Crees que puedes cortar la racha del ordenador en este intercambio?",
                "Te conviene jugar mas seguro para frenar el impulso rival ahora?",
            ])
        elif player_streak >= 2:
            candidates.extend([
                "Crees que puedes mantener esta racha con la misma estrategia?",
                "Te ves cerrando este juego si sostienes la presion que llevas?",
            ])

        if rally_hits >= 6:
            candidates.extend([
                "Sientes que tienes paciencia suficiente para dominar otro rally largo?",
                "Crees que el desgaste del rally favorece mas tu lectura o la rival?",
            ])

        if last_answer == "Si":
            candidates.extend([
                "Con esa confianza, te animas a acelerar el ritmo del siguiente punto?",
                "Tras tu respuesta, crees que debes mantener la misma apuesta tactica?",
            ])
        elif last_answer == "No":
            candidates.extend([
                "Si no lo ves claro, crees que toca cambiar la estrategia de devolucion?",
                "Despues de ese No, prefieres un plan mas conservador para este juego?",
            ])
        else:
            candidates.extend([
                "Sigues con dudas o ya tienes claro donde atacar en este tramo?",
                "Crees que este punto te ayudara a definir mejor tu estrategia?",
            ])

        random.shuffle(candidates)
        for candidate in candidates:
            polished = self._polish_question(candidate, candidate)
            if not self._is_question_too_similar(polished, recent_questions):
                return polished
        return "Crees que necesitas cambiar algo para competir mejor este juego?"
