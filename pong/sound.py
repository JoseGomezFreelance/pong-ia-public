"""
pong/sound.py -- Efectos de sonido retro generados proceduralmente.

En vez de usar archivos de audio (.wav, .mp3), los sonidos se generan
matematicamente con ondas cuadradas, como en las consolas de los anos 70-80.
Esto da el clasico "beep" de arcade sin necesitar archivos externos.

La clase RetroSoundManager se encarga de crear estos sonidos al inicio
y reproducirlos cuando ocurren eventos (por ejemplo, la pelota golpea una paleta).

IMPORTANTE: pygame.init() inicializa el mixer con los ajustes por defecto del
sistema (normalmente 44100 Hz estereo). Todas las funciones de sintesis consultan
el estado real del mixer con pygame.mixer.get_init() para generar buffers
compatibles, evitando desajustes de velocidad/tono.
"""

from __future__ import annotations

import math
import struct

import pygame

from pong.config.media import (
    SOUND_PADDLE_HIT_DURATION,
    SOUND_PADDLE_HIT_FREQUENCY,
    SOUND_PADDLE_HIT_VOLUME,
    SOUND_SAMPLE_RATE,
)
from pong.config.ui_achievements import (
    ACHIEVEMENT_SOUND_DURATION,
    ACHIEVEMENT_SOUND_FREQ_END,
    ACHIEVEMENT_SOUND_FREQ_START,
    ACHIEVEMENT_SOUND_VOLUME,
)


# ============================================================
# Utilidad interna: obtener formato real del mixer
# ============================================================

def _mixer_params() -> tuple[int, int]:
    """Devuelve (sample_rate, num_channels) del mixer activo.

    Si el mixer no esta inicializado, devuelve los valores de config como
    fallback.
    """
    info = pygame.mixer.get_init()
    if info is None:
        return SOUND_SAMPLE_RATE, 1
    return info[0], info[2]


def _pack_sample(sample: int, num_channels: int, buf: bytearray) -> None:
    """Escribe una muestra 16-bit en *buf*, duplicando para estereo si hace falta."""
    if num_channels >= 2:
        buf.extend(struct.pack("<hh", sample, sample))
    else:
        buf.extend(struct.pack("<h", sample))


# ============================================================
# RetroSoundManager (SFX del juego)
# ============================================================

class RetroSoundManager:
    """
    Gestiona efectos de sonido retro generados proceduralmente.

    Al crearse, genera un sonido de "beep" usando una onda cuadrada
    (la forma de onda mas basica y "retro"). Si el sistema de audio
    no esta disponible, el juego sigue funcionando sin sonido.

    Atributos:
        enabled:          True si el sistema de audio funciona.
        paddle_hit_sound: Objeto de sonido pygame para el golpe de paleta.
    """

    def __init__(self) -> None:
        """Inicializa el sistema de audio y genera los sonidos."""
        self.enabled: bool = False
        self.paddle_hit_sound: pygame.mixer.Sound | None = None
        self._paddle_hit_retro: pygame.mixer.Sound | None = None   # Beep original (fase silencio 0-30s)
        self._paddle_hit_music: pygame.mixer.Sound | None = None   # Beep con musica (30s+)
        self._achievement_sound: pygame.mixer.Sound | None = None  # Chirp ascendente para logros
        self._music_mode: bool = False
        self._init_mixer()

    def _init_mixer(self) -> None:
        """
        Inicializa el mixer de pygame y crea los sonidos.

        Genera dos variantes del beep de rebote:
        - Retro (0-30s): replica el sonido "accidental" original — mas agudo
          (1240 Hz) y corto (0.02s), como sonaba antes del fix de sample rate.
        - Music (30s+): beep correcto a 620 Hz, 0.08s.
        """
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(
                    frequency=SOUND_SAMPLE_RATE, size=-16, channels=1
                )
            # Reservar canales suficientes para SFX + musica (3 voces + percusion)
            pygame.mixer.set_num_channels(8)

            # Beep original "retro": el antiguo beep se reproducia a 4x velocidad
            # por el desajuste de sample rate, resultando en 1240 Hz y 0.02s.
            # Replicamos ese sonido intencionadamente.
            self._paddle_hit_retro = build_square_wave(
                frequency=SOUND_PADDLE_HIT_FREQUENCY * 2,   # 1240 Hz (era 620 a 2x)
                duration=SOUND_PADDLE_HIT_DURATION / 4,     # 0.02s (era 0.08 a 4x)
                volume=SOUND_PADDLE_HIT_VOLUME,
            )

            # Beep corregido para la fase musical
            self._paddle_hit_music = build_square_wave(
                frequency=SOUND_PADDLE_HIT_FREQUENCY,
                duration=SOUND_PADDLE_HIT_DURATION,
                volume=SOUND_PADDLE_HIT_VOLUME,
            )

            # Chirp ascendente para notificaciones de logros
            self._achievement_sound = _build_achievement_chirp()

            # Empezar con el beep retro
            self.paddle_hit_sound = self._paddle_hit_retro
            self.enabled = self.paddle_hit_sound is not None
        except pygame.error:
            self.enabled = False

    def set_music_mode(self, active: bool) -> None:
        """Cambia el sonido de rebote entre retro (0-30s) y musical (30s+).

        Args:
            active: True para usar el beep corregido (fase musical).
        """
        self._music_mode = active
        if active and self._paddle_hit_music:
            self.paddle_hit_sound = self._paddle_hit_music
        elif self._paddle_hit_retro:
            self.paddle_hit_sound = self._paddle_hit_retro

    def play_paddle_hit(self) -> None:
        """Reproduce el efecto de sonido de la pelota golpeando una paleta."""
        if self.enabled and self.paddle_hit_sound:
            self.paddle_hit_sound.play()

    def play_achievement(self) -> None:
        """Reproduce el chirp ascendente de notificacion de logro."""
        if self.enabled and self._achievement_sound:
            self._achievement_sound.play()


