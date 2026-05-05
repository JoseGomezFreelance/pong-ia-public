"""Estado emocional de la IA: modula el comportamiento de la paleta."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Restringe *value* al rango [lo, hi]."""
    return max(lo, min(hi, value))


@dataclass
class EmotionalState:
    """Perfil emocional continuo que controla la paleta del ordenador.

    Cada eje va de 0.0 a 1.0:
    - aggressiveness: velocidad, prediccion, golpes con el canto.
    - stability:      precision (1.0) vs movimiento erratico (0.0).
    - motivation:     esfuerzo maximo (1.0) vs quedarse quieta (0.0).
    - mood_tag:       etiqueta narrativa para logs/debug.
    """

    aggressiveness: float = 0.5
    stability: float = 0.8
    motivation: float = 0.7
    mood_tag: str = "neutral"

    def lerp_toward(self, target: EmotionalState, factor: float) -> None:
        """Interpola suavemente los ejes numericos hacia *target*."""
        self.aggressiveness += (target.aggressiveness - self.aggressiveness) * factor
        self.stability += (target.stability - self.stability) * factor
        self.motivation += (target.motivation - self.motivation) * factor
        self.mood_tag = target.mood_tag

    def copy(self) -> EmotionalState:
        """Devuelve una copia independiente."""
        return EmotionalState(
            aggressiveness=self.aggressiveness,
            stability=self.stability,
            motivation=self.motivation,
            mood_tag=self.mood_tag,
        )


DEFAULT_EMOTIONAL_STATE = EmotionalState()


# ── Tags de humor válidos ────────────────────────────────────

VALID_MOOD_TAGS: frozenset[str] = frozenset({
    "neutral", "relajado", "tenso", "irritado", "furioso",
    "deprimido", "aburrido", "euforico", "erratico",
})

# ── Parsing del JSON emocional que genera el LLM ────────────

# Regex para extraer el primer bloque JSON de una cadena que puede contener
# texto extra antes/despues (el LLM a veces envuelve el JSON en prosa).
_JSON_RE = re.compile(r"\{[^{}]*\{[^{}]*\}[^{}]*\}", re.DOTALL)


def parse_emotion_from_llm(raw_text: str) -> EmotionalState | None:
    """Intenta extraer un EmotionalState del JSON emitido por el LLM.

    Formato esperado (campos en espanol):
        {"pregunta": "...", "emocion": {"agresividad": 0.6, ...}}

    Devuelve ``None`` si el parsing falla.
    """
    try:
        data = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError):
        # Intentar extraer JSON anidado de texto envolvente.
        match = _JSON_RE.search(raw_text)
        if not match:
            return None
        try:
            data = json.loads(match.group())
        except (json.JSONDecodeError, TypeError):
            return None

    emo_raw = data.get("emocion")
    if not isinstance(emo_raw, dict):
        return None

    try:
        aggressiveness = _clamp(float(emo_raw.get("agresividad", 0.5)))
        stability = _clamp(float(emo_raw.get("estabilidad", 0.8)))
        motivation = _clamp(float(emo_raw.get("motivacion", 0.7)))
    except (ValueError, TypeError):
        return None

    mood_tag = str(emo_raw.get("humor", "neutral"))
    if mood_tag not in VALID_MOOD_TAGS:
        mood_tag = "neutral"

    return EmotionalState(
        aggressiveness=aggressiveness,
        stability=stability,
        motivation=motivation,
        mood_tag=mood_tag,
    )


def parse_question_from_llm(raw_text: str) -> str | None:
    """Extrae el campo ``pregunta`` del JSON emitido por el LLM.

    Devuelve ``None`` si no se encuentra.
    """
    try:
        data = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError):
        match = _JSON_RE.search(raw_text)
        if not match:
            return None
        try:
            data = json.loads(match.group())
        except (json.JSONDecodeError, TypeError):
            return None

    question = data.get("pregunta")
    if isinstance(question, str) and question.strip():
        return question.strip()
    return None
