"""
Persistencia de partidas y calculo de records.

Guarda el historial de sesiones en un archivo JSON local
(saves/game_history.json) y calcula los 5 mejores records
a partir de todas las sesiones almacenadas.
"""

from __future__ import annotations

import base64
import hashlib
import hmac as hmac_mod
import json
import os
import platform
import subprocess
import sys
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any


# ============================================================
# Rutas de almacenamiento
# ============================================================

def _resolve_save_dir() -> Path:
    """Directorio de saves en Application Support (frozen) o en el proyecto."""
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support" / "PongIA"
        else:
            import os
            base = Path(os.environ.get("APPDATA", Path.home())) / "PongIA"
        return base / "saves"
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

# ============================================================
# Integridad criptografica
# ============================================================
_CHAIN_GENESIS = "genesis"
_HMAC_SALT = b"PongIA-save-integrity-v1"
_CURRENT_VERSION = "1.4"
_FINGERPRINT_HEX_LEN = 16


def _get_platform_uuid() -> str:
    """Obtiene el UUID de placa base (SMBIOS) del sistema operativo."""
    try:
        if sys.platform == "darwin":
            out = subprocess.check_output(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                text=True, timeout=5,
            )
            for line in out.splitlines():
                if "IOPlatformUUID" in line:
                    return line.split('"')[-2]
        elif sys.platform == "win32":
            # Intentar wmic primero (rapido), fallback a PowerShell
            # wmic puede no estar disponible en bundles PyInstaller
            for cmd in (
                ["wmic", "csproduct", "get", "uuid"],
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance -ClassName Win32_ComputerSystemProduct).UUID"],
            ):
                try:
                    out = subprocess.check_output(
                        cmd, text=True, timeout=10,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    for line in out.splitlines():
                        stripped = line.strip()
                        if stripped and stripped != "UUID":
                            return stripped
                except (subprocess.SubprocessError, OSError):
                    continue
        elif sys.platform.startswith("linux"):
            # /etc/machine-id es estandar systemd, legible por cualquier usuario.
            # Fallback a /var/lib/dbus/machine-id (sistemas no-systemd viejos).
            for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        machine_id = fh.read().strip()
                    if machine_id:
                        return machine_id
                except OSError:
                    continue
    except (subprocess.SubprocessError, OSError):
        pass
    raise RuntimeError(
        "No se pudo obtener el UUID de placa base. "
        "La integridad de los archivos de guardado requiere este identificador."
    )


def _derive_machine_key() -> bytes:
    """Deriva una clave unica a partir del UUID de placa base."""
    hw_id = _get_platform_uuid().encode("utf-8")
    return hashlib.sha256(_HMAC_SALT + hw_id).digest()


def derive_machine_key() -> bytes:
    """API publica para obtener la clave derivada del hardware."""
    return _derive_machine_key()


def _canonical_session(session: dict[str, Any]) -> str:
    """JSON determinista de una sesion, excluyendo _chain_hash."""
    filtered = {k: v for k, v in session.items() if k != "_chain_hash"}
    return json.dumps(filtered, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _compute_chain_hash(previous_hash: str, session: dict[str, Any]) -> str:
    """Calcula el SHA-256 encadenado para una sesion."""
    payload = previous_hash + "|" + _canonical_session(session)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _rebuild_chain(sessions: list[dict[str, Any]]) -> None:
    """Recalcula _chain_hash para todas las sesiones in-place."""
    prev = _CHAIN_GENESIS
    for session in sessions:
        session.pop("_chain_hash", None)
        h = _compute_chain_hash(prev, session)
        session["_chain_hash"] = h
        prev = h


def _validate_chain(sessions: list[dict[str, Any]]) -> bool:
    """Retorna True si la cadena de hashes esta intacta."""
    prev = _CHAIN_GENESIS
    for session in sessions:
        expected = _compute_chain_hash(prev, session)
        if session.get("_chain_hash") != expected:
            return False
        prev = session["_chain_hash"]
    return True


def _compute_hmac(history: dict[str, Any]) -> str:
    """Calcula HMAC-SHA256 del historial (excluyendo _hmac e _integrity)."""
    key = _derive_machine_key()
    filtered = {k: v for k, v in history.items() if k not in ("_hmac", "_integrity")}
    payload = json.dumps(filtered, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hmac_mod.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _verify_hmac(history: dict[str, Any]) -> bool:
    """Retorna True si el HMAC almacenado coincide con el calculado."""
    stored = history.get("_hmac")
    if stored is None:
        return False
    return hmac_mod.compare_digest(stored, _compute_hmac(history))


def _clear_p2p_validation_state(history: dict[str, Any], profile: dict[str, str]) -> None:
    """Limpia validaciones P2P que dejan de ser fiables tras cambiar la identidad."""
    profile.pop("validated_suffix", None)
    profile.pop("validated_date", None)
    history["p2p_backup"] = []


def _empty_history() -> dict[str, Any]:
    """Devuelve la estructura base de un historial vacio."""
    return {
        "version": _CURRENT_VERSION,
        "sessions": [],
        "records": {},
        "achievements": {},
        "career_stats": {},
        "phases_unlocked": {},
        "rpg": {},
        "player_profile": {},
    }


def _apply_owner_only_permissions(path: Path) -> None:
    """Restringe el fichero al usuario actual en POSIX.

    En Windows o si ``chmod`` falla, se degrada sin romper el flujo.
    """
    if os.name != "posix":
        return
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _write_json_secure(
    path: Path,
    data: Any,
    *,
    ensure_ascii: bool = False,
    indent: int = 2,
) -> None:
    """Escribe JSON y aplica permisos owner-only en best-effort."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=ensure_ascii, indent=indent)
    _apply_owner_only_permissions(path)


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
        if "rpg" not in data:
            data["rpg"] = {}
        if "player_profile" not in data:
            data["player_profile"] = {}

        # Migracion: v1.3 -> v1.4 (integridad criptografica)
        # Desactivada: un archivo v1.3 fabricado podria inyectar progreso
        # falso que se firmaria como legitimo. No se admiten archivos sin
        # firma: se descartan y se empieza de cero.
        # if data.get("version", "1.0") < _CURRENT_VERSION:
        #     _rebuild_chain(data.get("sessions", []))
        #     data["version"] = _CURRENT_VERSION

        # Validacion de integridad: solo se aceptan archivos firmados
        # correctamente. Cualquier fallo descarta el archivo completo.
        if not _verify_hmac(data):
            if "_hmac" in data:
                warnings.warn(
                    "PongIA: HMAC no coincide — el archivo de guardado "
                    "ha sido manipulado o transferido. "
                    "Se inicia un historial nuevo.",
                    stacklevel=2,
                )
            else:
                warnings.warn(
                    "PongIA: Archivo de guardado sin firma. "
                    "Se inicia un historial nuevo.",
                    stacklevel=2,
                )
            return _empty_history()

        if data.get("sessions") and not _validate_chain(data["sessions"]):
            warnings.warn(
                "PongIA: Cadena de hashes rota — el historial de sesiones "
                "ha sido manipulado. Se inicia un historial nuevo.",
                stacklevel=2,
            )
            return _empty_history()

        profile = data.get("player_profile", {})
        profile, profile_changed, identity_changed = _normalize_p2p_profile(profile)
        persisted_change = False
        if profile_changed:
            data["player_profile"] = profile
            persisted_change = True
        if identity_changed:
            _clear_p2p_validation_state(data, profile)
            persisted_change = True
        if persisted_change:
            _write_history(data)

        return data
    except (json.JSONDecodeError, OSError):
        return _empty_history()


def _write_history(history: dict[str, Any]) -> None:
    """Escribe el historial completo a disco, con firma HMAC.

    La signing_key nunca se escribe en plano — solo signing_key_enc.
    """
    import copy

    to_write = {k: v for k, v in history.items() if k != "_integrity"}
    to_write["version"] = _CURRENT_VERSION

    # Proteger signing_key: cifrar antes de escribir, eliminar plano
    profile = to_write.get("player_profile")
    if isinstance(profile, dict) and profile.get("signing_key"):
        profile = copy.copy(profile)
        _encrypt_signing_key_in_profile(profile)
        profile.pop("signing_key", None)
        to_write["player_profile"] = profile

    to_write.pop("_hmac", None)
    to_write["_hmac"] = _compute_hmac(to_write)
    _write_json_secure(SAVE_FILE, to_write, ensure_ascii=False, indent=2)


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
    from pong.config.rpg import RPG_UNLOCK_TOTAL_SECONDS

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

    if total_time >= RPG_UNLOCK_TOTAL_SECONDS and "rpg" not in phases:
        phases["rpg"] = {
            "unlocked_at": datetime.now().isoformat(timespec="seconds"),
            "total_time_at_unlock": total_time,
        }
        # Marcar rpg_unlocked en el estado RPG persistente
        rpg_data = history.get("rpg", {})
        rpg_data["rpg_unlocked"] = True
        history["rpg"] = rpg_data
        newly_unlocked.append("rpg")

    history["phases_unlocked"] = phases
    return newly_unlocked


def save_session(
    session_data: dict[str, Any],
    achievements: dict[str, Any] | None = None,
    career_stats: dict[str, Any] | None = None,
    rpg_data: dict[str, Any] | None = None,
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

    # Calcular hash de cadena para la nueva sesion
    sessions = history["sessions"]
    if len(sessions) == 1:
        prev_hash = _CHAIN_GENESIS
    else:
        prev_hash = sessions[-2].get("_chain_hash", _CHAIN_GENESIS)
    session_data["_chain_hash"] = _compute_chain_hash(prev_hash, session_data)

    new_index = len(history["sessions"]) - 1
    records = compute_records(history["sessions"])
    history["records"] = records

    # Persistir logros y estadisticas de carrera si se proveen
    if achievements is not None:
        history["achievements"] = achievements
    if career_stats is not None:
        history["career_stats"] = career_stats
    if rpg_data is not None:
        history["rpg"] = rpg_data

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


# ============================================================
# Perfil de jugador (alias + fingerprint para rankings P2P)
# ============================================================

_APP_SIGNING_SALT = b"PongIA-leaderboard-sign-v1"


def _compute_fingerprint(verify_key_hex: str) -> str:
    """Deriva un fingerprint P2P estable a partir de la clave publica Ed25519."""
    try:
        verify_key_bytes = bytes.fromhex(verify_key_hex)
    except (TypeError, ValueError):
        return ""
    if len(verify_key_bytes) != 32:
        return ""
    return hashlib.sha256(verify_key_bytes).hexdigest()[:_FINGERPRINT_HEX_LEN]


def compute_app_signing_key() -> bytes:
    """Clave de firma HMAC legacy (solo para integridad local del save file).

    No usar para firmar entries P2P — usar Ed25519 en su lugar.
    """
    return hashlib.sha256(_APP_SIGNING_SALT + _HMAC_SALT).digest()


def _ensure_keypair(profile: dict[str, str]) -> dict[str, str]:
    """Genera un keypair Ed25519 si el perfil no tiene uno.

    La clave privada se cifra con XChaCha20-Poly1305 usando la clave del
    hardware y se almacena como ``signing_key_enc`` (base64).
    En memoria, ``signing_key`` (hex) esta disponible para firmar.
    """
    from nacl.signing import SigningKey

    # 1. Intentar descifrar clave cifrada (desde disco)
    enc_b64 = profile.get("signing_key_enc", "")
    if enc_b64:
        try:
            from pong.crypto import decrypt_at_rest

            blob = base64.b64decode(enc_b64)
            sk_hex = decrypt_at_rest(_derive_machine_key(), blob).decode("ascii")
            signing_key = SigningKey(bytes.fromhex(sk_hex))
            profile["signing_key"] = signing_key.encode().hex()
            profile["verify_key"] = signing_key.verify_key.encode().hex()
            return profile
        except Exception:
            pass  # Descifrado fallido → intentar plano o generar

    # 2. Aceptar clave en plano ya presente en memoria (tests, constructor)
    signing_key_hex = profile.get("signing_key", "")
    if signing_key_hex:
        try:
            signing_key = SigningKey(bytes.fromhex(signing_key_hex))
            profile["signing_key"] = signing_key.encode().hex()
            profile["verify_key"] = signing_key.verify_key.encode().hex()
            _encrypt_signing_key_in_profile(profile)
            return profile
        except (TypeError, ValueError):
            pass

    # 3. Generar nuevo par de claves
    sk = SigningKey.generate()
    profile["signing_key"] = sk.encode().hex()
    profile["verify_key"] = sk.verify_key.encode().hex()
    _encrypt_signing_key_in_profile(profile)
    return profile


def _encrypt_signing_key_in_profile(profile: dict[str, str]) -> None:
    """Cifra signing_key y la guarda como signing_key_enc en el perfil."""
    sk_hex = profile.get("signing_key", "")
    if not sk_hex:
        return
    try:
        from pong.crypto import encrypt_at_rest

        blob = encrypt_at_rest(_derive_machine_key(), sk_hex.encode("ascii"))
        profile["signing_key_enc"] = base64.b64encode(blob).decode("ascii")
    except Exception:
        pass


def _normalize_p2p_profile(
    profile: dict[str, str],
) -> tuple[dict[str, str], bool, bool]:
    """Normaliza keypair/fingerprint y detecta si cambia la identidad P2P."""
    normalized = dict(profile)
    if not any(
        normalized.get(key)
        for key in ("alias", "fingerprint", "signing_key", "verify_key")
    ):
        return normalized, False, False

    before = dict(normalized)
    original_fp = normalized.get("fingerprint", "")
    _ensure_keypair(normalized)

    derived_fp = _compute_fingerprint(normalized.get("verify_key", ""))
    if derived_fp:
        normalized["fingerprint"] = derived_fp

    changed = normalized != before
    identity_changed = bool(original_fp and derived_fp and original_fp != derived_fp)
    return normalized, changed, identity_changed


def get_player_profile(history: dict[str, Any]) -> dict[str, str]:
    """Devuelve el perfil del jugador o dict vacio si no hay alias."""
    result: dict[str, str] = history.get("player_profile", {})
    result, changed, identity_changed = _normalize_p2p_profile(result)
    if changed:
        history["player_profile"] = result
    if identity_changed:
        _clear_p2p_validation_state(history, result)
    return result


def set_player_alias(alias: str) -> dict[str, str]:
    """Guarda el alias del jugador y genera fingerprint + keypair si no existen."""
    history = load_history()
    profile: dict[str, str] = history.get("player_profile", {})
    profile["alias"] = alias
    profile, _changed, identity_changed = _normalize_p2p_profile(profile)
    history["player_profile"] = profile
    if identity_changed:
        _clear_p2p_validation_state(history, profile)
    _write_history(history)
    return profile


def save_p2p_validation(
    suffix: str,
    remote_entries: list[dict[str, Any]],
) -> dict[str, str]:
    """Persiste la validacion P2P: sufijo asignado, fecha y backup de entries.

    Se llama cada vez que el jugador conecta con al menos 1 peer.
    Guarda:
    - ``validated_suffix``: sufijo B64 definitivo (ej: ``AAAA``)
    - ``validated_date``: fecha ISO de la ultima validacion
    - ``p2p_backup``: copia de todas las entries remotas recibidas

    Returns:
        El player_profile actualizado.
    """
    from datetime import datetime, timezone

    history = load_history()
    profile: dict[str, str] = history.get("player_profile", {})
    profile["validated_suffix"] = suffix
    profile["validated_date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    history["player_profile"] = profile
    history["p2p_backup"] = remote_entries
    _write_history(history)
    return profile


def get_p2p_backup(history: dict[str, Any]) -> list[dict[str, Any]]:
    """Devuelve el backup de entries remotas guardado en el save."""
    result: list[dict[str, Any]] = history.get("p2p_backup", [])
    return result


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