# ============================================================
# Utilidades de sintesis reutilizables por el motor musical
# ============================================================

def build_square_wave(frequency: float, duration: float, volume: float, sample_rate: int | None = None) -> pygame.mixer.Sound | None:
    """Genera un buffer de onda cuadrada como pygame.mixer.Sound.

    Consulta el estado real del mixer (sample rate y canales) para
    generar un buffer 100% compatible. Esto evita desajustes de
    velocidad/tono cuando pygame.init() configura el mixer a 44100 Hz
    estereo en vez de 22050 Hz mono.

    Args:
        frequency: Tono en Hz.
        duration:  Duracion en segundos.
        volume:    Volumen de 0.0 a 1.0.
        sample_rate: Ignorado (se mantiene por compatibilidad). Se usa
                     siempre el rate real del mixer.

    Returns:
        pygame.mixer.Sound o None si el mixer no esta inicializado.
    """
    actual_rate, num_channels = _mixer_params()

    sample_count = int(actual_rate * duration)
    if sample_count < 1:
        return None
    fade_samples = min(int(actual_rate * 0.005), sample_count // 2)
    max_amplitude = int(32767 * max(0.0, min(volume, 1.0)))

    frames = bytearray()
    for index in range(sample_count):
        time_position = index / actual_rate

        if math.sin(2 * math.pi * frequency * time_position) >= 0:
            sample = max_amplitude
        else:
            sample = -max_amplitude

        if index < fade_samples:
            sample = int(sample * (index / fade_samples))
        elif index >= sample_count - fade_samples:
            fade_out = (sample_count - index - 1) / fade_samples
            sample = int(sample * max(0.0, fade_out))

        _pack_sample(sample, num_channels, frames)

    try:
        return pygame.mixer.Sound(buffer=bytes(frames))
    except pygame.error:
        return None


def _build_achievement_chirp() -> pygame.mixer.Sound | None:
    """Genera un chirp ascendente para notificaciones de logros.

    El chirp barre linealmente de ACHIEVEMENT_SOUND_FREQ_START a
    ACHIEVEMENT_SOUND_FREQ_END usando una onda cuadrada, con fade-in
    y fade-out para evitar clicks.

    Returns:
        pygame.mixer.Sound o None si el mixer no esta inicializado.
    """
    actual_rate, num_channels = _mixer_params()

    freq_start = ACHIEVEMENT_SOUND_FREQ_START
    freq_end = ACHIEVEMENT_SOUND_FREQ_END
    duration = ACHIEVEMENT_SOUND_DURATION
    volume = ACHIEVEMENT_SOUND_VOLUME

    sample_count = int(actual_rate * duration)
    if sample_count < 1:
        return None
    fade_samples = min(int(actual_rate * 0.005), sample_count // 2)
    max_amplitude = int(32767 * max(0.0, min(volume, 1.0)))

    frames = bytearray()
    for index in range(sample_count):
        time_position = index / actual_rate
        progress = index / sample_count
        freq = freq_start + (freq_end - freq_start) * progress

        if math.sin(2 * math.pi * freq * time_position) >= 0:
            sample = max_amplitude
        else:
            sample = -max_amplitude

        if index < fade_samples:
            sample = int(sample * (index / fade_samples))
        elif index >= sample_count - fade_samples:
            fade_out = (sample_count - index - 1) / fade_samples
            sample = int(sample * max(0.0, fade_out))

        _pack_sample(sample, num_channels, frames)

    try:
        return pygame.mixer.Sound(buffer=bytes(frames))
    except pygame.error:
        return None


def build_noise_burst(duration: float, volume: float, sample_rate: int | None = None) -> pygame.mixer.Sound | None:
    """Genera una rafaga de ruido blanco estilo canal de ruido del AY chip.

    Se usa para la percusion sintetizada (kicks, hihats, snares).
    Consulta el estado real del mixer para generar buffers compatibles.

    Args:
        duration: Duracion en segundos.
        volume:   Volumen de 0.0 a 1.0.
        sample_rate: Ignorado (compatibilidad). Se usa el rate del mixer.

    Returns:
        pygame.mixer.Sound o None si el mixer no esta inicializado.
    """
    import random as _rnd

    actual_rate, num_channels = _mixer_params()

    sample_count = int(actual_rate * duration)
    if sample_count < 1:
        return None
    fade_samples = min(int(actual_rate * 0.003), sample_count // 2)
    max_amplitude = int(32767 * max(0.0, min(volume, 1.0)))

    frames = bytearray()
    for index in range(sample_count):
        sample = _rnd.randint(-max_amplitude, max_amplitude)

        # Envolvente de percusion: ataque instantaneo + decay exponencial
        env = max(0.0, 1.0 - (index / sample_count) ** 0.5)
        sample = int(sample * env)

        if index < fade_samples:
            sample = int(sample * (index / fade_samples))

        sample = max(-32768, min(32767, sample))
        _pack_sample(sample, num_channels, frames)

    try:
        return pygame.mixer.Sound(buffer=bytes(frames))
    except pygame.error:
        return None
