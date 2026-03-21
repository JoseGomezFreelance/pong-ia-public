"""
pong/music.py -- Motor musical con sintesis ZX Spectrum y remix emocional.

Parsea un fichero MIDI y lo reproduce en tiempo real usando ondas cuadradas,
emulando el chip AY-3-8912 del Sinclair ZX Spectrum 128K (3 voces + ruido).

Fases de reproduccion:
1. Silencio (0-30 s): sin musica.
2. Tema original (30-120 s): melodia MIDI tal cual.
3. Remix emocional (120 s+): parametros modulados por el mood_tag de la IA.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pygame

if TYPE_CHECKING:
    from pong.emotional_state import EmotionalState

from pong.config.gameplay import FPS
from pong.config.media import (
    MUSIC_BULLET_TIME_VOLUME,
    MUSIC_FREQ_MAX,
    MUSIC_FREQ_MIN,
    MUSIC_MASTER_VOLUME,
    MUSIC_MAX_POLYPHONY,
    MUSIC_MIDI_PATH,
)
from pong.config.zx_spectrum import THEME_BULLET_TIME_LERP, THEME_COLOR_LERP_FACTOR
from pong.sound import build_noise_burst, build_square_wave


# ============================================================
# Eventos MIDI procesados
# ============================================================

@dataclass
class NoteEvent:
    """Un evento de nota listo para reproduccion."""

    time: float          # Tiempo absoluto en segundos desde el inicio
    midi_note: int       # Nota MIDI (0-127)
    velocity: int        # Velocidad (0-127)
    duration: float      # Duracion en segundos
    voice: int           # Indice de voz (0=melodia, 1=armonia, 2=bajo, 3=percusion)


# ============================================================
# Mapeo emocional: mood_tag -> parametros musicales
# ============================================================

@dataclass
class MoodMusicParams:
    """Parametros musicales objetivo para un mood_tag."""

    tempo_mult: float = 1.0       # Multiplicador de tempo (1.0 = original)
    pitch_shift: float = 0.0      # Semitonos de transposicion
    active_voices: int = 3        # Voces melodicas activas (1-3)
    drum_intensity: float = 1.0   # Intensidad de percusion (0.0-1.0)
    note_duration_mult: float = 1.0  # Multiplicador de duracion de notas


MOOD_MUSIC_PARAMS: dict[str, MoodMusicParams] = {
    "neutral":   MoodMusicParams(1.0,  0.0, 3, 1.0, 1.0),
    "relajado":  MoodMusicParams(0.75, 0.0, 2, 0.3, 1.4),
    "tenso":     MoodMusicParams(1.1,  2.0, 3, 1.2, 0.7),
    "irritado":  MoodMusicParams(1.2,  3.0, 3, 1.4, 0.6),
    "furioso":   MoodMusicParams(1.4,  5.0, 3, 1.6, 0.5),
    "deprimido": MoodMusicParams(0.6, -3.0, 1, 0.0, 1.6),
    "aburrido":  MoodMusicParams(0.5, -2.0, 1, 0.2, 1.8),
    "euforico":  MoodMusicParams(1.3,  4.0, 3, 1.5, 0.8),
    "erratico":  MoodMusicParams(1.0,  0.0, 2, 0.8, 1.0),
}


# ============================================================
# EmotionalRemixer
# ============================================================

class EmotionalRemixer:
    """Interpola parametros musicales hacia el mood_tag actual.

    Usa el mismo factor de interpolacion que el sistema de colores
    (THEME_COLOR_LERP_FACTOR) para mantener sincronia visual-sonora.
    """

    def __init__(self) -> None:
        self.tempo_mult: float = 1.0
        self.pitch_shift: float = 0.0
        self.active_voices: float = 3.0
        self.drum_intensity: float = 1.0
        self.note_duration_mult: float = 1.0
        self._erratic_timer: float = 0.0

    def update(self, mood_tag: str, dt: float, is_bullet_time: bool = False) -> None:
        """Interpola los parametros hacia el mood actual."""
        target = MOOD_MUSIC_PARAMS.get(mood_tag, MOOD_MUSIC_PARAMS["neutral"])
        lerp = THEME_BULLET_TIME_LERP if is_bullet_time else THEME_COLOR_LERP_FACTOR

        # Caso especial: erratico cambia parametros periodicamente
        if mood_tag == "erratico":
            self._erratic_timer += dt
            if self._erratic_timer > 2.0:  # Cada 2 segundos
                self._erratic_timer = 0.0
                import random
                target = MoodMusicParams(
                    tempo_mult=random.uniform(0.7, 1.5),
                    pitch_shift=random.uniform(-4.0, 4.0),
                    active_voices=random.randint(1, 3),
                    drum_intensity=random.uniform(0.2, 1.5),
                    note_duration_mult=random.uniform(0.5, 1.5),
                )

        self.tempo_mult += (target.tempo_mult - self.tempo_mult) * lerp
        self.pitch_shift += (target.pitch_shift - self.pitch_shift) * lerp
        self.active_voices += (target.active_voices - self.active_voices) * lerp
        self.drum_intensity += (target.drum_intensity - self.drum_intensity) * lerp
        self.note_duration_mult += (target.note_duration_mult - self.note_duration_mult) * lerp

    def get_active_voice_count(self) -> int:
        """Devuelve el numero entero de voces activas."""
        return max(1, min(MUSIC_MAX_POLYPHONY, round(self.active_voices)))


# ============================================================
# MusicEngine
# ============================================================

class MusicEngine:
    """Motor musical que sintetiza un MIDI con ondas cuadradas ZX Spectrum.

    Parsea el MIDI al inicializarse, y cada frame avanza el playback_time
    reproduciendo las notas cuyo momento ha llegado.
    """

    # Buckets de duracion para cachear sonidos (evitar generar cada frame)
    _DURATION_BUCKETS = (0.03, 0.05, 0.08, 0.1, 0.15, 0.2, 0.3, 0.5, 0.8, 1.0, 1.5, 2.0)

    def __init__(self) -> None:
        self.loaded: bool = False
        self.playing: bool = False
        self.playback_time: float = 0.0
        self.event_index: int = 0
        self.total_duration: float = 0.0

        self._events: list[NoteEvent] = []
        self._note_cache: dict[tuple[int, float], pygame.mixer.Sound] = {}
        self._drum_cache: dict[float, pygame.mixer.Sound] = {}
        self._channel_index: int = 0  # Rotacion round-robin de canales

        self.remixer = EmotionalRemixer()
        self._volume_mult: float = 1.0   # Para atenuacion en bullet time

        # Pistas seleccionadas del MIDI (indices de track):
        # Track 2 (ch1) = melodia principal (voz 0)
        # Track 1 (ch0) = armonia (voz 1)
        # Track 3 (ch2) = bajo (voz 2)
        # Track 6 (ch9) = percusion (voz 3)
        self._voice_track_map = {2: 0, 1: 1, 3: 2, 6: 3}

        self._load_midi()

    # ----------------------------------------------------------
    # Parseo MIDI
    # ----------------------------------------------------------

    def _load_midi(self) -> None:
        """Parsea el fichero MIDI y convierte los eventos a NoteEvent."""
        midi_path = Path(MUSIC_MIDI_PATH)
        if not midi_path.is_absolute():
            # Ruta relativa al directorio del proyecto
            project_root = Path(__file__).resolve().parent.parent
            midi_path = project_root / midi_path

        if not midi_path.exists():
            return

        try:
            import mido
        except ImportError:
            return

        try:
            mid = mido.MidiFile(str(midi_path))
        except (OSError, ValueError):
            return

        # Recoger tempo changes de la pista conductor (track 0)
        tempo_map = self._build_tempo_map(mid.tracks[0], mid.ticks_per_beat)

        # Procesar las pistas seleccionadas
        for track_idx, voice_idx in self._voice_track_map.items():
            if track_idx >= len(mid.tracks):
                continue
            self._parse_track(
                mid.tracks[track_idx], voice_idx,
                mid.ticks_per_beat, tempo_map,
            )

        # Ordenar todos los eventos por tiempo
        self._events.sort(key=lambda e: e.time)

        if self._events:
            self.total_duration = self._events[-1].time + self._events[-1].duration
            self.loaded = True

    def _build_tempo_map(self, conductor_track: Iterable[Any], ticks_per_beat: int) -> list[tuple[int, float]]:
        """Extrae un mapa de tempo [(tick_absoluto, microseg_por_beat), ...].

        Returns:
            Lista ordenada de cambios de tempo. Si no hay ningun set_tempo,
            asume 120 BPM (500000 us/beat).
        """
        import mido

        tempo_map: list[tuple[int, float]] = []
        abs_tick = 0
        for msg in conductor_track:
            abs_tick += msg.time
            if msg.type == "set_tempo":
                tempo_map.append((abs_tick, msg.tempo))

        if not tempo_map:
            tempo_map.append((0, 500000))  # 120 BPM por defecto
        elif tempo_map[0][0] != 0:
            tempo_map.insert(0, (0, 500000))

        return tempo_map

    def _tick_to_seconds(
        self, abs_tick: int, ticks_per_beat: int, tempo_map: list[tuple[int, float]]
    ) -> float:
        """Convierte un tick absoluto a segundos usando el mapa de tempo."""
        seconds = 0.0
        prev_tick = 0
        prev_tempo = tempo_map[0][1]

        for map_tick, map_tempo in tempo_map:
            if map_tick >= abs_tick:
                break
            # Acumular tiempo del tramo anterior
            delta_ticks = map_tick - prev_tick
            seconds += delta_ticks * prev_tempo / (ticks_per_beat * 1_000_000)
            prev_tick = map_tick
            prev_tempo = map_tempo

        # Tramo final hasta abs_tick
        delta_ticks = abs_tick - prev_tick
        seconds += delta_ticks * prev_tempo / (ticks_per_beat * 1_000_000)
        return seconds

    def _parse_track(
        self,
        track: Iterable[Any],
        voice_idx: int,
        ticks_per_beat: int,
        tempo_map: list[tuple[int, float]],
    ) -> None:
        """Convierte una pista MIDI en NoteEvents."""
        # Primero recoger note_on/note_off con ticks absolutos
        abs_tick = 0
        active_notes: dict[int, tuple[int, int]] = {}  # note -> (start_tick, velocity)

        for msg in track:
            abs_tick += msg.time

            if msg.type == "note_on" and msg.velocity > 0:
                active_notes[msg.note] = (abs_tick, msg.velocity)
            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                if msg.note in active_notes:
                    start_tick, velocity = active_notes.pop(msg.note)
                    start_sec = self._tick_to_seconds(start_tick, ticks_per_beat, tempo_map)
                    end_sec = self._tick_to_seconds(abs_tick, ticks_per_beat, tempo_map)
                    duration = max(0.02, end_sec - start_sec)

                    self._events.append(NoteEvent(
                        time=start_sec,
                        midi_note=msg.note,
                        velocity=velocity,
                        duration=duration,
                        voice=voice_idx,
                    ))

    # ----------------------------------------------------------
    # Sintesis de notas
    # ----------------------------------------------------------

    @staticmethod
    def _snap_duration(duration: float) -> float:
        """Redondea la duracion al bucket mas cercano para cache."""
        best = MusicEngine._DURATION_BUCKETS[-1]
        for bucket in MusicEngine._DURATION_BUCKETS:
            if duration <= bucket:
                best = bucket
                break
        return best

    def _get_note_sound(
        self, midi_note: int, duration: float, velocity: int, pitch_shift: float = 0.0
    ) -> pygame.mixer.Sound | None:
        """Obtiene o genera un Sound de onda cuadrada para la nota.

        El volumen en la onda se fija a 0.7 (fuerte pero sin clipear).
        El escalado final por velocity y MUSIC_MASTER_VOLUME se aplica
        en _play_note via set_volume del canal, evitando doble atenuacion.
        """
        # Aplicar pitch shift
        effective_note = midi_note + pitch_shift
        freq = 440.0 * (2 ** ((effective_note - 69) / 12.0))

        # Clampear al rango del ZX Spectrum
        freq = max(MUSIC_FREQ_MIN, min(MUSIC_FREQ_MAX, freq))

        snapped = self._snap_duration(duration)
        cache_key = (round(effective_note * 2), snapped)  # Resolucion de medio semitono

        if cache_key not in self._note_cache:
            sound = build_square_wave(freq, snapped, 0.7)
            if sound is not None:
                self._note_cache[cache_key] = sound

        return self._note_cache.get(cache_key)

    def _get_drum_sound(self, midi_note: int, velocity: int) -> pygame.mixer.Sound | None:
        """Obtiene o genera un Sound de ruido blanco para percusion.

        Volumen fijo en la onda (0.7); escalado final por canal en _play_note.
        """
        # Diferentes duraciones segun tipo de percusion
        if midi_note in (36, 35):       # Kick drum
            dur = 0.08
        elif midi_note in (38, 40):     # Snare
            dur = 0.06
        elif midi_note in (42, 44, 46): # Hi-hat
            dur = 0.03
        else:
            dur = 0.05

        cache_key = dur
        if cache_key not in self._drum_cache:
            sound = build_noise_burst(dur, 0.7)
            if sound is not None:
                self._drum_cache[cache_key] = sound

        return self._drum_cache.get(cache_key)

    # ----------------------------------------------------------
    # Reproduccion
    # ----------------------------------------------------------

    def _next_channel(self) -> pygame.mixer.Channel | None:
        """Devuelve el siguiente canal disponible (round-robin desde canal 1).

        Canal 0 se reserva para el SFX de rebote de paleta.
        """
        try:
            total = pygame.mixer.get_num_channels()
        except pygame.error:
            return None

        # Canales 1..total-1 para musica
        for _ in range(total - 1):
            idx = 1 + (self._channel_index % (total - 1))
            self._channel_index += 1
            ch = pygame.mixer.Channel(idx)
            if not ch.get_busy():
                return ch

        # Todos ocupados: robar el siguiente en rotacion
        idx = 1 + (self._channel_index % (total - 1))
        self._channel_index += 1
        return pygame.mixer.Channel(idx)

    def _play_note(self, event: NoteEvent) -> None:
        """Reproduce un NoteEvent en un canal disponible."""
        voice_limit = self.remixer.get_active_voice_count()

        # Filtrar voces segun el remixer (voz 3 = percusion, siempre se evalua aparte)
        if event.voice < 3 and event.voice >= voice_limit:
            return

        # Percusion: evaluar drum_intensity
        if event.voice == 3:
            if self.remixer.drum_intensity <= 0.05:
                return
            sound = self._get_drum_sound(event.midi_note, event.velocity)
        else:
            duration = event.duration * self.remixer.note_duration_mult
            sound = self._get_note_sound(
                event.midi_note, duration, event.velocity,
                pitch_shift=self.remixer.pitch_shift,
            )

        if sound is None:
            return

        ch = self._next_channel()
        if ch is None:
            return

        # Volumen final: master * velocity * bullet_time * (drum_intensity si percusion)
        vel_factor = event.velocity / 127.0
        vol = MUSIC_MASTER_VOLUME * vel_factor * self._volume_mult
        if event.voice == 3:
            vol *= min(1.0, self.remixer.drum_intensity)

        ch.set_volume(max(0.0, min(1.0, vol)))
        ch.play(sound)

    # ----------------------------------------------------------
    # API publica
    # ----------------------------------------------------------

    def start(self) -> None:
        """Inicia la reproduccion desde el principio."""
        if not self.loaded:
            return
        self.playing = True
        self.playback_time = 0.0
        self.event_index = 0

    def stop(self) -> None:
        """Detiene la reproduccion."""
        self.playing = False

    def set_bullet_time(self, active: bool) -> None:
        """Atenua el volumen durante el bullet time de preguntas."""
        self._volume_mult = MUSIC_BULLET_TIME_VOLUME if active else 1.0

    def update(
        self,
        dt: float,
        emotional_state: EmotionalState | None = None,
        emotion_active: bool = False,
        is_bullet_time: bool = False,
    ) -> None:
        """Avanza la reproduccion y dispara las notas pendientes.

        Debe llamarse cada frame desde game.py.

        Args:
            dt: Delta time en segundos (siempre 1/FPS, tiempo real).
            emotional_state: EmotionalState actual (None = sin remix).
            emotion_active: True si el remix emocional esta activo.
            is_bullet_time: True durante la camara lenta de preguntas.
        """
        if not self.playing or not self.loaded:
            return

        # Actualizar remixer si hay estado emocional
        if emotion_active and emotional_state is not None:
            self.remixer.update(
                emotional_state.mood_tag, dt, is_bullet_time=is_bullet_time,
            )

        # Avanzar el tiempo de reproduccion (modulado por tempo del remixer)
        effective_dt = dt * self.remixer.tempo_mult
        self.playback_time += effective_dt

        # Reproducir notas cuyo momento ha llegado
        while (
            self.event_index < len(self._events)
            and self._events[self.event_index].time <= self.playback_time
        ):
            self._play_note(self._events[self.event_index])
            self.event_index += 1

        # Loop: si se acabaron los eventos, reiniciar
        if self.event_index >= len(self._events):
            self.playback_time = 0.0
            self.event_index = 0
