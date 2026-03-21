"""
pong/theme.py -- Sistema de colores dinamicos con estetica ZX Spectrum.

Gestiona las tres fases visuales del juego:
1. Fase monocromo (0-30 s): Pong clasico blanco y negro.
2. Fase despertar (~30 s):   Transicion suave al marron ZX Spectrum.
3. Fase emocional (continua): Colores segun el estado emocional de la IA.

La paleta esta restringida a los 16 colores del Sinclair ZX Spectrum (4-bit).
Todas las transiciones usan interpolacion lineal (lerp) entre tuplas RGB.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pong.emotional_state import EmotionalState

from pong.config.narrator import QUESTION_FIRST_DELAY_SECONDS
from pong.config.zx_spectrum import (
    THEME_AWAKENING_DURATION,
    THEME_BULLET_TIME_LERP,
    THEME_COLOR_LERP_FACTOR,
    ZX_BLACK,
    ZX_BLUE_BRIGHT,
    ZX_BLUE_DARK,
    ZX_BROWN,
    ZX_CYAN_BRIGHT,
    ZX_GRAY_DARK,
    ZX_GRAY_LIGHT,
    ZX_GREEN_BRIGHT,
    ZX_GREEN_DARK,
    ZX_MAGENTA_BRIGHT,
    ZX_MAGENTA_DARK,
    ZX_RED_BRIGHT,
    ZX_RED_DARK,
    ZX_WHITE,
    ZX_YELLOW,
)

# Tipo RGB: tupla de 3 enteros (0-255).
RGB = tuple[int, int, int]


# ============================================================
# Colores por defecto (monocromo Pong 1972)
# ============================================================

@dataclass
class ThemeColors:
    """Colores actuales para cada elemento visual del juego.

    Todos los campos son tuplas RGB ``(int, int, int)``.
    Los valores por defecto reproducen el estilo monocromo original.
    """

    # Zona de juego
    background: RGB = (0, 0, 0)
    player_paddle: RGB = (255, 255, 255)
    computer_paddle: RGB = (255, 255, 255)
    ball: RGB = (255, 255, 255)
    center_line: RGB = (255, 255, 255)

    # Marcador
    score_text: RGB = (255, 255, 255)
    score_band_bg: RGB = (20, 20, 20)
    divider: RGB = (50, 50, 50)

    # Narracion
    narration_text: RGB = (255, 255, 255)
    narration_bg: RGB = (20, 20, 20)

    # Preguntas (bullet time)
    answer_active: RGB = (255, 255, 255)
    answer_inactive: RGB = (80, 80, 80)
    countdown: RGB = (120, 120, 120)

    # Pantalla final
    end_screen_bg: RGB = (8, 8, 8)
    end_screen_text: RGB = (255, 255, 255)
    summary_text: RGB = (220, 220, 220)
    summary_label: RGB = (120, 120, 120)
    progress_filled: RGB = (255, 255, 255)
    progress_empty: RGB = (30, 30, 30)
    copy_button_border: RGB = (255, 255, 255)
    copy_button_text: RGB = (255, 255, 255)


# ============================================================
# Utilidad: interpolacion RGB
# ============================================================

def _lerp_rgb(current: RGB, target: RGB, factor: float) -> RGB:
    """Interpola suavemente entre dos colores RGB.

    Cuando el paso calculado es tan pequeno que ``round()`` lo convierte
    en cero, salta directamente al valor objetivo para evitar que el
    color se quede atascado a unos pocos niveles del target.

    Args:
        current: Color actual ``(r, g, b)``.
        target:  Color objetivo ``(r, g, b)``.
        factor:  0.0 = sin cambio, 1.0 = saltar al target.

    Returns:
        Tupla RGB interpolada, clampeada a 0-255.
    """
    def _ch(c: int, t: int) -> int:
        if c == t:
            return t
        step = (t - c) * factor
        rounded = round(step)
        if rounded == 0:
            # Paso demasiado pequeno para mover un entero.
            # Si factor > 0 estamos cerca del target: snap.
            # Si factor == 0 no queremos mover: quedarse.
            return t if factor > 0 else c
        return max(0, min(255, c + rounded))

    return (_ch(current[0], target[0]),
            _ch(current[1], target[1]),
            _ch(current[2], target[2]))


# ============================================================
# Esquemas de color por mood_tag
# ============================================================
# Cada mood_tag mapea a un esquema completo.  Criterios de diseno:
# - computer_paddle y narration_text comparten color (la "voz" del ordenador).
# - ball contrasta con computer_paddle (complementario dentro de la paleta ZX).
# - center_line es un tono armonico mas oscuro.
# - score_text sigue el tono dominante suavizado.
# - divider es la version oscura del color dominante.

_BROWN_DARK: RGB = (85, 42, 0)

MOOD_COLOR_SCHEMES: dict[str, dict[str, RGB]] = {
    "neutral": {
        "computer_paddle": ZX_BLUE_BRIGHT,
        "narration_text":  ZX_BLUE_BRIGHT,
        "ball":            ZX_CYAN_BRIGHT,
        "center_line":     ZX_BLUE_DARK,
        "score_text":      ZX_GRAY_LIGHT,
        "divider":         ZX_BLUE_DARK,
        "answer_active":   ZX_CYAN_BRIGHT,
        "countdown":       ZX_BLUE_DARK,
    },
    "relajado": {
        "computer_paddle": ZX_GREEN_BRIGHT,
        "narration_text":  ZX_GREEN_BRIGHT,
        "ball":            ZX_CYAN_BRIGHT,
        "center_line":     ZX_GREEN_DARK,
        "score_text":      ZX_GREEN_BRIGHT,
        "divider":         ZX_GREEN_DARK,
        "answer_active":   ZX_GREEN_BRIGHT,
        "countdown":       ZX_GREEN_DARK,
    },
    "tenso": {
        "computer_paddle": ZX_RED_BRIGHT,
        "narration_text":  ZX_RED_BRIGHT,
        "ball":            ZX_YELLOW,
        "center_line":     ZX_RED_DARK,
        "score_text":      ZX_RED_BRIGHT,
        "divider":         ZX_RED_DARK,
        "answer_active":   ZX_YELLOW,
        "countdown":       ZX_RED_DARK,
    },
    "irritado": {
        "computer_paddle": ZX_RED_BRIGHT,
        "narration_text":  ZX_RED_BRIGHT,
        "ball":            ZX_MAGENTA_BRIGHT,
        "center_line":     ZX_RED_DARK,
        "score_text":      ZX_RED_BRIGHT,
        "divider":         ZX_RED_DARK,
        "answer_active":   ZX_MAGENTA_BRIGHT,
        "countdown":       ZX_RED_DARK,
    },
    "furioso": {
        "computer_paddle": ZX_RED_DARK,
        "narration_text":  ZX_RED_DARK,
        "ball":            ZX_RED_BRIGHT,
        "center_line":     ZX_MAGENTA_DARK,
        "score_text":      ZX_RED_BRIGHT,
        "divider":         ZX_MAGENTA_DARK,
        "answer_active":   ZX_RED_BRIGHT,
        "countdown":       ZX_RED_DARK,
    },
    "deprimido": {
        "computer_paddle": ZX_RED_DARK,
        "narration_text":  ZX_RED_DARK,
        "ball":            ZX_GRAY_DARK,
        "center_line":     ZX_GRAY_DARK,
        "score_text":      ZX_GRAY_LIGHT,
        "divider":         ZX_GRAY_DARK,
        "answer_active":   ZX_GRAY_LIGHT,
        "countdown":       ZX_GRAY_DARK,
    },
    "aburrido": {
        "computer_paddle": ZX_GRAY_LIGHT,
        "narration_text":  ZX_GRAY_LIGHT,
        "ball":            ZX_BROWN,
        "center_line":     ZX_GRAY_DARK,
        "score_text":      ZX_GRAY_LIGHT,
        "divider":         ZX_GRAY_DARK,
        "answer_active":   ZX_BROWN,
        "countdown":       ZX_GRAY_DARK,
    },
    "euforico": {
        "computer_paddle": ZX_YELLOW,
        "narration_text":  ZX_YELLOW,
        "ball":            ZX_MAGENTA_BRIGHT,
        "center_line":     ZX_GREEN_BRIGHT,
        "score_text":      ZX_YELLOW,
        "divider":         ZX_GREEN_DARK,
        "answer_active":   ZX_YELLOW,
        "countdown":       ZX_GREEN_DARK,
    },
    "erratico": {
        "computer_paddle": ZX_MAGENTA_BRIGHT,
        "narration_text":  ZX_MAGENTA_BRIGHT,
        "ball":            ZX_CYAN_BRIGHT,
        "center_line":     ZX_MAGENTA_DARK,
        "score_text":      ZX_MAGENTA_BRIGHT,
        "divider":         ZX_MAGENTA_DARK,
        "answer_active":   ZX_CYAN_BRIGHT,
        "countdown":       ZX_MAGENTA_DARK,
    },
}

# Esquema de la fase "despertar": todo tiende al marron ZX Spectrum.
_AWAKENING_SCHEME: dict[str, RGB] = {
    "computer_paddle": ZX_BROWN,
    "narration_text":  ZX_BROWN,
    "ball":            ZX_BROWN,
    "center_line":     ZX_BROWN,
    "score_text":      ZX_BROWN,
    "divider":         _BROWN_DARK,
    "answer_active":   ZX_BROWN,
    "countdown":       _BROWN_DARK,
}


# ============================================================
# ThemeManager
# ============================================================

class ThemeManager:
    """Gestor de colores dinamicos con estetica ZX Spectrum.

    Cada frame, el juego llama a ``update()`` con el tiempo transcurrido
    y el estado emocional actual.  ThemeManager calcula los colores
    objetivo segun la fase actual y los interpola suavemente.

    Fases:
        1. **monochrome** — Todo blanco sobre negro (Pong clasico).
        2. **awakening**  — Transicion al marron #AA5500.
        3. **emotional**  — Colores modulados por ``mood_tag``.
    """

    def __init__(self) -> None:
        self.colors = ThemeColors()
        self._phase = "monochrome"
        self._awakening_start: float | None = None

    @property
    def phase(self) -> str:
        """Fase actual: ``'monochrome'``, ``'awakening'`` o ``'emotional'``."""
        return self._phase

    def update(
        self,
        elapsed_time: float,
        emotional_state: EmotionalState | None,
        emotion_active: bool,
        is_bullet_time: bool = False,
    ) -> None:
        """Actualiza los colores para el frame actual.

        Args:
            elapsed_time:    Segundos desde el inicio del partido.
            emotional_state: ``EmotionalState`` actual (puede ser ``None``).
            emotion_active:  ``True`` si el sistema emocional esta activado.
            is_bullet_time:  ``True`` durante la camara lenta de preguntas.
        """
        awakening_threshold = QUESTION_FIRST_DELAY_SECONDS

        # --- Determinar fase ---
        if elapsed_time < awakening_threshold:
            self._phase = "monochrome"
        elif self._awakening_start is None:
            self._awakening_start = elapsed_time
            self._phase = "awakening"
        elif elapsed_time < self._awakening_start + THEME_AWAKENING_DURATION:
            self._phase = "awakening"
        else:
            self._phase = "emotional"

        # --- Colores objetivo ---
        target = self._compute_target(emotional_state, emotion_active)

        # --- Fase monocromo: colores fijos, sin lerp ---
        if self._phase == "monochrome":
            self.colors = target
            return

        # --- Interpolar suavemente ---
        lerp = THEME_BULLET_TIME_LERP if is_bullet_time else THEME_COLOR_LERP_FACTOR

        self.colors = ThemeColors(
            # Fondos e invariantes: salto directo (sin lerp)
            background=target.background,
            player_paddle=target.player_paddle,
            score_band_bg=target.score_band_bg,
            narration_bg=target.narration_bg,
            answer_inactive=target.answer_inactive,
            end_screen_bg=target.end_screen_bg,
            summary_label=target.summary_label,
            progress_empty=target.progress_empty,
            # Elementos dinamicos: interpolacion suave
            computer_paddle=_lerp_rgb(self.colors.computer_paddle, target.computer_paddle, lerp),
            ball=_lerp_rgb(self.colors.ball, target.ball, lerp),
            center_line=_lerp_rgb(self.colors.center_line, target.center_line, lerp),
            score_text=_lerp_rgb(self.colors.score_text, target.score_text, lerp),
            divider=_lerp_rgb(self.colors.divider, target.divider, lerp),
            narration_text=_lerp_rgb(self.colors.narration_text, target.narration_text, lerp),
            answer_active=_lerp_rgb(self.colors.answer_active, target.answer_active, lerp),
            countdown=_lerp_rgb(self.colors.countdown, target.countdown, lerp),
            end_screen_text=_lerp_rgb(self.colors.end_screen_text, target.end_screen_text, lerp),
            summary_text=_lerp_rgb(self.colors.summary_text, target.summary_text, lerp),
            progress_filled=_lerp_rgb(self.colors.progress_filled, target.progress_filled, lerp),
            copy_button_border=_lerp_rgb(self.colors.copy_button_border, target.copy_button_border, lerp),
            copy_button_text=_lerp_rgb(self.colors.copy_button_text, target.copy_button_text, lerp),
        )

    # ----------------------------------------------------------

    def _compute_target(self, emotional_state: EmotionalState | None, emotion_active: bool) -> ThemeColors:
        """Devuelve los colores "puros" de la fase actual (sin lerp)."""
        if self._phase == "monochrome":
            return ThemeColors()

        if self._phase == "awakening":
            scheme = _AWAKENING_SCHEME
        elif emotion_active and emotional_state is not None:
            mood = emotional_state.mood_tag
            scheme = MOOD_COLOR_SCHEMES.get(mood, MOOD_COLOR_SCHEMES["neutral"])
        else:
            scheme = MOOD_COLOR_SCHEMES["neutral"]

        return ThemeColors(
            background=ZX_BLACK,
            player_paddle=ZX_WHITE,
            computer_paddle=scheme["computer_paddle"],
            ball=scheme["ball"],
            center_line=scheme["center_line"],
            score_text=scheme["score_text"],
            score_band_bg=(20, 20, 20),
            divider=scheme["divider"],
            narration_text=scheme["narration_text"],
            narration_bg=(20, 20, 20),
            answer_active=scheme["answer_active"],
            answer_inactive=(80, 80, 80),
            countdown=scheme["countdown"],
            end_screen_bg=(8, 8, 8),
            end_screen_text=scheme["score_text"],
            summary_text=scheme["narration_text"],
            summary_label=(120, 120, 120),
            progress_filled=scheme["computer_paddle"],
            progress_empty=(30, 30, 30),
            copy_button_border=scheme["score_text"],
            copy_button_text=scheme["score_text"],
        )
