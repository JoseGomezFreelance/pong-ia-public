"""Sonido retro, musica (sintesis ZX Spectrum) y fase visual generativa."""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = [
    # Sonido retro
    "SOUND_SAMPLE_RATE",
    "SOUND_PADDLE_HIT_FREQUENCY",
    "SOUND_PADDLE_HIT_DURATION",
    "SOUND_PADDLE_HIT_VOLUME",
    # Musica: tema principal (sintesis ZX Spectrum)
    "MUSIC_MIDI_PATH",
    "MUSIC_START_SECONDS",
    "MUSIC_ORIGINAL_DURATION",
    "MUSIC_REMIX_START",
    "MUSIC_MASTER_VOLUME",
    "MUSIC_MAX_POLYPHONY",
    "MUSIC_DRUM_VOLUME",
    "MUSIC_MELODY_VOLUME",
    "MUSIC_FREQ_MIN",
    "MUSIC_FREQ_MAX",
    "MUSIC_NOTE_FADE_MS",
    "MUSIC_BULLET_TIME_VOLUME",
    # Fase visual generativa (fondo con IA de imagen)
    "IMAGEGEN_UNLOCK_TOTAL_SECONDS",
    "IMAGEGEN_MATCH_ACTIVATE_SECONDS",
    "IMAGEGEN_INTERVAL_SECONDS",
    "IMAGEGEN_TRANSITION_SECONDS",
    "IMAGEGEN_OVERLAY_ALPHA",
    "IMAGEGEN_CACHE_DIR",
    "IMAGEGEN_DEBUG_SAVE",
]


# ============================================================
# Helpers de rutas para PyInstaller
# ============================================================

def _resolve_asset_path(relative: str) -> Path:
    """Ruta de asset compatible con desarrollo y ejecutable PyInstaller."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidate = Path(meipass) / relative
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parent.parent.parent / relative


def _resolve_writable_dir(relative: str) -> Path:
    """Directorio escribible junto al .app o en la raiz del proyecto."""
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        if exe_dir.name == "MacOS" and exe_dir.parent.name == "Contents":
            return exe_dir.parent.parent.parent / relative
        return exe_dir / relative
    return Path(relative)


# ============================================================
# SONIDO RETRO
# ============================================================
# Los sonidos se generan proceduralmente (no son archivos de audio).
# Usamos una onda cuadrada como en las consolas de los 70-80.
SOUND_SAMPLE_RATE = 22050              # Frecuencia de muestreo (Hz)
SOUND_PADDLE_HIT_FREQUENCY = 620      # Tono del "beep" al golpear (Hz)
SOUND_PADDLE_HIT_DURATION = 0.08      # Duracion del beep (segundos)
SOUND_PADDLE_HIT_VOLUME = 0.25        # Volumen (0.0 a 1.0)


# ============================================================
# MUSICA: TEMA PRINCIPAL (sintesis ZX Spectrum)
# ============================================================
# El tema MIDI se sintetiza en tiempo real con ondas cuadradas,
# emulando el chip AY-3-8912 del Sinclair ZX Spectrum 128K.
MUSIC_MIDI_PATH = _resolve_asset_path("assets/music/main_theme.mid")
MUSIC_START_SECONDS = 30.0             # Empieza con el "despertar" visual
MUSIC_ORIGINAL_DURATION = 90.0         # Segundos de melodia original antes del remix
MUSIC_REMIX_START = MUSIC_START_SECONDS + MUSIC_ORIGINAL_DURATION  # 120s = 2 min
MUSIC_MASTER_VOLUME = 0.35             # Volumen global de la musica
MUSIC_MAX_POLYPHONY = 3                # Voces simultaneas (AY chip = 3 canales)
MUSIC_DRUM_VOLUME = 0.12               # Volumen de percusion (ruido blanco)
MUSIC_MELODY_VOLUME = 0.20             # Volumen de voces melodicas
MUSIC_FREQ_MIN = 100                   # Hz minimo (rango realista del beeper)
MUSIC_FREQ_MAX = 4000                  # Hz maximo
MUSIC_NOTE_FADE_MS = 5                 # Milisegundos de micro-fade anti-click
MUSIC_BULLET_TIME_VOLUME = 0.5         # Multiplicador de volumen en bullet time


# ============================================================
# FASE VISUAL GENERATIVA (fondo con IA de imagen)
# ============================================================
# Se desbloquea tras 5 minutos de juego acumulado entre partidas.
# Una vez desbloqueada, se activa a los 3 minutos de cada partida.
# El fondo negro del terreno de juego pasa a mostrar imagenes
# generadas por Stable Diffusion, contextualizadas al estado
# emocional, el marcador y la conversacion con el LLM.

IMAGEGEN_UNLOCK_TOTAL_SECONDS = 300       # 5 min totales para desbloquear
IMAGEGEN_MATCH_ACTIVATE_SECONDS = 180     # 3 min de partida para activar

# La configuracion del modelo de imagen (model_id, LoRAs, steps, etc.)
# se define ahora en models.toml. Ver pong/config/models.py.
IMAGEGEN_INTERVAL_SECONDS = 15            # Segundos entre generaciones
IMAGEGEN_TRANSITION_SECONDS = 3.0         # Fade de transicion entre imagenes
IMAGEGEN_OVERLAY_ALPHA = 60               # Opacidad del overlay oscuro (0-255)
                                          # para que los elementos del juego
                                          # sigan siendo visibles
IMAGEGEN_CACHE_DIR = _resolve_writable_dir("models/diffusion")
IMAGEGEN_DEBUG_SAVE = False              # Guardar cada imagen generada a disco
