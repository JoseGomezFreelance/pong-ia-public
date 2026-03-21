"""
pong/narrator_summary.py -- Mixin de resumen de partido e imagen.

Contiene los metodos de generacion de resumen post-partido (normal
y streaming), enriquecimiento de prompts de imagen con IA, y
reformulacion de preguntas.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable

logger = logging.getLogger(__name__)

from pong.exceptions import LLMInferenceError


class NarratorSummaryMixin:
    """Mixin: resumen de partido, enriquecimiento de imagen y reformulacion."""

    # -- Atributos declarados en LocalNarrator, visibles aquí para mypy --
    enabled: bool
    _llm: Any

    def enrich_image_prompt(self, base_prompt: str, context: dict[str, Any]) -> str:
        """
        Anade detalles visuales creativos al prompt de Stable Diffusion.

        El LLM genera 1-2 frases cortas en ingles que se concatenan al
        prompt base de plantilla, aportando variedad visual sin perder
        el estilo ZX Spectrum.

        Args:
            base_prompt: Prompt base generado por build_image_prompt().
            context:     Diccionario con mood_tag, score, rally, etc.

        Returns:
            Prompt enriquecido (base + detalles del LLM), o el base
            original si el LLM no esta disponible o falla.
        """
        if not self.enabled:
            return base_prompt

        system_prompt = (
            "You add short creative visual details to Stable Diffusion prompts. "
            "Output ONLY 1-2 comma-separated visual phrases in English "
            "(10-20 words max). "
            "Keep ZX Spectrum pixel art style. No explanations, no repeating "
            "what is already in the base prompt."
        )
        narration = context.get("narration_text", "")
        user_prompt = (
            f"Base prompt: {base_prompt}\n"
            f"Game mood: {context.get('mood_tag', 'neutral')}\n"
            f"Rally hits: {context.get('rally_hits', 0)}\n"
            f"Score: player {context.get('score_player', 0)} - "
            f"computer {context.get('score_computer', 0)}\n"
        )
        if narration:
            user_prompt += f"Current narration: {narration}\n"
        user_prompt += "Add creative visual details:"

        try:
            response = self._llm.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=40,
                temperature=0.95,
                top_p=0.92,
            )
            enrichment = response["choices"][0]["message"]["content"].strip()
            if enrichment:
                return f"{base_prompt}, {enrichment}"
        except Exception as exc:
            err = LLMInferenceError(f"enrich_image_prompt: {exc}")
            err.__cause__ = exc
            logger.error("%s", err, exc_info=True)

        return base_prompt

    def reformulate_question(self, original_question: str) -> str:
        """
        Reformula una pregunta inicial para que suene diferente cada partida.

        El LLM toma la pregunta original y la reescribe manteniendo el
        significado pero cambiando las palabras.

        Args:
            original_question: La pregunta original del pool de 10.

        Returns:
            String con la pregunta reformulada, o la original si falla.
        """
        if not self.enabled:
            return original_question

        system_prompt = (
            "Eres un narrador de partidos de Pong. "
            "Reformula la siguiente pregunta de Si/No manteniendo su significado "
            "pero usando palabras diferentes. La pregunta debe ser en espanol, "
            "natural y directa. Maximo 20 palabras. "
            "Responde SOLO con la pregunta reformulada, sin explicaciones."
        )
        prompt = f"Pregunta original: {original_question}\nReformulacion:"

        try:
            response = self._llm.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=48,
                temperature=0.9,
                top_p=0.92,
            )
            raw_content = response["choices"][0]["message"]["content"]
            content = str(raw_content).strip()
            content = content.strip("\"'`")
            # Validacion basica: al menos 5 palabras
            if len(content.split()) >= 5:
                if not content.endswith("?"):
                    content += "?"
                return content
        except Exception as exc:
            err = LLMInferenceError(f"reformulando pregunta: {exc}")
            err.__cause__ = exc
            logger.error("%s", err, exc_info=True)

        return original_question

    def generate_match_summary(self, match_data: dict[str, Any]) -> str:
        """
        Genera un resumen reflexivo del partido y la conversacion con el jugador.

        El LLM recibe datos completos del partido y el dialogo, y produce
        un parrafo como cronica post-partido de un narrador deportivo.

        Args:
            match_data: Diccionario con winner, final_sets, elapsed_text,
                        total_points, dialogue_summary, narration_highlights, etc.

        Returns:
            String con el resumen (3-5 frases), o un resumen de respaldo.
        """
        fallback = self._fallback_match_summary(match_data)

        if not self.enabled:
            return fallback

        system_prompt = (
            "Eres un narrador deportivo de Pong. Acaba de terminar el partido. "
            "Escribe un resumen reflexivo de 3 a 5 frases en espanol (~80-120 palabras). "
            "El resumen debe cubrir: 1) como fue el partido (ritmo, momentos clave), "
            "2) que revelo la conversacion con el jugador sobre su personalidad o actitud. "
            "Conecta ambos aspectos: como su forma de responder refleja su forma de jugar. "
            "Tono: narrador experimentado que da su veredicto post-partido. "
            "NO uses datos numericos crudos, integralos de forma natural. "
            "NO repitas el marcador final, el jugador ya lo ve en pantalla."
        )

        prompt = (
            f"RESULTADO: {match_data['winner']} gano el partido.\n"
            f"Sets: {match_data['final_sets']} | "
            f"Juegos ultimo set: {match_data['final_games_last_set']} | "
            f"Tiempo: {match_data['elapsed_text']}\n"
            f"Puntos totales: {match_data['total_points']} "
            f"(Jugador {match_data['player_points_total']}, "
            f"Ordenador {match_data['computer_points_total']})\n"
            f"Racha max jugador: {match_data['longest_streak_player']} | "
            f"Racha max ordenador: {match_data['longest_streak_computer']}\n"
            f"---\n"
            f"CONVERSACION DURANTE EL PARTIDO:\n{match_data['dialogue_summary']}\n"
            f"---\n"
            f"MOMENTOS DESTACADOS DE LA NARRACION:\n"
            f"{match_data['narration_highlights']}\n"
            f"---\n"
            f"Perfil del jugador: {match_data['dialogue_essence']}\n"
            f"---\n"
            f"Escribe el resumen post-partido:"
        )

        try:
            response = self._llm.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=256,
                temperature=0.80,
                top_p=0.92,
                repeat_penalty=1.15,
            )
            content = response["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            err = LLMInferenceError(f"resumen de partido: {exc}")
            err.__cause__ = exc
            logger.error("%s", err, exc_info=True)
            content = ""

        if not content or len(content.split()) < 15:
            return fallback

        # Limpiar comillas y prefijos innecesarios
        content = content.strip(" \"'`")
        content = re.sub(
            r"^(resumen|cronica|veredicto)\s*[:\-]\s*",
            "", content, flags=re.IGNORECASE,
        )

        # Truncar si es excesivamente largo
        words = content.split()
        if len(words) > 150:
            content = " ".join(words[:150])
            last_period = content.rfind(".")
            if last_period > len(content) * 0.6:
                content = content[:last_period + 1]

        return content

    def generate_match_summary_streaming(self, match_data: dict[str, Any], progress_callback: Callable[[int, int], None] | None = None) -> str:
        """
        Variante streaming de generate_match_summary.

        Genera el resumen token a token y reporta progreso mediante
        *progress_callback(tokens_done, tokens_max)* tras cada chunk.
        """
        fallback = self._fallback_match_summary(match_data)

        if not self.enabled:
            if progress_callback:
                progress_callback(1, 1)
            return fallback

        system_prompt = (
            "Eres un narrador deportivo de Pong. Acaba de terminar el partido. "
            "Escribe un resumen reflexivo de 3 a 5 frases en espanol (~80-120 palabras). "
            "El resumen debe cubrir: 1) como fue el partido (ritmo, momentos clave), "
            "2) que revelo la conversacion con el jugador sobre su personalidad o actitud. "
            "Conecta ambos aspectos: como su forma de responder refleja su forma de jugar. "
            "Tono: narrador experimentado que da su veredicto post-partido. "
            "NO uses datos numericos crudos, integralos de forma natural. "
            "NO repitas el marcador final, el jugador ya lo ve en pantalla."
        )

        prompt = (
            f"RESULTADO: {match_data['winner']} gano el partido.\n"
            f"Sets: {match_data['final_sets']} | "
            f"Juegos ultimo set: {match_data['final_games_last_set']} | "
            f"Tiempo: {match_data['elapsed_text']}\n"
            f"Puntos totales: {match_data['total_points']} "
            f"(Jugador {match_data['player_points_total']}, "
            f"Ordenador {match_data['computer_points_total']})\n"
            f"Racha max jugador: {match_data['longest_streak_player']} | "
            f"Racha max ordenador: {match_data['longest_streak_computer']}\n"
            f"---\n"
            f"CONVERSACION DURANTE EL PARTIDO:\n{match_data['dialogue_summary']}\n"
            f"---\n"
            f"MOMENTOS DESTACADOS DE LA NARRACION:\n"
            f"{match_data['narration_highlights']}\n"
            f"---\n"
            f"Perfil del jugador: {match_data['dialogue_essence']}\n"
            f"---\n"
            f"Escribe el resumen post-partido:"
        )

        max_tokens = 256
        try:
            stream = self._llm.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.80,
                top_p=0.92,
                repeat_penalty=1.15,
                stream=True,
            )

            collected = []
            token_count = 0
            for chunk in stream:
                delta = chunk["choices"][0].get("delta", {})
                piece = delta.get("content", "")
                if piece:
                    collected.append(piece)
                    token_count += 1
                    if progress_callback:
                        progress_callback(token_count, max_tokens)

            content = "".join(collected).strip()
        except Exception as exc:
            err = LLMInferenceError(f"resumen de partido (streaming): {exc}")
            err.__cause__ = exc
            logger.error("%s", err, exc_info=True)
            content = ""

        if not content or len(content.split()) < 15:
            if progress_callback:
                progress_callback(1, 1)
            return fallback

        # Limpiar comillas y prefijos innecesarios
        content = content.strip(" \"'`")
        content = re.sub(
            r"^(resumen|cronica|veredicto)\s*[:\-]\s*",
            "", content, flags=re.IGNORECASE,
        )

        # Truncar si es excesivamente largo
        words = content.split()
        if len(words) > 150:
            content = " ".join(words[:150])
            last_period = content.rfind(".")
            if last_period > len(content) * 0.6:
                content = content[:last_period + 1]

        if progress_callback:
            progress_callback(1, 1)

        return content

    def _fallback_match_summary(self, match_data: dict[str, Any]) -> str:
        """
        Resumen de respaldo cuando el LLM no esta disponible.

        Args:
            match_data: Diccionario con datos del partido.

        Returns:
            String con un resumen basico pre-escrito.
        """
        winner = match_data.get("winner", "el ganador")
        elapsed = match_data.get("elapsed_text", "??:??")
        total_pts = match_data.get("total_points", 0)
        dialogue_count = match_data.get("dialogue_count", 0)

        summary = (
            f"Partido concluido en {elapsed} con {total_pts} puntos disputados. "
            f"Victoria para {winner}. "
        )
        if dialogue_count > 0:
            summary += (
                f"Durante el encuentro se intercambiaron {dialogue_count} preguntas "
                f"con el jugador, revelando su actitud ante la competencia."
            )
        else:
            summary += "No hubo dialogo durante este encuentro."
        return summary
