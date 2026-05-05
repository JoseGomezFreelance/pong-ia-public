"""
pong/p2p_cache.py -- Cache de peers conocidos en disco.

Equivalente a peers.dat de Bitcoin: almacena peers descubiertos
para reconectar sin broadcast en sesiones futuras.
El contenido se cifra con XChaCha20-Poly1305 usando la clave del hardware.
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any

from pong.save_manager import (
    _apply_owner_only_permissions,
    _compute_fingerprint,
    derive_machine_key,
)


# Tiempo maximo en cache antes de considerar un peer obsoleto (7 dias)
_PEER_MAX_AGE = 7 * 24 * 3600
_DEFAULT_DATA_PORT = 19848


def _normalize_cached_peer(peer: dict[str, Any]) -> dict[str, Any] | None:
    """Migra peers legacy al nuevo modelo ``fp = sha256(vk)[:16]``."""
    if not isinstance(peer, dict):
        return None

    verify_key = peer.get("vk", "")
    fingerprint = _compute_fingerprint(verify_key)
    if not fingerprint:
        return None

    try:
        port = int(peer.get("port", _DEFAULT_DATA_PORT))
    except (TypeError, ValueError):
        port = _DEFAULT_DATA_PORT
    try:
        last_seen = float(peer.get("last_seen", 0))
    except (TypeError, ValueError):
        last_seen = 0

    return {
        "ip": str(peer.get("ip", "")),
        "port": port,
        "fp": fingerprint,
        "alias": str(peer.get("alias", "")),
        "vk": verify_key,
        "last_seen": last_seen,
    }


def load_peer_cache(cache_path: Path) -> list[dict[str, Any]]:
    """Carga la lista de peers conocidos desde disco (cifrada)."""
    if not cache_path.exists():
        return []
    try:
        with open(cache_path, "r", encoding="utf-8") as fh:
            wrapper = json.load(fh)

        if not isinstance(wrapper, dict) or "_enc" not in wrapper:
            return []  # Formato no reconocido → fresh start

        from pong.crypto import decrypt_at_rest

        blob = base64.b64decode(wrapper["_enc"])
        plaintext = decrypt_at_rest(derive_machine_key(), blob)
        data = json.loads(plaintext.decode("utf-8"))

        if not isinstance(data, list):
            return []
        return [
            migrated
            for peer in data
            if (migrated := _normalize_cached_peer(peer)) is not None
        ]
    except Exception:
        return []


def save_peer_cache(cache_path: Path, peers: list[dict[str, Any]]) -> None:
    """Guarda la lista de peers conocidos a disco (cifrada)."""
    try:
        from pong.crypto import encrypt_at_rest

        plaintext = json.dumps(peers, ensure_ascii=False, indent=2).encode("utf-8")
        blob = encrypt_at_rest(derive_machine_key(), plaintext)
        wrapper = {"_enc": base64.b64encode(blob).decode("ascii"), "_v": 1}

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as fh:
            json.dump(wrapper, fh, indent=2)
        _apply_owner_only_permissions(cache_path)
    except OSError:
        pass


def merge_peer_cache(
    existing: list[dict[str, Any]],
    new_peers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Mergea peers nuevos con los existentes, deduplicando por fingerprint.

    Mantiene la entrada mas reciente (mayor last_seen) para cada
    fingerprint. Elimina peers obsoletos (> 7 dias sin ver).
    """
    by_fp: dict[str, dict[str, Any]] = {}

    for peer in existing + new_peers:
        normalized_peer = _normalize_cached_peer(peer)
        if normalized_peer is None:
            continue
        fp = normalized_peer.get("fp", "")
        prev = by_fp.get(fp)
        if prev is None:
            by_fp[fp] = dict(normalized_peer)
            continue

        prev_seen = prev.get("last_seen", 0)
        peer_seen = normalized_peer.get("last_seen", 0)
        if peer_seen >= prev_seen:
            merged = dict(normalized_peer)
            if not merged.get("vk") and prev.get("vk"):
                merged["vk"] = prev["vk"]
        else:
            merged = dict(prev)
            if not merged.get("vk") and normalized_peer.get("vk"):
                merged["vk"] = normalized_peer["vk"]

        if not merged.get("alias") and prev.get("alias"):
            merged["alias"] = prev["alias"]
        if not merged.get("alias") and normalized_peer.get("alias"):
            merged["alias"] = normalized_peer["alias"]
        if not merged.get("ip") and prev.get("ip"):
            merged["ip"] = prev["ip"]
        if not merged.get("ip") and normalized_peer.get("ip"):
            merged["ip"] = normalized_peer["ip"]
        if "port" not in merged or not merged.get("port"):
            if prev.get("port"):
                merged["port"] = prev["port"]
            elif normalized_peer.get("port"):
                merged["port"] = normalized_peer["port"]

        by_fp[fp] = merged

    # Purgar peers obsoletos
    now = time.time()
    return [
        p for p in by_fp.values()
        if now - p.get("last_seen", 0) < _PEER_MAX_AGE
    ]


def load_seed_peers(saves_dir: Path) -> list[dict[str, Any]]:
    """
    Carga peers de un fichero known_peers.txt compartible.

    Formato del fichero (una linea por peer):
        # Comentario
        192.168.1.50:19848
        10.0.0.5:19848

    Returns:
        Lista de dicts con formato compatible con la cache.
    """
    seed_file = saves_dir / "known_peers.txt"
    if not seed_file.exists():
        return []

    peers: list[dict[str, Any]] = []
    try:
        with open(seed_file, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(":")
                if len(parts) != 2:
                    continue
                ip = parts[0].strip()
                try:
                    port = int(parts[1].strip())
                except ValueError:
                    continue
                peers.append({
                    "ip": ip,
                    "port": port,
                    "fp": "",  # desconocido hasta handshake
                    "alias": "",
                    "last_seen": 0,
                })
    except OSError:
        pass
    return peers
