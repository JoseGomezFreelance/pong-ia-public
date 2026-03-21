"""
Persistencia de partidas y calculo de records.

Guarda el historial de sesiones en un archivo JSON local
(saves/game_history.json) y calcula los 5 mejores records
a partir de todas las sesiones almacenadas.
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


# ============================================================
# Rutas de almacenamiento
# ============================================================

def _resolve_save_dir() -> Path:
    """Directorio de saves junto al .app/.exe o en la raiz del proyecto."""
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        if exe_dir.name == "MacOS" and exe_dir.parent.name == "Contents":
            return exe_dir.parent.parent.parent / "saves"
        return exe_dir / "saves"
    return Path("saves")


SAVE_DIR = _resolve_save_dir()
SAVE_FILE = SAVE_DIR / "game_history.json"

# ============================================================
# Categorias de records
# ============================================================
RECORD_CATEGORIES = [
    ("max_score", "Mayor puntuacion"),
    ("fastest_win", "Victoria mas rapida"),
    ("longest_rally", "Rally mas largo"),
    ("longest_streak", "Racha imparable"),
    ("biggest_domination", "Victoria mas dominante"),
]


def _empty_history() -> dict[str, Any]:
    """Devuelve la estructura base de un historial vacio."""
    return {
        "version": "1.2",
        "sessions": [],
        "records": {},
        "achievements": {},
        "career_stats": {},
        "phases_unlocked": {},
    }


def load_history() -> dict[str, Any]:
    """
    Carga el historial desde disco.

    Returns:
        dict con claves "version", "sessions" y "records".
    """
    if not SAVE_FILE.exists():
        return _empty_history()
    try:
        with open(SAVE_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict) or "sessions" not in data:
            return _empty_history()
        # Migracion: asegurar que existan las claves de logros
        if "achievements" not in data:
            data["achievements"] = {}
        if "career_stats" not in data:
            data["career_stats"] = {}
        if "phases_unlocked" not in data:
            data["phases_unlocked"] = {}
        return data
    except (json.JSONDecodeError, OSError):
        return _empty_history()


def _write_history(history: dict[str, Any]) -> None:
    """Escribe el historial completo a disco."""
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    with open(SAVE_FILE, "w", encoding="utf-8") as fh:
        json.dump(history, fh, ensure_ascii=False, indent=2)


def compute_records(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Recalcula los 5 records a partir de todas las sesiones.

    Para cada categoria, almacena el mejor valor, el indice
    de la sesion y la fecha.

    Returns:
        dict con una clave por categoria.
    """
    records: dict[str, Any] = {}

    for idx, session in enumerate(sessions):
        date = session.get("date", "")
        winner = session.get("winner", "")
        is_player_win = winner == "jugador"

        # --- Mayor puntuacion ---
        pts = session.get("player_points_total", 0)
        prev = records.get("max_score")
        if prev is None or pts > prev["value"]:
            records["max_score"] = {
                "value": pts, "session_index": idx, "date": date,
            }

        # --- Victoria mas rapida (solo victorias del jugador) ---
        if is_player_win:
            elapsed = session.get("elapsed_seconds", 0)
            prev = records.get("fastest_win")
            if prev is None or elapsed < prev["value"]:
                records["fastest_win"] = {
                    "value": elapsed, "session_index": idx, "date": date,
                }

        # --- Rally mas largo ---
        rally = session.get("max_rally", 0)
        prev = records.get("longest_rally")
        if prev is None or rally > prev["value"]:
            records["longest_rally"] = {
                "value": rally, "session_index": idx, "date": date,
            }

        # --- Racha imparable ---
        streak = session.get("longest_player_streak", 0)
        prev = records.get("longest_streak")
        if prev is None or streak > prev["value"]:
            records["longest_streak"] = {
                "value": streak, "session_index": idx, "date": date,
            }

        # --- Victoria mas dominante (solo victorias) ---
        if is_player_win:
            diff = session.get("point_differential", 0)
            prev = records.get("biggest_domination")
            if prev is None or diff > prev["value"]:
                records["biggest_domination"] = {
                    "value": diff, "session_index": idx, "date": date,
                }

    return records


def check_phase_unlocks(history: dict[str, Any]) -> list[str]:
    """
    Comprueba si se desbloquean nuevas fases por tiempo total jugado.

    Args:
        history: dict completo de game_history.json (via load_history()).

    Returns:
        list de claves de fases recien desbloqueadas.
    """
    from pong.config.media import IMAGEGEN_UNLOCK_TOTAL_SECONDS

    sessions = history.get("sessions", [])
    total_time = sum(s.get("elapsed_seconds", 0) for s in sessions)
    phases = history.get("phases_unlocked", {})

    newly_unlocked = []
    if total_time >= IMAGEGEN_UNLOCK_TOTAL_SECONDS and "imagegen" not in phases:
        phases["imagegen"] = {
            "unlocked_at": datetime.now().isoformat(timespec="seconds"),
            "total_time_at_unlock": total_time,
        }
        newly_unlocked.append("imagegen")

    history["phases_unlocked"] = phases
    return newly_unlocked


