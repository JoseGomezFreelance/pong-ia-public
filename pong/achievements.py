"""
pong/achievements.py -- Sistema de logros inspirado en Cookie Clicker.

Motor de logros autocontenido: definiciones, comprobacion y persistencia.
Cada logro es un dato declarativo (AchievementDef); anadir uno nuevo es
anadir una entrada al diccionario ACHIEVEMENT_DEFS, sin escribir logica.

El motor tiene dos fases de comprobacion:
- check_realtime(): se llama tras cada punto, con acceso al estado vivo.
- check_post_match(): se llama al guardar la partida, con session_data.

Las estadisticas de carrera (CareerStats) se acumulan entre sesiones y
se persisten junto con los logros en game_history.json.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pong.exceptions import AchievementDefinitionError


# ============================================================
# Categorias
# ============================================================

CATEGORY_CAREER = "carrera"
CATEGORY_MATCH = "hazana"
CATEGORY_SECRET = "secreto"
CATEGORY_EMOTION = "emocional"

ALL_CATEGORIES = {CATEGORY_CAREER, CATEGORY_MATCH, CATEGORY_SECRET, CATEGORY_EMOTION}

# Los 9 mood_tags posibles de la IA emocional
ALL_MOOD_TAGS = {
    "neutral", "relajado", "tenso", "irritado",
    "furioso", "deprimido", "aburrido", "euforico", "erratico",
}

# Metadatos visuales (iconos 24x24 proceduralmente generados)
TIER_INTERMEDIATE = "intermedio"
TIER_ADVANCED = "avanzado"
TIER_HIGH = "alto"
TIER_LEGENDARY = "legendario"

ALL_ACHIEVEMENT_TIERS = {
    TIER_INTERMEDIATE,
    TIER_ADVANCED,
    TIER_HIGH,
    TIER_LEGENDARY,
}

MOTIF_CASSETTE = "m01_cassette"
MOTIF_PADDLE_TROPHY = "m02_paddle_trophy"
MOTIF_SCORE_CHIP = "m03_score_chip"
MOTIF_RALLY_WAVE = "m04_rally_wave"
MOTIF_STREAK_CHAIN = "m05_streak_chain"
MOTIF_PERFECT_SEAL = "m06_perfect_seal"
MOTIF_SPEED_COMET = "m07_speed_comet"
MOTIF_42_SPIRAL = "m08_42_spiral"
MOTIF_DIALOG_BUBBLE = "m09_dialog_bubble"
MOTIF_BROKEN_HELMET = "m10_broken_helmet"
MOTIF_MONO_CRT = "m11_mono_crt"
MOTIF_FURY_CLAW = "m12_fury_claw"
MOTIF_SAD_DROP = "m13_sad_drop"
MOTIF_EUPHORIA_STAR = "m14_euphoria_star"
MOTIF_GLITCH_CHIP = "m15_glitch_chip"
MOTIF_SPECTRUM_WHEEL = "m16_spectrum_wheel"
MOTIF_BEAST_TAMER = "m17_beast_tamer"
MOTIF_NIGHT_MOON = "m18_night_moon"

ALL_ACHIEVEMENT_MOTIFS = {
    MOTIF_CASSETTE,
    MOTIF_PADDLE_TROPHY,
    MOTIF_SCORE_CHIP,
    MOTIF_RALLY_WAVE,
    MOTIF_STREAK_CHAIN,
    MOTIF_PERFECT_SEAL,
    MOTIF_SPEED_COMET,
    MOTIF_42_SPIRAL,
    MOTIF_DIALOG_BUBBLE,
    MOTIF_BROKEN_HELMET,
    MOTIF_MONO_CRT,
    MOTIF_FURY_CLAW,
    MOTIF_SAD_DROP,
    MOTIF_EUPHORIA_STAR,
    MOTIF_GLITCH_CHIP,
    MOTIF_SPECTRUM_WHEEL,
    MOTIF_BEAST_TAMER,
    MOTIF_NIGHT_MOON,
}

# achievement_id -> (tier, motif, icon_seed)
_ACHIEVEMENT_VISUAL_META = {
    # --- CARRERA ---
    "career_matches_1": (TIER_INTERMEDIATE, MOTIF_CASSETTE, 101),
    "career_matches_5": (TIER_INTERMEDIATE, MOTIF_CASSETTE, 102),
    "career_matches_10": (TIER_ADVANCED, MOTIF_CASSETTE, 103),
    "career_matches_25": (TIER_ADVANCED, MOTIF_CASSETTE, 104),
    "career_matches_50": (TIER_HIGH, MOTIF_CASSETTE, 105),
    "career_matches_100": (TIER_LEGENDARY, MOTIF_CASSETTE, 106),
    "career_wins_1": (TIER_INTERMEDIATE, MOTIF_PADDLE_TROPHY, 107),
    "career_wins_5": (TIER_INTERMEDIATE, MOTIF_PADDLE_TROPHY, 108),
    "career_wins_10": (TIER_ADVANCED, MOTIF_PADDLE_TROPHY, 109),
    "career_wins_25": (TIER_HIGH, MOTIF_PADDLE_TROPHY, 110),
    "career_wins_50": (TIER_LEGENDARY, MOTIF_PADDLE_TROPHY, 111),
    "career_pts_50": (TIER_INTERMEDIATE, MOTIF_SCORE_CHIP, 112),
    "career_pts_100": (TIER_ADVANCED, MOTIF_SCORE_CHIP, 113),
    "career_pts_500": (TIER_HIGH, MOTIF_SCORE_CHIP, 114),
    "career_pts_1000": (TIER_LEGENDARY, MOTIF_SCORE_CHIP, 115),
    "career_rallies_100": (TIER_INTERMEDIATE, MOTIF_RALLY_WAVE, 116),
    "career_rallies_500": (TIER_ADVANCED, MOTIF_RALLY_WAVE, 117),
    "career_rallies_1000": (TIER_LEGENDARY, MOTIF_RALLY_WAVE, 118),
    # --- HAZANA ---
    "rally_5": (TIER_INTERMEDIATE, MOTIF_RALLY_WAVE, 119),
    "rally_10": (TIER_INTERMEDIATE, MOTIF_RALLY_WAVE, 120),
    "rally_15": (TIER_ADVANCED, MOTIF_RALLY_WAVE, 121),
    "rally_25": (TIER_ADVANCED, MOTIF_RALLY_WAVE, 122),
    "rally_50": (TIER_HIGH, MOTIF_RALLY_WAVE, 123),
    "rally_100": (TIER_LEGENDARY, MOTIF_RALLY_WAVE, 124),
    "streak_3": (TIER_INTERMEDIATE, MOTIF_STREAK_CHAIN, 125),
    "streak_5": (TIER_ADVANCED, MOTIF_STREAK_CHAIN, 126),
    "perfect_game": (TIER_ADVANCED, MOTIF_PERFECT_SEAL, 127),
    "perfect_set": (TIER_HIGH, MOTIF_PERFECT_SEAL, 128),
    "perfect_match": (TIER_LEGENDARY, MOTIF_PERFECT_SEAL, 129),
    "comeback_set": (TIER_ADVANCED, MOTIF_PERFECT_SEAL, 130),
    "speed_180": (TIER_ADVANCED, MOTIF_SPEED_COMET, 131),
    "speed_120": (TIER_HIGH, MOTIF_SPEED_COMET, 132),
    # --- SECRETO ---
    "hitchhiker_42": (TIER_HIGH, MOTIF_42_SPIRAL, 133),
    "midnight_player": (TIER_INTERMEDIATE, MOTIF_NIGHT_MOON, 134),
    "all_si": (TIER_ADVANCED, MOTIF_DIALOG_BUBBLE, 135),
    "all_no": (TIER_ADVANCED, MOTIF_DIALOG_BUBBLE, 136),
    "all_duda": (TIER_ADVANCED, MOTIF_DIALOG_BUBBLE, 137),
    "total_defeat": (TIER_ADVANCED, MOTIF_BROKEN_HELMET, 138),
    "monochrome_win": (TIER_LEGENDARY, MOTIF_MONO_CRT, 139),
    # --- EMOCIONAL ---
    "mood_furioso": (TIER_ADVANCED, MOTIF_FURY_CLAW, 140),
    "mood_deprimido": (TIER_ADVANCED, MOTIF_SAD_DROP, 141),
    "mood_euforico": (TIER_ADVANCED, MOTIF_EUPHORIA_STAR, 142),
    "mood_erratico": (TIER_ADVANCED, MOTIF_GLITCH_CHIP, 143),
    "mood_all_9": (TIER_LEGENDARY, MOTIF_SPECTRUM_WHEEL, 144),
    "win_vs_furioso": (TIER_HIGH, MOTIF_BEAST_TAMER, 145),
}


# ============================================================
# Estructuras de datos
# ============================================================

@dataclass
class AchievementDef:
    """Definicion estatica de un logro.

    Atributos:
        id:          Clave unica (snake_case).
        name:        Nombre visible (espanol).
        description: Condicion legible (espanol, se oculta si hidden).
        flavor:      Texto humoristico ZX Spectrum (espanol).
        category:    Una de las 4 categorias.
        tier:        Rango visual (intermedio, avanzado, alto, legendario).
        motif:       Motivo visual base para el icono procedural 24x24.
        icon_seed:   Semilla deterministic para variaciones del motivo.
        hidden:      True para logros secretos (muestra "???" hasta desbloquear).
    """

    id: str
    name: str
    description: str
    flavor: str
    category: str
    tier: str
    motif: str
    icon_seed: int
    hidden: bool = False


@dataclass
class CareerStats:
    """Estadisticas acumuladas entre sesiones para logros de carrera.

    Se recalculan a partir de todas las sesiones (como compute_records),
    garantizando consistencia tras cualquier corrupcion.
    """

    total_matches: int = 0
    total_victories: int = 0
    total_points_scored: int = 0
    total_rallies: int = 0
    moods_experienced: set[str] = field(default_factory=set)


# ============================================================
# Catalogo de logros (45 logros en 4 categorias)
# ============================================================

def _build_achievement_defs() -> dict[str, AchievementDef]:
    """Construye el diccionario completo de definiciones de logros."""
    defs: dict[str, AchievementDef] = {}

    def _add(id_: str, name: str, desc: str, flavor: str, category: str, hidden: bool = False) -> None:
        visual_meta = _ACHIEVEMENT_VISUAL_META.get(id_)
        if visual_meta is None:
            raise AchievementDefinitionError(f"Faltan metadatos visuales para: {id_}")
        tier, motif, icon_seed = visual_meta
        defs[id_] = AchievementDef(
            id=id_, name=name, description=desc,
            flavor=flavor, category=category,
            tier=tier, motif=motif, icon_seed=icon_seed,
            hidden=hidden,
        )

    # --- CARRERA: Partidos jugados ---
    _add("career_matches_1", "Novato",
         "Juega tu primer partido",
         'Todo gran maestro empezo con un LOAD ""',
         CATEGORY_CAREER)
    _add("career_matches_5", "Habitual",
         "Juega 5 partidos",
         "El beeper ya te reconoce",
         CATEGORY_CAREER)
    _add("career_matches_10", "Veterano",
         "Juega 10 partidos",
         "48K de memoria muscular",
         CATEGORY_CAREER)
    _add("career_matches_25", "Adicto",
         "Juega 25 partidos",
         "Tu Spectrum se esta calentando",
         CATEGORY_CAREER)
    _add("career_matches_50", "Obsesivo",
         "Juega 50 partidos",
         "R Tape Loading Error? Nunca.",
         CATEGORY_CAREER)
    _add("career_matches_100", "Leyenda del Spectrum",
         "Juega 100 partidos",
         "Sir Clive estaria orgulloso",
         CATEGORY_CAREER)

    # --- CARRERA: Victorias ---
    _add("career_wins_1", "Primera Victoria",
         "Gana tu primer partido",
         "1-0 a tu favor. El ordenador no lo olvidara.",
         CATEGORY_CAREER)
    _add("career_wins_5", "Palista Competente",
         "Gana 5 partidos",
         "La paleta es una extension de tu brazo",
         CATEGORY_CAREER)
    _add("career_wins_10", "Domador de Bits",
         "Gana 10 partidos",
         "La IA empieza a temerte.",
         CATEGORY_CAREER)
    _add("career_wins_25", "Pesadilla Digital",
         "Gana 25 partidos",
         "El ordenador tiene pesadillas contigo",
         CATEGORY_CAREER)
    _add("career_wins_50", "Azote del Silicio",
         "Gana 50 partidos",
         "Los transistores tiemblan",
         CATEGORY_CAREER)

    # --- CARRERA: Puntos totales ---
    _add("career_pts_50", "Medio Centenar",
         "Anota 50 puntos en total",
         "50 pixeles que cruzaron la pantalla",
         CATEGORY_CAREER)
    _add("career_pts_100", "Centenario",
         "Anota 100 puntos en total",
         "Un siglo de rebotes",
         CATEGORY_CAREER)
    _add("career_pts_500", "Artillero",
         "Anota 500 puntos en total",
         "500 balas cuadradas",
         CATEGORY_CAREER)
    _add("career_pts_1000", "Kilopunto",
         "Anota 1000 puntos en total",
         "1K de puntos. Falta el otro 47K.",
         CATEGORY_CAREER)

    # --- CARRERA: Rallies acumulados ---
    _add("career_rallies_100", "Cien Rebotes",
         "Acumula 100 golpes de rally en tu carrera",
         "Toc, toc, toc...",
         CATEGORY_CAREER)
    _add("career_rallies_500", "Mecanografo",
         "Acumula 500 golpes de rally en tu carrera",
         "Click-clack como un teclado de goma",
         CATEGORY_CAREER)
    _add("career_rallies_1000", "Mil Rebotes",
         "Acumula 1000 golpes de rally en tu carrera",
         "El beeper pide tregua",
         CATEGORY_CAREER)

    # --- HAZANA: Rallies en un solo partido ---
    _add("rally_5", "Peloteo",
         "Rally de 5 golpes en un partido",
         "Calentamiento completado",
         CATEGORY_MATCH)
    _add("rally_10", "Intercambio Intenso",
         "Rally de 10 golpes en un partido",
         "La pelota empieza a sudar",
         CATEGORY_MATCH)
    _add("rally_15", "Maratoniano",
         "Rally de 15 golpes en un partido",
         "Esto ya no es Pong, es resistencia",
         CATEGORY_MATCH)
    _add("rally_25", "Eterno",
         "Rally de 25 golpes en un partido",
         "La pelota pide vacaciones",
         CATEGORY_MATCH)
    _add("rally_50", "Infinito",
         "Rally de 50 golpes en un partido",
         "El tiempo se detiene. Solo existe el rally.",
         CATEGORY_MATCH)
    _add("rally_100", "Singularidad",
         "Rally de 100 golpes en un partido",
         "Has creado un agujero negro de Pong",
         CATEGORY_MATCH)

    # --- HAZANA: Rachas ---
    _add("streak_3", "Triplete",
         "Racha de 3 puntos seguidos",
         "Tres en raya... de puntos",
         CATEGORY_MATCH)
    _add("streak_5", "Imparable",
         "Racha de 5 puntos seguidos",
         "Nadie puede pararte",
         CATEGORY_MATCH)

    # --- HAZANA: Juegos y sets perfectos ---
    _add("perfect_game", "Juego Perfecto",
         "Gana un juego 3-0",
         "Blanco perfecto",
         CATEGORY_MATCH)
    _add("perfect_set", "Set Impoluto",
         "Gana un set sin perder ningun juego",
         "Ni un juego cedido",
         CATEGORY_MATCH)
    _add("perfect_match", "Perfeccion Absoluta",
         "Gana sin perder un solo punto",
         "Error: puntos_perdidos == 0. Imposible.",
         CATEGORY_MATCH)
    _add("comeback_set", "Remontada",
         "Gana un set tras ir perdiendo en juegos",
         "Nunca digas nunca",
         CATEGORY_MATCH)

    # --- HAZANA: Velocidad ---
    _add("speed_180", "Relampago",
         "Gana en menos de 3 minutos",
         "Mas rapido que cargar un programa de cinta",
         CATEGORY_MATCH)
    _add("speed_120", "Centella",
         "Gana en menos de 2 minutos",
         "Ni el Spectrum arrancaba tan rapido",
         CATEGORY_MATCH)

    # --- SECRETO ---
    _add("hitchhiker_42", "La Respuesta",
         "???",
         "La respuesta a la vida, el universo y todo lo demas",
         CATEGORY_SECRET, hidden=True)
    _add("midnight_player", "Trasnochador",
         "???",
         "Los pixeles brillan mas a medianoche",
         CATEGORY_SECRET, hidden=True)
    _add("all_si", "El Optimista",
         "???",
         "Dices que si a todo. Hasta a la derrota.",
         CATEGORY_SECRET, hidden=True)
    _add("all_no", "El Nihilista",
         "???",
         "Nein. Nyet. No. Definitivamente no.",
         CATEGORY_SECRET, hidden=True)
    _add("all_duda", "El Indeciso",
         "???",
         "Ni si ni no sino todo lo contrario",
         CATEGORY_SECRET, hidden=True)
    _add("total_defeat", "Humillacion Total",
         "???",
         "Al menos tu Spectrum sigue funcionando",
         CATEGORY_SECRET, hidden=True)
    _add("monochrome_win", "Nostalgia Pura",
         "???",
         "Ganaste antes de que el Spectrum despertara",
         CATEGORY_SECRET, hidden=True)

    # --- EMOCIONAL ---
    _add("mood_furioso", "Bestia Desatada",
         "Enfurece a la IA hasta el modo furioso",
         "Has roto algo dentro del chip",
         CATEGORY_EMOTION)
    _add("mood_deprimido", "Alma Rota",
         "Deprime a la IA completamente",
         "Hasta los bytes pueden llorar",
         CATEGORY_EMOTION)
    _add("mood_euforico", "Euforia Digital",
         "Haz que la IA entre en euforia",
         "Los circuitos bailan de alegria",
         CATEGORY_EMOTION)
    _add("mood_erratico", "Cortocircuito",
         "Haz que la IA se vuelva erratica",
         "ERROR: comportamiento_indefinido",
         CATEGORY_EMOTION)
    _add("mood_all_9", "Espectro Completo",
         "Experimenta los 9 estados emocionales",
         "Has visto todos los colores del Spectrum",
         CATEGORY_EMOTION)
    _add("win_vs_furioso", "Domador de Fieras",
         "Gana con la IA en modo furioso",
         "Has domado a la bestia digital",
         CATEGORY_EMOTION)

    # Validacion para evitar metadatos obsoletos/no usados.
    extra_visuals = set(_ACHIEVEMENT_VISUAL_META) - set(defs)
    if extra_visuals:
        extras = ", ".join(sorted(extra_visuals))
        raise AchievementDefinitionError(f"IDs visuales sin definicion de logro: {extras}")

    return defs


def _validate_visual_meta_catalog() -> None:
    """Valida consistencia interna del catalogo visual de logros."""
    if len(_ACHIEVEMENT_VISUAL_META) != 45:
        raise AchievementDefinitionError(
            "El catalogo visual debe tener exactamente 45 logros "
            f"(tiene {len(_ACHIEVEMENT_VISUAL_META)})."
        )

    for achievement_id, (tier, motif, icon_seed) in _ACHIEVEMENT_VISUAL_META.items():
        if tier not in ALL_ACHIEVEMENT_TIERS:
            raise AchievementDefinitionError(
                f"Tier invalido para {achievement_id}: {tier!r}"
            )
        if motif not in ALL_ACHIEVEMENT_MOTIFS:
            raise AchievementDefinitionError(
                f"Motif invalido para {achievement_id}: {motif!r}"
            )
        if not isinstance(icon_seed, int) or icon_seed < 0:
            raise AchievementDefinitionError(
                f"icon_seed invalido para {achievement_id}: {icon_seed!r}"
            )


_validate_visual_meta_catalog()
ACHIEVEMENT_DEFS = _build_achievement_defs()

# Umbrales de carrera: (campo_career_stats, umbral, achievement_id)
_CAREER_THRESHOLDS = [
    ("total_matches", 1, "career_matches_1"),
    ("total_matches", 5, "career_matches_5"),
    ("total_matches", 10, "career_matches_10"),
    ("total_matches", 25, "career_matches_25"),
    ("total_matches", 50, "career_matches_50"),
    ("total_matches", 100, "career_matches_100"),
    ("total_victories", 1, "career_wins_1"),
    ("total_victories", 5, "career_wins_5"),
    ("total_victories", 10, "career_wins_10"),
    ("total_victories", 25, "career_wins_25"),
    ("total_victories", 50, "career_wins_50"),
    ("total_points_scored", 50, "career_pts_50"),
    ("total_points_scored", 100, "career_pts_100"),
    ("total_points_scored", 500, "career_pts_500"),
    ("total_points_scored", 1000, "career_pts_1000"),
    ("total_rallies", 100, "career_rallies_100"),
    ("total_rallies", 500, "career_rallies_500"),
    ("total_rallies", 1000, "career_rallies_1000"),
]

# Umbrales de rally: (umbral, achievement_id)
_RALLY_THRESHOLDS = [
    (5, "rally_5"),
    (10, "rally_10"),
    (15, "rally_15"),
    (25, "rally_25"),
    (50, "rally_50"),
    (100, "rally_100"),
]

# Umbrales de racha: (umbral, achievement_id)
_STREAK_THRESHOLDS = [
    (3, "streak_3"),
    (5, "streak_5"),
]

# Mood -> achievement_id para logros individuales de emociones
_MOOD_ACHIEVEMENTS = {
    "furioso": "mood_furioso",
    "deprimido": "mood_deprimido",
    "euforico": "mood_euforico",
    "erratico": "mood_erratico",
}


# ============================================================
# Motor principal
# ============================================================

class AchievementEngine:
    """Motor de logros autocontenido.

    Atributos:
        definitions:           dict[str, AchievementDef] catalogo completo.
        unlocked:              dict[str, dict] logros desbloqueados.
        career_stats:          CareerStats acumulados entre sesiones.
        pending_notifications: list[AchievementDef] cola FIFO de popups.
    """

    def __init__(self) -> None:
        self.definitions: dict[str, AchievementDef] = ACHIEVEMENT_DEFS
        self.unlocked: dict[str, dict[str, Any]] = {}
        self.career_stats: CareerStats = CareerStats()
        self.pending_notifications: list[AchievementDef] = []
        self._notification_start_time: float | None = None

        # Estado transitorio del partido actual
        self._match_moods_seen: set[str] = set()
        self._computer_led_in_set = False

    # --------------------------------------------------------
    # Persistencia
    # --------------------------------------------------------

    def load_from_history(self, history: dict[str, Any]) -> None:
        """Carga logros y career_stats desde el dict de game_history.json.

        Si el historial no contiene logros (version anterior), recalcula
        career_stats y concede retroactivamente los logros de carrera.
        """
        saved_achievements = history.get("achievements", {})
        saved_career = history.get("career_stats", {})
        sessions = history.get("sessions", [])

        # Restaurar logros desbloqueados
        self.unlocked = dict(saved_achievements)

        # Restaurar o recalcular career_stats
        if saved_career:
            self.career_stats = CareerStats(
                total_matches=saved_career.get("total_matches", 0),
                total_victories=saved_career.get("total_victories", 0),
                total_points_scored=saved_career.get("total_points_scored", 0),
                total_rallies=saved_career.get("total_rallies", 0),
                moods_experienced=set(saved_career.get("moods_experienced", [])),
            )
        elif sessions:
            # Primera carga tras upgrade: recalcular desde sesiones
            self.career_stats = self.recompute_career_stats(sessions)
            # Conceder logros de carrera retroactivamente
            self._check_career(len(sessions) - 1)

    def recompute_career_stats(self, sessions: list[dict[str, Any]]) -> CareerStats:
        """Recalcula CareerStats desde cero a partir de todas las sesiones."""
        stats = CareerStats()
        for session in sessions:
            stats.total_matches += 1
            if session.get("winner") == "jugador":
                stats.total_victories += 1
            stats.total_points_scored += session.get("player_points_total", 0)
            stats.total_rallies += session.get("max_rally", 0)
        return stats

    def get_save_data(self) -> dict[str, dict[str, Any]]:
        """Devuelve dict de logros para persistir en JSON."""
        return dict(self.unlocked)

    def get_career_stats_data(self) -> dict[str, Any]:
        """Devuelve dict de career_stats para persistir en JSON."""
        return {
            "total_matches": self.career_stats.total_matches,
            "total_victories": self.career_stats.total_victories,
            "total_points_scored": self.career_stats.total_points_scored,
            "total_rallies": self.career_stats.total_rallies,
            "moods_experienced": sorted(self.career_stats.moods_experienced),
        }

    # --------------------------------------------------------
    # Ciclo de vida del partido
    # --------------------------------------------------------

    def start_match(self) -> None:
        """Resetea el estado transitorio al inicio de un partido."""
        self._match_moods_seen = set()
        self._computer_led_in_set = False

    def record_mood(self, mood_tag: str | None) -> None:
        """Registra un mood_tag observado durante el partido actual."""
        if mood_tag:
            self._match_moods_seen.add(mood_tag)
            self.career_stats.moods_experienced.add(mood_tag)

    # --------------------------------------------------------
    # Desbloqueo
    # --------------------------------------------------------

    def _unlock(self, achievement_id: str, session_index: int) -> bool:
        """Desbloquea un logro si no lo estaba ya.

        Returns:
            True si es un desbloqueo nuevo.
        """
        if achievement_id in self.unlocked:
            return False
        if achievement_id not in self.definitions:
            return False

        self.unlocked[achievement_id] = {
            "date": datetime.now().isoformat(timespec="seconds"),
            "session_index": session_index,
        }
        self.pending_notifications.append(self.definitions[achievement_id])
        return True

    # --------------------------------------------------------
    # Comprobacion en tiempo real (durante gameplay)
    # --------------------------------------------------------

    def check_rally(self, rally_hits: int, max_rally_hits: int) -> list[str]:
        """Comprueba logros de rally (llamar tras cada golpe de paleta).

        Args:
            rally_hits: golpes en el rally actual.
            max_rally_hits: maximo de golpes en cualquier rally de la partida.

        Returns:
            list[str] de IDs de logros recien desbloqueados.
        """
        newly = []
        idx = -1

        for threshold, aid in _RALLY_THRESHOLDS:
            if max_rally_hits >= threshold and self._unlock(aid, idx):
                newly.append(aid)

        if rally_hits == 42 and self._unlock("hitchhiker_42", idx):
            newly.append("hitchhiker_42")

        return newly

    def check_mood(self, mood_tag: str | None) -> list[str]:
        """Comprueba logros emocionales (llamar tras cada cambio de mood).

        Args:
            mood_tag: etiqueta del mood actual.

        Returns:
            list[str] de IDs de logros recien desbloqueados.
        """
        newly = []
        idx = -1

        if mood_tag and mood_tag in _MOOD_ACHIEVEMENTS:
            aid = _MOOD_ACHIEVEMENTS[mood_tag]
            if self._unlock(aid, idx):
                newly.append(aid)

        if len(self.career_stats.moods_experienced) >= len(ALL_MOOD_TAGS):
            if self._unlock("mood_all_9", idx):
                newly.append("mood_all_9")

        return newly

    def check_realtime(self, context: dict[str, Any]) -> list[str]:
        """Comprueba logros que se activan al marcar un punto.

        Delega rally y mood a sus metodos especificos (idempotente por
        si aun no se dispararon) y comprueba logros que requieren
        point_result (racha, juego perfecto, remontada).

        Args:
            context: dict con claves:
                rally_hits, max_rally_hits, score (ScoreState),
                point_result (PointResult), pre_player_pts, pre_computer_pts,
                mood_tag, elapsed_seconds, dialogue_history, winner.

        Returns:
            list[str] de IDs de logros recien desbloqueados.
        """
        newly = []

        # Delegar a metodos especificos (idempotente: _unlock ignora duplicados)
        newly.extend(self.check_rally(
            context.get("rally_hits", 0),
            context.get("max_rally_hits", 0),
        ))
        newly.extend(self.check_mood(context.get("mood_tag")))

        point_result = context.get("point_result")
        winner = context.get("winner")

        # --- Streak achievements ---
        if point_result and winner == "player":
            idx = -1
            streak = point_result.scoring_streak
            for threshold, aid in _STREAK_THRESHOLDS:
                if streak >= threshold and self._unlock(aid, idx):
                    newly.append(aid)

        # --- Perfect game: ganar un juego con 0 puntos del rival ---
        if point_result and point_result.game_won and winner == "player":
            pre_computer_pts = context.get("pre_computer_pts", -1)
            if pre_computer_pts == 0 and self._unlock("perfect_game", -1):
                newly.append("perfect_game")

        # --- Comeback: computer lidera en juegos y luego player gana set ---
        score = context.get("score")
        if score and score.computer_games > score.player_games:
            self._computer_led_in_set = True

        if (
            point_result
            and point_result.set_won
            and winner == "player"
            and self._computer_led_in_set
        ):
            if self._unlock("comeback_set", -1):
                newly.append("comeback_set")

        # Reset comeback tracking on new set
        if point_result and point_result.set_won:
            self._computer_led_in_set = False

        return newly

    # --------------------------------------------------------
    # Comprobacion post-partido (al guardar)
    # --------------------------------------------------------

    def check_post_match(self, session_data: dict[str, Any], session_index: int) -> list[str]:
        """Comprueba logros de carrera y de fin de partido.

        Actualiza career_stats y luego comprueba todos los umbrales.

        Args:
            session_data: dict con los datos de la sesion.
            session_index: indice que tendra la sesion en el historial.

        Returns:
            list[str] de IDs de logros recien desbloqueados.
        """
        newly = []

        # Actualizar career_stats
        self.career_stats.total_matches += 1
        is_player_win = session_data.get("winner") == "jugador"
        if is_player_win:
            self.career_stats.total_victories += 1
        self.career_stats.total_points_scored += session_data.get(
            "player_points_total", 0
        )
        self.career_stats.total_rallies += session_data.get("max_rally", 0)

        # --- Career thresholds ---
        newly.extend(self._check_career(session_index))

        # --- Match feats (post-match) ---
        newly.extend(self._check_match_feats(session_data, session_index))

        # --- Secret achievements ---
        newly.extend(self._check_secrets(session_data, session_index))

        # --- Emotion achievements (post-match) ---
        newly.extend(self._check_emotions(session_data, session_index))

        # Actualizar session_index de logros desbloqueados en realtime
        # que tenian idx=-1 provisional
        for aid, data in self.unlocked.items():
            if data.get("session_index") == -1:
                data["session_index"] = session_index

        return newly

    def _check_career(self, session_index: int) -> list[str]:
        """Comprueba umbrales de carrera contra career_stats."""
        newly = []
        for field_name, threshold, aid in _CAREER_THRESHOLDS:
            value = getattr(self.career_stats, field_name, 0)
            if value >= threshold and self._unlock(aid, session_index):
                newly.append(aid)
        return newly

    def _check_match_feats(self, session_data: dict[str, Any], session_index: int) -> list[str]:
        """Comprueba logros de hazana basados en datos finales."""
        newly = []
        is_player_win = session_data.get("winner") == "jugador"

        # --- Perfect set: ganar set sin perder juegos ---
        # En el formato actual (1 set por partido), si el jugador gana
        # y computer_games == 0, fue un set perfecto.
        if is_player_win and session_data.get("computer_games", 1) == 0:
            if self._unlock("perfect_set", session_index):
                newly.append("perfect_set")

        # --- Perfect match: ganar sin perder un solo punto ---
        if is_player_win and session_data.get("computer_points_total", 1) == 0:
            if self._unlock("perfect_match", session_index):
                newly.append("perfect_match")

        # --- Speed achievements ---
        if is_player_win:
            elapsed = session_data.get("elapsed_seconds", 9999)
            if elapsed < 180 and self._unlock("speed_180", session_index):
                newly.append("speed_180")
            if elapsed < 120 and self._unlock("speed_120", session_index):
                newly.append("speed_120")

        return newly

    def _check_secrets(self, session_data: dict[str, Any], session_index: int) -> list[str]:
        """Comprueba logros secretos basados en condiciones especiales."""
        newly = []

        # --- Midnight player: jugar entre 00:00 y 04:59 ---
        now = datetime.now()
        if now.hour < 5:
            if self._unlock("midnight_player", session_index):
                newly.append("midnight_player")

        # --- Monochrome win: ganar antes de 30 segundos ---
        is_player_win = session_data.get("winner") == "jugador"
        elapsed = session_data.get("elapsed_seconds", 9999)
        if is_player_win and elapsed < 30:
            if self._unlock("monochrome_win", session_index):
                newly.append("monochrome_win")

        # --- Total defeat: perder con 0 puntos totales ---
        if (
            not is_player_win
            and session_data.get("player_points_total", 1) == 0
        ):
            if self._unlock("total_defeat", session_index):
                newly.append("total_defeat")

        # --- All Si / All No / All Duda ---
        # dialogue_history se analiza desde los datos del match
        # Nota: estos datos no se guardan en session_data, se comprueban
        # en check_realtime_dialogue al final del partido si se pasan
        # por contexto. Pero para robustez, tambien los comprobamos
        # desde el contexto del match si se ha pasado.

        return newly

    def check_dialogue_achievements(self, dialogue_history: list[Any], session_index: int) -> list[str]:
        """Comprueba logros basados en las respuestas del dialogo.

        Se llama al final de la partida con el historial completo de dialogo.

        Args:
            dialogue_history: lista de DialogueEntry con .answer.
            session_index: indice de la sesion.

        Returns:
            list[str] de IDs de logros recien desbloqueados.
        """
        newly: list[str] = []
        if len(dialogue_history) < 3:
            return newly

        answers = [entry.answer for entry in dialogue_history]

        if all(a == "Si" for a in answers):
            if self._unlock("all_si", session_index):
                newly.append("all_si")
        if all(a == "No" for a in answers):
            if self._unlock("all_no", session_index):
                newly.append("all_no")
        if all(a == "Duda" for a in answers):
            if self._unlock("all_duda", session_index):
                newly.append("all_duda")

        return newly

    def _check_emotions(self, session_data: dict[str, Any], session_index: int) -> list[str]:
        """Comprueba logros emocionales al final del partido."""
        newly = []
        is_player_win = session_data.get("winner") == "jugador"

        # --- Win vs furioso: ganar habiendo visto "furioso" ---
        if is_player_win and "furioso" in self._match_moods_seen:
            if self._unlock("win_vs_furioso", session_index):
                newly.append("win_vs_furioso")

        return newly

    # --------------------------------------------------------
    # Gestion de notificaciones
    # --------------------------------------------------------

    def has_notifications(self) -> bool:
        """True si hay notificaciones pendientes."""
        return len(self.pending_notifications) > 0

    def peek_notification(self) -> AchievementDef | None:
        """Devuelve la siguiente notificacion sin consumirla, o None."""
        if self.pending_notifications:
            return self.pending_notifications[0]
        return None

    def advance_notification(self) -> None:
        """Consume la notificacion actual y resetea el timer."""
        if self.pending_notifications:
            self.pending_notifications.pop(0)
        self._notification_start_time = None

    def get_notification_start(self) -> float | None:
        """Devuelve el timestamp de inicio de la notificacion actual."""
        return self._notification_start_time

    def set_notification_start(self, t: float | None) -> None:
        """Establece el timestamp de inicio de la notificacion actual."""
        self._notification_start_time = t

    # --------------------------------------------------------
    # Consulta
    # --------------------------------------------------------

    def count_unlocked(self) -> int:
        """Numero de logros desbloqueados."""
        return len(self.unlocked)

    def count_total(self) -> int:
        """Numero total de logros definidos."""
        return len(self.definitions)

    def is_unlocked(self, achievement_id: str) -> bool:
        """True si el logro esta desbloqueado."""
        return achievement_id in self.unlocked
