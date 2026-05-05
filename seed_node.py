"""PongIA seed node — modo headless para VPS (sin pygame).

Arranca solo la capa P2P como punto de encuentro permanente.
No juega partidas ni tiene records propios. Actua como bootstrap
estable para discovery y gossip entre jugadores.

Uso:
    python seed_node.py                  # produccion (INFO)
    python seed_node.py --debug          # logs detallados
    python seed_node.py --alias mi-nodo  # alias personalizado
"""
from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
from pathlib import Path
from typing import Any

# Importar solo submodulos — evitar pong/__init__.py que importa pygame
from pong.save_manager import (
    _apply_owner_only_permissions,
    _normalize_p2p_profile,
    derive_machine_key,
)
from pong.p2p import PeerNetwork

logger = logging.getLogger("pongia.seed")

__all__ = ["PeerNetwork", "format_status_line", "load_or_create_profile", "main"]

SAVE_DIR = Path("saves")
PROFILE_PATH = SAVE_DIR / "seed_profile.json"
CACHE_PATH = SAVE_DIR / "known_peers.json"
STATUS_INTERVAL = 60  # segundos entre logs de estado


def _save_seed_profile(profile: dict[str, str]) -> None:
    """Escribe el perfil del seed cifrando la signing_key."""
    import base64
    import copy

    from pong.crypto import encrypt_at_rest

    to_write = copy.copy(profile)
    sk_hex = to_write.pop("signing_key", "")
    if sk_hex:
        blob = encrypt_at_rest(derive_machine_key(), sk_hex.encode("ascii"))
        to_write["signing_key_enc"] = base64.b64encode(blob).decode("ascii")

    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROFILE_PATH, "w", encoding="utf-8") as fh:
        json.dump(to_write, fh, indent=2)
    _apply_owner_only_permissions(PROFILE_PATH)


def load_or_create_profile(alias: str) -> dict[str, str]:
    """Carga o genera el perfil persistente del seed node."""
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    profile: dict[str, str] | None = None
    created = False

    if PROFILE_PATH.exists():
        try:
            with open(PROFILE_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                profile = loaded
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Error leyendo perfil, regenerando: %s", e)

    if profile is None:
        profile = {"alias": alias}
        created = True
    elif not profile.get("alias"):
        profile["alias"] = alias

    profile, changed, _identity_changed = _normalize_p2p_profile(profile)
    if created or changed:
        _save_seed_profile(profile)
        logger.info("Perfil %s: %s (%s)", "creado" if created else "actualizado", profile.get("alias"), profile.get("fingerprint"))
    else:
        logger.info("Perfil cargado: %s (%s)", profile.get("alias"), profile.get("fingerprint"))
    return profile


def format_status_line(telemetry: dict[str, Any]) -> str:
    """Construye la linea de estado periodica del seed node."""
    return (
        "Estado: "
        f"{telemetry.get('active_peers', 0)} peers activos, "
        f"{telemetry.get('remote_entries', 0)} entries remotas, "
        f"{telemetry.get('total_peers_seen', 0)} peers vistos total"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="PongIA seed node (headless)")
    parser.add_argument("--debug", action="store_true", help="Logging detallado")
    parser.add_argument("--alias", default="seed-01", help="Alias del nodo (default: seed-01)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stdout,
    )

    logger.info("=== PongIA Seed Node ===")

    profile = load_or_create_profile(args.alias)

    network = PeerNetwork(
        profile=profile,
        cache_path=CACHE_PATH,
    )
    try:
        network.start(strict_bind=True)
    except OSError as exc:
        logger.error("No se pudo arrancar el seed node: %s", exc)
        raise SystemExit(1) from exc
    logger.info("Red P2P arrancada. Esperando conexiones...")

    # Shutdown limpio con SIGINT (Ctrl+C) y SIGTERM (systemd)
    running = True

    def _shutdown(signum: int, frame: Any) -> None:
        nonlocal running
        logger.info("Senal %d recibida, parando...", signum)
        running = False

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # Bucle principal: log de estado periodico
    last_status = time.time()
    while running:
        time.sleep(1)
        now = time.time()
        if now - last_status >= STATUS_INTERVAL:
            last_status = now
            telemetry = network.get_telemetry()
            logger.info(format_status_line(telemetry))

    network.stop()
    logger.info("Seed node parado.")


if __name__ == "__main__":
    main()