def save_session(
    session_data: dict[str, Any],
    achievements: dict[str, Any] | None = None,
    career_stats: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """
    Anade una sesion al historial, recalcula records y persiste.

    Args:
        session_data:  dict con los datos de la partida.
        achievements:  dict de logros desbloqueados (opcional, del AchievementEngine).
        career_stats:  dict de estadisticas de carrera (opcional, del AchievementEngine).

    Returns:
        tuple (records, new_record_keys):
            records:         dict completo de records actualizado.
            new_record_keys: list de claves donde la sesion actual
                             establecio un nuevo record.
    """
    history = load_history()
    session_data["date"] = datetime.now().isoformat(timespec="seconds")
    history["sessions"].append(session_data)

    new_index = len(history["sessions"]) - 1
    records = compute_records(history["sessions"])
    history["records"] = records

    # Persistir logros y estadisticas de carrera si se proveen
    if achievements is not None:
        history["achievements"] = achievements
    if career_stats is not None:
        history["career_stats"] = career_stats

    # Comprobar desbloqueo de fases por tiempo total jugado
    newly_unlocked_phases = check_phase_unlocks(history)

    _write_history(history)

    new_record_keys = [
        key for key, rec in records.items()
        if rec["session_index"] == new_index
    ]

    return records, new_record_keys, newly_unlocked_phases


def format_record_value(key: str, value: int | float) -> str:
    """
    Formatea el valor de un record para mostrarlo en la UI.

    Args:
        key:   Clave de la categoria (e.g. "max_score").
        value: Valor numerico del record.

    Returns:
        str formateado.
    """
    if key == "fastest_win":
        mins = int(value) // 60
        secs = int(value) % 60
        return f"{mins}:{secs:02d}"
    if key == "longest_rally":
        return f"{int(value)} golpes"
    if key == "biggest_domination":
        return f"+{int(value)} pts"
    # max_score, longest_streak
    return f"{int(value)} pts"


def format_record_date(date_str: str) -> str:
    """
    Convierte una fecha ISO a formato corto dd/mm/yyyy.

    Args:
        date_str: Fecha en formato ISO 8601.

    Returns:
        str en formato dd/mm/yyyy, o "—" si no se puede parsear.
    """
    try:
        dt = datetime.fromisoformat(date_str)
        return dt.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return "\u2014"


def compute_derived_stats(history: dict[str, Any]) -> dict[str, Any]:
    """
    Calcula estadisticas derivadas para la pantalla de Estadisticas y Logros.

    Combina career_stats, records y datos calculados de las sesiones
    en un unico dict listo para renderizar.

    Args:
        history: dict completo de game_history.json (via load_history()).

    Returns:
        dict con todas las estadisticas formateadas.
    """
    sessions = history.get("sessions", [])
    career = history.get("career_stats", {})
    records = history.get("records", {})

    total_matches = career.get("total_matches", len(sessions))
    total_victories = career.get("total_victories", 0)
    total_defeats = total_matches - total_victories
    win_rate = int(total_victories / total_matches * 100) if total_matches else 0

    total_points = career.get("total_points_scored", 0)
    total_rallies = career.get("total_rallies", 0)
    total_computer_points = sum(
        s.get("computer_points_total", 0) for s in sessions
    )
    total_time = sum(s.get("elapsed_seconds", 0) for s in sessions)
    longest_match = max(
        (s.get("elapsed_seconds", 0) for s in sessions), default=0,
    )

    moods = career.get("moods_experienced", [])
    if isinstance(moods, set):
        moods = sorted(moods)

    # Formatear records (con fallback "—" si no existen)
    def _rec(key: str) -> str:
        rec = records.get(key)
        if rec is None:
            return "\u2014"
        return format_record_value(key, rec["value"])

    return {
        # General
        "total_matches": total_matches,
        "total_victories": total_victories,
        "total_defeats": total_defeats,
        "win_rate": win_rate,
        "total_points": total_points,
        "total_computer_points": total_computer_points,
        "total_rallies": total_rallies,
        "total_time": total_time,
        "longest_match": longest_match,
        # Records
        "rec_longest_rally": _rec("longest_rally"),
        "rec_longest_streak": _rec("longest_streak"),
        "rec_max_score": _rec("max_score"),
        "rec_fastest_win": _rec("fastest_win"),
        "rec_biggest_domination": _rec("biggest_domination"),
        # Emocional
        "moods_experienced": moods,
        "moods_total": 9,
    }


def _format_time(seconds: int | float) -> str:
    """Formatea segundos en M:SS o H:MM:SS."""
    total = int(seconds)
    if total >= 3600:
        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60
        return f"{h}:{m:02d}:{s:02d}"
    m = total // 60
    s = total % 60
    return f"{m}:{s:02d}"


def open_saves_folder() -> None:
    """Abre la carpeta de guardados con el explorador de archivos del SO."""
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    folder = str(SAVE_DIR.resolve())
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.Popen(["open", folder])
        elif system == "Windows":
            subprocess.Popen(["explorer", folder])
        else:
            subprocess.Popen(["xdg-open", folder])
    except OSError:
        pass
