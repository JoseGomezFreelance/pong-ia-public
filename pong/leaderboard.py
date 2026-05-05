"""
pong/leaderboard.py -- Logica de rankings y clasificaciones.

Gestiona entradas de leaderboard, firma criptografica, verificacion
de plausibilidad y merge de datos locales + remotos (P2P).
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from pong.save_manager import (
    RECORD_CATEGORIES,
    compute_records,
    format_record_date,
    format_record_value,
)

logger = logging.getLogger(__name__)

# Umbrales de plausibilidad — valores por encima/debajo se marcan sospechosos
_PLAUSIBILITY = {
    "fastest_win": ("lt", 8.0),       # < 8 segundos es sospechoso
    "longest_rally": ("gt", 300),     # > 300 golpes
    "max_score": ("gt", 100),         # > 100 puntos en una partida
    "longest_streak": ("gt", 30),     # > 30 puntos consecutivos
    "biggest_domination": ("gt", 80), # +80 puntos de diferencia
}

# Sufijos Base64 para aliases duplicados (AAAA..////)
_B64_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"


def _index_to_b64_suffix(index: int) -> str:
    """Convierte un indice (0-based) a sufijo de 4 chars en Base64."""
    result = []
    for _ in range(4):
        result.append(_B64_CHARS[index % 64])
        index //= 64
    return "".join(reversed(result))


@dataclass
class LeaderboardEntry:
    """Una entrada individual en el ranking."""

    alias: str
    fingerprint: str
    category: str
    value: float
    date: str
    signature: str = ""
    is_local: bool = False
    is_suspicious: bool = False
    display_alias: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serializa para transmision P2P."""
        return {
            "alias": self.alias,
            "fingerprint": self.fingerprint,
            "category": self.category,
            "value": self.value,
            "date": self.date,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LeaderboardEntry:
        """Deserializa desde datos P2P."""
        return cls(
            alias=data.get("alias", "???"),
            fingerprint=data.get("fingerprint", ""),
            category=data.get("category", ""),
            value=data.get("value", 0),
            date=data.get("date", ""),
            signature=data.get("signature", ""),
        )


def _canonical_payload(entry: LeaderboardEntry) -> bytes:
    """Payload canonico para firmar/verificar una entry."""
    return json.dumps(
        {
            "fp": entry.fingerprint,
            "cat": entry.category,
            "val": entry.value,
            "date": entry.date,
        },
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")


def compute_entries_digest(entries: list[LeaderboardEntry]) -> str:
    """Digest SHA-256 orden-independiente para detectar cambios reales en entries."""
    canonical = sorted(
        (entry.to_dict() for entry in entries),
        key=lambda item: (
            item.get("fingerprint", ""),
            item.get("category", ""),
            item.get("alias", ""),
            item.get("date", ""),
            item.get("value", 0),
            item.get("signature", ""),
        ),
    )
    payload = json.dumps(
        canonical,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sign_entry(entry: LeaderboardEntry, signing_key_hex: str) -> None:
    """Firma una entry in-place con Ed25519."""
    from nacl.signing import SigningKey

    sk = SigningKey(bytes.fromhex(signing_key_hex))
    payload = _canonical_payload(entry)
    signed = sk.sign(payload)
    entry.signature = signed.signature.hex()


def verify_entry(entry: LeaderboardEntry, verify_key_hex: str) -> bool:
    """Verifica la firma Ed25519 de una entry.

    Args:
        entry: La entry a verificar.
        verify_key_hex: Clave publica Ed25519 del peer (hex, 64 chars).
            Si esta vacia, la verificacion falla.
    """
    if not entry.signature or not verify_key_hex:
        return False
    try:
        from nacl.signing import VerifyKey
        from nacl.exceptions import BadSignatureError

        vk = VerifyKey(bytes.fromhex(verify_key_hex))
        payload = _canonical_payload(entry)
        vk.verify(payload, bytes.fromhex(entry.signature))
        return True
    except (BadSignatureError, ValueError, Exception):
        logger.debug("Firma invalida para entry %s/%s", entry.fingerprint, entry.category)
        return False


def check_plausibility(entry: LeaderboardEntry) -> bool:
    """Retorna True si el valor es plausible. Marca is_suspicious si no."""
    rule = _PLAUSIBILITY.get(entry.category)
    if rule is None:
        return True
    direction, threshold = rule
    if direction == "lt" and entry.value < threshold:
        entry.is_suspicious = True
        return False
    if direction == "gt" and entry.value > threshold:
        entry.is_suspicious = True
        return False
    return True


def get_local_entries(
    history: dict[str, Any],
    profile: dict[str, str],
) -> list[LeaderboardEntry]:
    """Extrae entries del leaderboard a partir de los records locales."""
    records = history.get("records", {})
    if not profile.get("alias") or not profile.get("fingerprint"):
        return []

    signing_key = profile.get("signing_key", "")

    entries: list[LeaderboardEntry] = []
    for key, _label in RECORD_CATEGORIES:
        rec = records.get(key)
        if rec is None:
            continue
        entry = LeaderboardEntry(
            alias=profile["alias"],
            fingerprint=profile["fingerprint"],
            category=key,
            value=rec["value"],
            date=rec.get("date", ""),
            is_local=True,
        )
        if signing_key:
            sign_entry(entry, signing_key)
        check_plausibility(entry)
        entries.append(entry)
    return entries


def merge_entries(
    local: list[LeaderboardEntry],
    remote: list[LeaderboardEntry],
    *,
    p2p_validated: bool = False,
    saved_suffix: str = "",
) -> dict[str, list[LeaderboardEntry]]:
    """Mergea entries locales y remotos, agrupa por categoria y ordena.

    Args:
        local: Entries del jugador local.
        remote: Entries recibidas de peers P2P.
        p2p_validated: True si hay al menos 1 peer conectado.
            Si False, los sufijos locales se muestran como ``????``
            porque el nombre aun no ha sido validado contra la red.
        saved_suffix: Sufijo B64 de la ultima validacion guardada
            (ej: ``AAAA``). Se usa cuando ``p2p_validated=False``
            para mostrar el ultimo sufijo conocido en vez de ``????``.
    """
    by_category: dict[str, dict[str, LeaderboardEntry]] = {}

    for entry in local + remote:
        cat = entry.category
        if cat not in by_category:
            by_category[cat] = {}
        fp = entry.fingerprint
        existing = by_category[cat].get(fp)
        if existing is None:
            by_category[cat][fp] = entry
        else:
            # Mantener el mejor valor (menor para fastest_win, mayor para otros)
            if cat == "fastest_win":
                if entry.value < existing.value:
                    by_category[cat][fp] = entry
            else:
                if entry.value > existing.value:
                    by_category[cat][fp] = entry

    result: dict[str, list[LeaderboardEntry]] = {}
    for key, _label in RECORD_CATEGORIES:
        entries = list(by_category.get(key, {}).values())
        reverse = key != "fastest_win"
        entries.sort(key=lambda e: e.value, reverse=reverse)
        _assign_display_aliases(
            entries, p2p_validated=p2p_validated, saved_suffix=saved_suffix,
        )
        result[key] = entries
    return result


def _assign_display_aliases(
    entries: list[LeaderboardEntry],
    *,
    p2p_validated: bool = False,
    saved_suffix: str = "",
) -> None:
    """Asigna display_alias con sufijo Base64, guardado o ``????``.

    - Con peers (``p2p_validated=True``): sufijo determinista por fingerprint.
    - Sin peers pero con validacion previa: usa el ``saved_suffix``.
    - Sin peers ni validacion previa: usa ``????``.
    """
    # Agrupar por alias
    alias_groups: dict[str, list[LeaderboardEntry]] = {}
    for entry in entries:
        alias_groups.setdefault(entry.alias, []).append(entry)

    for alias, group in alias_groups.items():
        # Ordenar por fingerprint para asignar sufijos deterministas
        group.sort(key=lambda e: e.fingerprint)
        for i, entry in enumerate(group):
            if p2p_validated or not entry.is_local:
                entry.display_alias = f"{alias}-{_index_to_b64_suffix(i)}"
            elif saved_suffix:
                entry.display_alias = f"{alias}-{saved_suffix}"
            else:
                entry.display_alias = f"{alias}-????"


def format_entry_value(entry: LeaderboardEntry) -> str:
    """Formatea el valor de una entry para mostrar en la UI."""
    return format_record_value(entry.category, entry.value)


def format_entry_date(entry: LeaderboardEntry) -> str:
    """Formatea la fecha de una entry para mostrar en la UI."""
    return format_record_date(entry.date)
