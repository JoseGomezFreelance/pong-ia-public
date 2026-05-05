"""
pong/p2p.py -- Red P2P para rankings de PongIA.

Arquitectura inspirada en Bitcoin:
- Descubrimiento por UDP beacon anonimo en LAN (sin identidad en broadcast)
- Intercambio de records por TCP con cifrado XChaCha20-Poly1305
- Handshake cifrado desde el primer byte (X25519 efimero + Ed25519)
- Forward secrecy via triple ECDH (efimero-efimero + estatico-efimero)
- Gossip de peers sin IPs (solo fingerprints y alias)
- Cache de peers cifrada en disco
- Soporte para seed peers via fichero known_peers.txt
- Firmas Ed25519 en cada entry del leaderboard

Dependencias: PyNaCl (libsodium), stdlib (socket, threading, json, time).
Todos los hilos son daemon (mueren con el proceso).
Thread safety via threading.Lock.
"""

from __future__ import annotations

import json
import logging
import secrets
import socket
import struct
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pong.crypto import (
    aead_decrypt,
    aead_encrypt,
    derive_key,
    ecdh,
    generate_ephemeral_x25519,
)
from pong.leaderboard import LeaderboardEntry, check_plausibility, verify_entry
from pong.p2p_cache import (
    load_peer_cache,
    load_seed_peers,
    merge_peer_cache,
    save_peer_cache,
)
from pong.save_manager import _compute_fingerprint

logger = logging.getLogger("pongia.p2p")

# Puertos del protocolo
BROADCAST_PORT = 19847
DATA_PORT = 19848

# Intervalos (segundos)
DISCOVERY_INTERVAL = 10
GOSSIP_INTERVAL = 30
PEER_TIMEOUT = 60
CACHE_SAVE_INTERVAL = 60

# Tamano maximo de mensaje
MAX_MSG_SIZE = 65536

# Protocolo version (4.0 = XChaCha20-Poly1305 + handshake cifrado + forward secrecy)
PROTOCOL_VERSION = "4.0"

# Rate limiting
MAX_CONN_PER_IP_PER_MIN = 10
MAX_CONCURRENT_CONNECTIONS = 20
MAX_PEERS = 200
MAX_ENTRIES_PER_MESSAGE = 50

# Reputacion
MAX_STRIKES = 3

# Bootstrap WAN
BOOTSTRAP_DIAL_LIMIT = 3
BOOTSTRAP_RETRY_INTERVAL = 60

# Seeds hardcoded (fallback si no existe known_peers.txt)
DEFAULT_SEEDS: list[tuple[str, int]] = [
    ("178.104.104.58", 19848),
]


@dataclass
class PeerInfo:
    """Informacion de un peer descubierto."""

    fingerprint: str
    alias: str
    ip: str
    data_port: int
    last_seen: float = field(default_factory=time.time)
    records: list[LeaderboardEntry] = field(default_factory=list)
    verify_key: str = ""
    encrypted: bool = False
    punch_endpoint: dict[str, Any] = field(default_factory=dict)
    relay_capable: bool = False


class PeerNetwork:
    """
    Red P2P para intercambio de rankings de PongIA.

    Descubrimiento: UDP broadcast en LAN.
    Datos: TCP cifrado con NaCl crypto_box.
    Gossip: propagacion de listas de peers.
    """

    def __init__(self, profile: dict[str, str], cache_path: Path) -> None:
        self._profile = profile
        self._cache_path = cache_path
        self._fingerprint = profile.get("fingerprint", "")
        self._alias = profile.get("alias", "")
        self._verify_key = profile.get("verify_key", "")
        self._signing_key = profile.get("signing_key", "")

        self._peers: dict[str, PeerInfo] = {}
        self._remote_entries: list[LeaderboardEntry] = []
        self._local_entries: list[LeaderboardEntry] = []
        self._lock = threading.Lock()

        self._running = False
        self._threads: list[threading.Thread] = []

        # Rate limiting
        self._conn_tracker: dict[str, list[float]] = {}
        self._active_connections: int = 0


        # Reputacion (strikes por peer, con timestamp para expiracion)
        self._peer_strikes: dict[str, int] = {}
        self._strike_times: dict[str, float] = {}
        self._last_bootstrap_attempts: dict[str, float] = {}

        # Peers con los que hemos intercambiado records exitosamente (para consent del punch)
        self._exchanged_with: set[str] = set()

        # NAT traversal (se inicializa en start())
        self._punch_manager: Any = None
        # Flag de degradacion: True si el NAT traversal no pudo arrancar
        # (el resto de la red P2P sigue funcionando, pero sin punch directo)
        self._p2p_degraded: bool = False

        # Telemetria publica (thread-safe via _lock)
        self._discovery_attempts: int = 0
        self._peers_ever_seen: int = 0
        self._last_broadcast_time: float = 0
        self._broadcast_addresses: list[str] = []
        self._listener_socket: socket.socket | None = None
        self._data_server_socket: socket.socket | None = None

    def start(self, *, strict_bind: bool = False) -> None:
        """Inicia todos los hilos de la red P2P."""
        if self._running:
            return

        # Cargar peers conocidos del cache y seeds
        self._load_initial_peers()

        listener_sock = self._create_listener_socket()
        data_sock = self._create_data_server_socket()
        if strict_bind and (listener_sock is None or data_sock is None):
            for sock in (listener_sock, data_sock):
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
            raise OSError("P2P: no se pudieron abrir los puertos requeridos")

        self._listener_socket = listener_sock
        self._data_server_socket = data_sock
        self._running = True

        threads = [("pongia-discovery", self._discovery_loop)]
        if self._listener_socket is not None:
            threads.append(("pongia-listener", self._listener_loop))
        if self._data_server_socket is not None:
            threads.append(("pongia-data-server", self._data_server_loop))
        threads.extend([
            ("pongia-gossip", self._gossip_loop),
            ("pongia-cache-saver", self._cache_save_loop),
        ])
        for name, target in threads:
            t = threading.Thread(target=target, name=name, daemon=True)
            t.start()
            self._threads.append(t)
        logger.info(
            "P2P red iniciada: broadcast=%d, listener=%s, data=%s",
            BROADCAST_PORT,
            "ok" if self._listener_socket is not None else "disabled",
            "ok" if self._data_server_socket is not None else "disabled",
        )

        # NAT traversal (opcional, si falla el resto sigue pero queda degradado)
        try:
            # Debug: forzar degradacion para probar el indicador UI
            import os
            if os.environ.get("PONGIA_FORCE_DEGRADED") == "1":
                raise RuntimeError("degradacion forzada por PONGIA_FORCE_DEGRADED")

            from pong.punch import PunchManager
            pm = PunchManager(self)
            pm.start()
            # Verificacion activa: PunchManager puede arrancar sin errores
            # pero quedar sin socket UDP (puerto bloqueado, etc)
            if pm._udp_sock is None:
                raise RuntimeError("PunchManager sin socket UDP")
            self._punch_manager = pm
            logger.info("P2P: PunchManager iniciado en puerto %d",
                        pm._udp_sock.getsockname()[1])
        except Exception as exc:
            logger.error(
                "P2P DEGRADADO: NAT punch no disponible (%s). "
                "La red seguira funcionando via TCP relay, pero sin "
                "conexiones directas entre peers tras NAT.",
                exc,
            )
            self._punch_manager = None
            self._p2p_degraded = True

    def stop(self) -> None:
        """Detiene la red P2P y guarda la cache."""
        self._running = False
        if self._punch_manager is not None:
            try:
                self._punch_manager.stop()
            except Exception:
                pass
            self._punch_manager = None
        for attr in ("_listener_socket", "_data_server_socket"):
            sock = getattr(self, attr)
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
                setattr(self, attr, None)
        self._save_cache()
        # Los hilos daemon se detienen solos al terminar el proceso

    @staticmethod
    def _create_listener_socket() -> socket.socket | None:
        """Crea y bindea el socket UDP del listener, o None si falla."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except OSError:
                    pass
            sock.bind(("", BROADCAST_PORT))
            sock.settimeout(1.0)
            return sock
        except OSError:
            logger.warning("P2P: no se pudo bind al puerto de broadcast %d", BROADCAST_PORT)
            return None

    @staticmethod
    def _create_data_server_socket() -> socket.socket | None:
        """Crea y bindea el socket TCP del servidor de datos, o None si falla."""
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("", DATA_PORT))
            server.listen(5)
            server.settimeout(1.0)
            return server
        except OSError:
            logger.warning("P2P: no se pudo bind al puerto de datos %d", DATA_PORT)
            return None

    def get_peer_entries(self) -> list[LeaderboardEntry]:
        """Devuelve las entries de peers remotos."""
        with self._lock:
            return list(self._remote_entries)

    def get_peer_count(self) -> int:
        """Devuelve el numero de peers activos."""
        with self._lock:
            now = time.time()
            return sum(
                1 for p in self._peers.values()
                if now - p.last_seen < PEER_TIMEOUT
            )

    def broadcast_records(self, entries: list[LeaderboardEntry]) -> None:
        """Actualiza las entries locales para enviar a peers."""
        with self._lock:
            self._local_entries = list(entries)

    def get_telemetry(self) -> dict[str, Any]:
        """Devuelve metricas de la red para mostrar en UI."""
        with self._lock:
            now = time.time()
            active = sum(
                1 for p in self._peers.values()
                if now - p.last_seen < PEER_TIMEOUT
            )
            return {
                "active_peers": active,
                "total_peers_seen": self._peers_ever_seen,
                "remote_entries": len(self._remote_entries),
                "discovery_attempts": self._discovery_attempts,
                "broadcast_addresses": list(self._broadcast_addresses),
                "last_broadcast": self._last_broadcast_time,
                "running": self._running,
                "p2p_degraded": self._p2p_degraded,
            }

    # ================================================================
    # Inicializacion
    # ================================================================

    def _load_initial_peers(self) -> None:
        """Carga peers del cache y del fichero de seeds."""
        cached = load_peer_cache(self._cache_path)
        seeds = load_seed_peers(self._cache_path.parent)
        # Anadir semillas hardcoded que no esten ya en el fichero
        file_endpoints = {(p["ip"], p["port"]) for p in seeds}
        for def_ip, def_port in DEFAULT_SEEDS:
            if (def_ip, def_port) not in file_endpoints:
                seeds.append({
                    "ip": def_ip, "port": def_port,
                    "fp": "", "alias": "", "last_seen": 0,
                })
        # Solo merge de cached (seeds tienen fp="" y merge los descarta)
        merged = merge_peer_cache(cached, [])

        with self._lock:
            for p in merged:
                fp = p.get("fp", "")
                if fp and fp != self._fingerprint:
                    self._peers[fp] = PeerInfo(
                        fingerprint=fp,
                        alias=p.get("alias", ""),
                        ip=p.get("ip", ""),
                        data_port=p.get("port", DATA_PORT),
                        last_seen=p.get("last_seen", 0),
                        verify_key=p.get("vk", ""),
                    )

            # Seed peers: clave temporal seed:IP:puerto
            for p in seeds:
                ip = p.get("ip", "")
                port = p.get("port", DATA_PORT)
                if not ip:
                    continue
                seed_key = f"seed:{ip}:{port}"
                # Skip si ya tenemos un peer cached en esa IP:puerto
                already_known = any(
                    peer.ip == ip and peer.data_port == port
                    for peer in self._peers.values()
                )
                if already_known:
                    logger.info("P2P: seed %s omitido (peer ya en cache)", seed_key)
                else:
                    self._peers[seed_key] = PeerInfo(
                        fingerprint=seed_key,
                        alias="",
                        ip=ip,
                        data_port=port,
                        last_seen=0,
                    )
                    logger.info("P2P: seed %s cargado desde known_peers.txt", seed_key)

    @staticmethod
    def _has_consistent_identity(fp: str, vk: str) -> bool:
        """Comprueba que ``fp`` coincide con ``sha256(vk)[:16]``."""
        return bool(fp and vk and _compute_fingerprint(vk) == fp)

    def _pin_verify_key(self, fp: str, vk: str) -> str | None:
        """Fija la verify_key de un fingerprint y rechaza cambios posteriores."""
        if not fp:
            return None
        if not self._has_consistent_identity(fp, vk):
            logger.warning("P2P: identidad inconsistente fp/vk para %s", fp)
            if fp and not fp.startswith("seed:"):
                self._add_strike(fp)
            return None

        with self._lock:
            existing = self._peers.get(fp)
            pinned = existing.verify_key if existing is not None else ""
            if pinned and pinned != vk:
                should_reject = True
            else:
                if existing is not None and not existing.verify_key:
                    existing.verify_key = vk
                should_reject = False

        if should_reject:
            logger.warning("P2P: verify_key conflict para %s — peer rechazado", fp)
            self._add_strike(fp)
            return None
        return pinned or vk

    @staticmethod
    def _handshake_payload(
        *,
        role: str,
        client_fp: str,
        client_vk: str,
        client_nonce: str,
        client_eph_pk: str,
        server_fp: str,
        server_vk: str,
        server_nonce: str,
        server_eph_pk: str,
    ) -> bytes:
        """Payload canonico firmado durante el challenge-response del handshake."""
        return json.dumps(
            {
                "type": "pongia_handshake",
                "v": PROTOCOL_VERSION,
                "role": role,
                "client_fp": client_fp,
                "client_vk": client_vk,
                "client_nonce": client_nonce,
                "client_eph_pk": client_eph_pk,
                "server_fp": server_fp,
                "server_vk": server_vk,
                "server_nonce": server_nonce,
                "server_eph_pk": server_eph_pk,
            },
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def _sign_handshake_payload(self, payload: bytes) -> str:
        """Firma un payload arbitrario con la clave Ed25519 local."""
        from nacl.signing import SigningKey

        signing_key = SigningKey(bytes.fromhex(self._signing_key))
        signature_hex = signing_key.sign(payload).signature.hex()
        if not isinstance(signature_hex, str):
            raise TypeError("La firma Ed25519 debe serializarse como hex str")
        return signature_hex

    @staticmethod
    def _verify_handshake_signature(
        payload: bytes,
        signature_hex: str,
        verify_key_hex: str,
    ) -> bool:
        """Verifica una firma Ed25519 del handshake."""
        try:
            from nacl.exceptions import BadSignatureError
            from nacl.signing import VerifyKey

            verify_key = VerifyKey(bytes.fromhex(verify_key_hex))
            verify_key.verify(payload, bytes.fromhex(signature_hex))
            return True
        except (BadSignatureError, TypeError, ValueError):
            return False

    def _mark_bootstrap_attempt(self, fp: str, now: float) -> None:
        """Registra un intento saliente de bootstrap para aplicar backoff."""
        with self._lock:
            self._last_bootstrap_attempts[fp] = now

    def _select_bootstrap_candidates(self, now: float) -> list[PeerInfo]:
        """Selecciona peers dialables aprendidos por cache/gossip con backoff."""
        with self._lock:
            active_fps = {
                p.fingerprint for p in self._peers.values()
                if now - p.last_seen < PEER_TIMEOUT
            }
            candidates = [
                p for p in self._peers.values()
                if p.fingerprint not in active_fps
                and p.fingerprint != self._fingerprint
                and not self._is_blacklisted(p.fingerprint)
                and bool(p.ip)
                and p.data_port > 0
                and now - self._last_bootstrap_attempts.get(p.fingerprint, 0)
                >= BOOTSTRAP_RETRY_INTERVAL
            ]

        candidates.sort(
            key=lambda p: (
                0 if p.fingerprint.startswith("seed:") else 1,
                -p.last_seen,
                p.alias,
                p.fingerprint,
            ),
        )
        return candidates[:BOOTSTRAP_DIAL_LIMIT]

    # ================================================================
    # Descubrimiento (UDP broadcast)
    # ================================================================

    @staticmethod
    def _get_broadcast_addresses() -> list[str]:
        """Calcula direcciones de broadcast: 255.255.255.255 + subredes locales."""
        addrs = ["255.255.255.255"]
        try:
            # Obtener IPs locales y calcular broadcast de subred
            hostname = socket.gethostname()
            for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
                ip = str(info[4][0])
                if ip.startswith("127."):
                    continue
                # Asumir /24 como subred mas comun en LANs domesticas
                parts = ip.split(".")
                if len(parts) == 4:
                    subnet_bcast = f"{parts[0]}.{parts[1]}.{parts[2]}.255"
                    if subnet_bcast not in addrs:
                        addrs.append(subnet_bcast)
        except OSError:
            pass
        # Intentar tambien con netifaces-like approach via connect trick
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe.connect(("8.8.8.8", 80))
            local_ip = probe.getsockname()[0]
            probe.close()
            parts = local_ip.split(".")
            if len(parts) == 4:
                subnet_bcast = f"{parts[0]}.{parts[1]}.{parts[2]}.255"
                if subnet_bcast not in addrs:
                    addrs.append(subnet_bcast)
        except OSError:
            pass
        return addrs

    def _discovery_loop(self) -> None:
        """Envia broadcasts UDP periodicos para anunciar presencia."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(1.0)
        except OSError:
            logger.warning("P2P: no se pudo crear socket de broadcast")
            return

        broadcast_addrs = self._get_broadcast_addresses()
        with self._lock:
            self._broadcast_addresses = broadcast_addrs
        logger.info("P2P: broadcast a %s", broadcast_addrs)

        msg = json.dumps({
            "type": "pongia_beacon",
            "v": PROTOCOL_VERSION,
            "port": DATA_PORT,
        }).encode("utf-8")

        try:
            while self._running:
                for addr in broadcast_addrs:
                    try:
                        sock.sendto(msg, (addr, BROADCAST_PORT))
                    except OSError:
                        pass
                with self._lock:
                    self._discovery_attempts += 1
                    self._last_broadcast_time = time.time()
                # Dormir en intervalos cortos para parar rapido
                for _ in range(DISCOVERY_INTERVAL):
                    if not self._running:
                        break
                    time.sleep(1)
        finally:
            sock.close()

    def _listener_loop(self) -> None:
        """Escucha broadcasts UDP de otros peers."""
        sock = self._listener_socket
        if sock is None:
            return

        try:
            while self._running:
                try:
                    data, addr = sock.recvfrom(MAX_MSG_SIZE)
                except socket.timeout:
                    continue
                except OSError:
                    continue

                try:
                    msg = json.loads(data.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue

                if msg.get("type") != "pongia_beacon":
                    continue
                if msg.get("v") != PROTOCOL_VERSION:
                    continue

                peer_ip = addr[0]
                peer_port = msg.get("port", DATA_PORT)
                # Beacon anonimo: no sabemos identidad hasta TCP
                beacon_key = f"beacon:{peer_ip}:{peer_port}"

                is_new = False
                with self._lock:
                    # No registrar si ya tenemos un peer real en esa IP
                    already_known = any(
                        p.ip == peer_ip and p.data_port == peer_port
                        for p in self._peers.values()
                        if not p.fingerprint.startswith(("beacon:", "seed:"))
                    )
                    if already_known:
                        continue
                    if len(self._peers) >= MAX_PEERS and beacon_key not in self._peers:
                        continue
                    if beacon_key not in self._peers:
                        is_new = True
                        self._peers[beacon_key] = PeerInfo(
                            fingerprint=beacon_key,
                            alias="",
                            ip=peer_ip,
                            data_port=peer_port,
                            last_seen=0,
                        )

                if is_new:
                    logger.info("P2P: beacon recibido de %s:%d", peer_ip, peer_port)
                    self._exchange_records_with(beacon_key)
        finally:
            try:
                sock.close()
            except OSError:
                pass
            if self._listener_socket is sock:
                self._listener_socket = None

    # ================================================================
    # Servidor TCP (recibe records y gossip)
    # ================================================================

    def _check_rate_limit(self, ip: str) -> bool:
        """Comprueba si una IP ha excedido el rate limit. True = permitido."""
        now = time.time()
        with self._lock:
            if self._active_connections >= MAX_CONCURRENT_CONNECTIONS:
                return False
            timestamps = self._conn_tracker.get(ip, [])
            # Limpiar timestamps mas viejos de 60 segundos
            cutoff = now - 60
            timestamps = [t for t in timestamps if t > cutoff]
            if not timestamps:
                # Evitar memory leak: eliminar IPs sin actividad reciente
                self._conn_tracker.pop(ip, None)
                timestamps = []
            if len(timestamps) >= MAX_CONN_PER_IP_PER_MIN:
                return False
            timestamps.append(now)
            self._conn_tracker[ip] = timestamps
        return True

    def _data_server_loop(self) -> None:
        """Servidor TCP que recibe records y listas de peers."""
        server = self._data_server_socket
        if server is None:
            return

        try:
            while self._running:
                try:
                    conn, addr = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    continue

                # Rate limiting
                if not self._check_rate_limit(addr[0]):
                    try:
                        conn.close()
                    except OSError:
                        pass
                    logger.debug("P2P: rate limit excedido para %s", addr[0])
                    continue

                # Manejar conexion en hilo separado
                t = threading.Thread(
                    target=self._handle_connection,
                    args=(conn, addr),
                    daemon=True,
                )
                t.start()
        finally:
            try:
                server.close()
            except OSError:
                pass
            if self._data_server_socket is server:
                self._data_server_socket = None

    def _handle_connection(
        self, conn: socket.socket, addr: tuple[str, int],
    ) -> None:
        """Maneja una conexion TCP entrante con handshake cifrado obligatorio."""
        with self._lock:
            self._active_connections += 1
        try:
            conn.settimeout(5.0)
            session_key = self._handshake_server(conn, addr[0])
            if session_key is None:
                logger.debug("P2P: handshake fallido desde %s — descartando", addr[0])
                return

            raw = self._recv_message(conn, key=session_key)
            if not raw:
                return

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                self._add_strike_by_ip(addr[0])
                return

            msg_type = msg.get("type", "")

            if msg_type == "pongia_records":
                self._handle_records_message(msg, addr[0])
                response = self._build_records_message()
                self._send_message(conn, response, key=session_key)

            elif msg_type == "pongia_peers":
                self._handle_peers_message(msg)
                response = self._build_peers_message()
                self._send_message(conn, response, key=session_key)

            elif msg_type == "pongia_punch_req":
                if self._punch_manager is not None:
                    resp = self._punch_manager.handle_punch_request(msg, addr[0])
                    if resp:
                        self._send_message(conn, resp, key=session_key)
                else:
                    logger.info(
                        "P2P: pongia_punch_req ignorado — red degradada",
                    )

            elif msg_type == "pongia_relay_setup":
                if self._punch_manager is not None:
                    self._punch_manager.handle_relay_setup(msg)
                else:
                    logger.info(
                        "P2P: pongia_relay_setup ignorado — red degradada",
                    )

        except Exception:
            pass
        finally:
            with self._lock:
                self._active_connections -= 1
            try:
                conn.close()
            except OSError:
                pass

    # ================================================================
    # Gossip (propagacion de peers)
    # ================================================================

    def _gossip_loop(self) -> None:
        """Periodicamente intercambia peers y records con un peer aleatorio."""
        import random

        # Primera iteracion rapida (5s) para captar peers que ya estan online
        first_run = True
        while self._running:
            wait = 5 if first_run else GOSSIP_INTERVAL
            first_run = False
            for _ in range(wait):
                if not self._running:
                    return
                time.sleep(1)

            now = time.time()
            contacted: set[str] = set()

            for peer in self._select_bootstrap_candidates(now):
                self._mark_bootstrap_attempt(peer.fingerprint, now)
                self._exchange_records_with(peer.fingerprint)
                contacted.add(peer.fingerprint)

            with self._lock:
                active = [
                    p for p in self._peers.values()
                    if now - p.last_seen < PEER_TIMEOUT
                    and not self._is_blacklisted(p.fingerprint)
                ]
            if not active and not contacted:
                continue

            # Intercambiar records con peers activos, evitando duplicados del bootstrap
            for peer in active:
                if peer.fingerprint in contacted:
                    continue
                self._mark_bootstrap_attempt(peer.fingerprint, now)
                self._exchange_records_with(peer.fingerprint)
            # Gossip de lista de peers solo con peers verificados
            gossipable = [
                peer for peer in active
                if not peer.fingerprint.startswith("seed:")
            ]
            if gossipable:
                peer = random.choice(gossipable)
                self._exchange_peers_with(peer)

            # Podar estado rancio: bootstrap attempts de peers desaparecidos
            with self._lock:
                stale = [
                    fp for fp in self._last_bootstrap_attempts
                    if fp not in self._peers
                ]
                for fp in stale:
                    del self._last_bootstrap_attempts[fp]

            # Mantener punches activos: gossip via UDP + keepalive + cleanup
            if self._punch_manager is not None:
                try:
                    self._punch_manager.attempt_pending_punches()
                except Exception as exc:
                    logger.warning(
                        "punch: error en attempt_pending_punches: %s", exc,
                    )

                # Trigger nuevo punch (1 por ciclo, conservador)
                try:
                    self._try_initiate_one_punch(now)
                except Exception as exc:
                    logger.warning("punch: error en trigger: %s", exc)

    # ================================================================
    # Intercambio de datos (TCP)
    # ================================================================

    def _tcp_exchange(
        self,
        ip: str,
        port: int,
        msg: str,
        *,
        expected_fp: str = "",
        expected_vk: str = "",
    ) -> str | None:
        """Conecta por TCP con handshake cifrado obligatorio."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(10.0)
            sock.connect((ip, port))
            session_key = self._handshake_client(
                sock,
                expected_fp=expected_fp,
                expected_vk=expected_vk,
            )
            if session_key is None:
                logger.debug("P2P: handshake fallido con %s — descartando", ip)
                return None
            self._send_message(sock, msg, key=session_key)
            return self._recv_message(sock, key=session_key)
        except (OSError, ConnectionError):
            return None
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def _exchange_records_with(self, fp: str) -> None:
        """Envia records a un peer y recibe los suyos."""
        with self._lock:
            peer = self._peers.get(fp)
            if peer is None:
                return
            ip, port = peer.ip, peer.data_port
            is_temporary = fp.startswith(("seed:", "beacon:"))
            expected_vk = peer.verify_key

        msg = self._build_records_message()
        raw = self._tcp_exchange(
            ip,
            port,
            msg,
            expected_fp="" if is_temporary else fp,
            expected_vk="" if is_temporary else expected_vk,
        )

        if raw:
            try:
                response = json.loads(raw)
                if response.get("type") == "pongia_records":
                    self._handle_records_message(response, ip)
                    # Promocion: eliminar clave temporal seed:/beacon:
                    if is_temporary:
                        real_fp = response.get("fp", "")
                        with self._lock:
                            if real_fp and real_fp in self._peers:
                                # Preservar el puerto real del seed/beacon
                                temp_peer = self._peers.get(fp)
                                if temp_peer:
                                    self._peers[real_fp].data_port = (
                                        temp_peer.data_port
                                    )
                                self._peers.pop(fp, None)
                                logger.info(
                                    "P2P: %s promoted -> %s",
                                    fp, real_fp,
                                )
            except json.JSONDecodeError:
                pass

    def _exchange_peers_with(self, peer: PeerInfo) -> None:
        """Intercambia listas de peers con un peer (gossip)."""
        msg = self._build_peers_message()
        raw = self._tcp_exchange(
            peer.ip,
            peer.data_port,
            msg,
            expected_fp=peer.fingerprint,
            expected_vk=peer.verify_key,
        )

        if raw:
            try:
                response = json.loads(raw)
                if response.get("type") == "pongia_peers":
                    self._handle_peers_message(response)
            except json.JSONDecodeError:
                pass

    def _try_initiate_one_punch(self, now: float) -> None:
        """Intenta iniciar un punch con un peer al ciclo (conservador).

        Selecciona un peer activo que:
        - Tiene punch_endpoint conocido (sabemos como puncharle)
        - No tiene ya un punch activo o establecido
        - Es real (no seed/beacon temporal)
        - Esta dentro del PEER_TIMEOUT
        - No esta blacklisted

        Como coordinador usa el primer peer relay_capable que encuentra
        (tipicamente sera el seed con IP publica).
        """
        if self._punch_manager is None:
            return

        with self._lock:
            # Estados de punch ya activos
            active_punch_fps = set(self._punch_manager._punch_states.keys())

            # Candidatos: peers reales con endpoint y sin punch activo
            candidates = [
                p for p in self._peers.values()
                if p.punch_endpoint
                and p.punch_endpoint.get("ip")
                and p.fingerprint not in active_punch_fps
                and not p.fingerprint.startswith(("seed:", "beacon:"))
                and not self._is_blacklisted(p.fingerprint)
                and now - p.last_seen < PEER_TIMEOUT
                and p.fingerprint != self._fingerprint
            ]

            # Coordinador: primer peer relay_capable
            coordinator_fp = ""
            for p in self._peers.values():
                if (p.relay_capable
                    and p.ip
                    and not self._is_blacklisted(p.fingerprint)
                    and now - p.last_seen < PEER_TIMEOUT):
                    coordinator_fp = p.fingerprint
                    break

        if not candidates or not coordinator_fp:
            return

        # Coger el primer candidato (uno por ciclo)
        target = candidates[0]
        # Evitar pedir al coordinador que sea su propio target
        if target.fingerprint == coordinator_fp:
            if len(candidates) < 2:
                return
            target = candidates[1]

        self._request_punch(target.fingerprint, coordinator_fp)

    def _request_punch(self, target_fp: str, coordinator_fp: str) -> bool:
        """Pide a un coordinador que coordine un punch hacia un peer.

        Envia pongia_punch_req via TCP, recibe pongia_punch_resp, y
        si la respuesta es valida llama a PunchManager.initiate_punch
        para empezar a abrir el hueco NAT.

        Retorna True si el punch se inicio, False si fallo (sin red,
        sin coordinador, sin consent, etc).
        """
        if self._punch_manager is None:
            return False

        with self._lock:
            coordinator = self._peers.get(coordinator_fp)
            if not coordinator or not coordinator.ip:
                return False
            ip, port = coordinator.ip, coordinator.data_port
            is_temporary = coordinator_fp.startswith(("seed:", "beacon:"))
            expected_vk = coordinator.verify_key

        msg = json.dumps({
            "type": "pongia_punch_req",
            "v": PROTOCOL_VERSION,
            "fp": self._fingerprint,
            "target_fp": target_fp,
        })

        raw = self._tcp_exchange(
            ip, port, msg,
            expected_fp="" if is_temporary else coordinator_fp,
            expected_vk="" if is_temporary else expected_vk,
        )
        if not raw:
            return False

        try:
            resp = json.loads(raw)
            if resp.get("type") != "pongia_punch_resp":
                return False
            tier = resp.get("tier", "")
            circuit_id = resp.get("circuit_id", "")
            target_vk = resp.get("target_vk", "")

            if tier == "direct":
                target_ep = resp.get("target_ep", {})
                if not target_ep or not circuit_id:
                    return False
                self._punch_manager.initiate_punch(
                    target_fp=target_fp,
                    target_ep=target_ep,
                    target_vk=target_vk,
                    circuit_id=circuit_id,
                )
                logger.info(
                    "punch: iniciado DIRECT con %s via %s",
                    target_fp[:8], coordinator_fp[:8],
                )
                return True

            if tier == "relay":
                relay = resp.get("relay", {})
                relay_ep = relay.get("ep", {})
                relay_fp = relay.get("fp", "")
                if not relay_ep or not circuit_id or not relay_fp:
                    return False

                # 1. Pedir al relay que abra el circuito (via TCP)
                target_peer = self._peers.get(target_fp)
                target_ep = (
                    target_peer.punch_endpoint if target_peer else {}
                )
                setup_msg = json.dumps({
                    "type": "pongia_relay_setup",
                    "v": PROTOCOL_VERSION,
                    "circuit_id": circuit_id,
                    "peer_a": {"fp": self._fingerprint, "ep": {
                        "ip": relay_ep.get("ip", ""),
                        "port": relay_ep.get("port", 0),
                    }},
                    "peer_b": {"fp": target_fp, "ep": target_ep},
                })
                # Setup es fire-and-forget: no esperamos respuesta util
                self._tcp_exchange(
                    relay_ep.get("ip", ""),
                    relay_ep.get("port", 0),
                    setup_msg,
                    expected_fp=relay_fp,
                    expected_vk=relay.get("vk", ""),
                )

                # 2. Iniciar punch con target_fp, pero enviando via relay
                relay_addr = (relay_ep.get("ip", ""), int(relay_ep.get("port", 0)))
                self._punch_manager.initiate_punch(
                    target_fp=target_fp,
                    target_ep=target_ep or {"ip": relay_addr[0], "port": relay_addr[1]},
                    target_vk=target_vk,
                    circuit_id=circuit_id,
                )
                # Marcar el state con via_relay para que use el wrap
                with self._punch_manager._lock:
                    st = self._punch_manager._punch_states.get(target_fp)
                    if st is not None:
                        st.via_relay = relay_addr

                logger.info(
                    "punch: iniciado RELAY con %s via relay %s",
                    target_fp[:8], relay_fp[:8],
                )
                return True

            if tier == "onion":
                circuit = resp.get("circuit", [])
                if not circuit or not target_vk or not circuit_id:
                    return False
                # target_ep para que la ultima capa entregue al destino real
                target_peer = self._peers.get(target_fp)
                target_ep = target_peer.punch_endpoint if target_peer else {}
                if not target_ep:
                    return False
                # Iniciar handshake onion (envia hs1 via circuit)
                ok = self._punch_manager.initiate_onion_handshake(
                    target_fp=target_fp,
                    target_vk=target_vk,
                    target_ep=target_ep,
                    circuit=circuit,
                )
                if ok:
                    logger.info(
                        "punch: iniciado ONION con %s (%d hops) via %s",
                        target_fp[:8], len(circuit), coordinator_fp[:8],
                    )
                return bool(ok)

            logger.debug("punch: tier %s desconocido", tier)
            return False
        except (json.JSONDecodeError, KeyError):
            return False

    # ================================================================
    # Onion: envio de hs2 (respuesta al iniciador) y data
    # ================================================================

    def _send_onion_hs2_response(
        self,
        sender_fp: str,
        sender_vk: str,
        my_eph_pk: bytes,
        peer_eph_pk: bytes,
        responds_to: str,
    ) -> None:
        """Responde al initiator via onion: pide circuito y envia hs2.

        Llamado por PunchManager cuando recibe un hs1 valido.
        Bob necesita su propio circuito para responder — lo pide al coordinador.
        """
        if self._punch_manager is None:
            return

        # Buscar coordinador (igual criterio que para _request_punch normal)
        now = time.time()
        coordinator_fp = ""
        with self._lock:
            for p in self._peers.values():
                if (p.relay_capable and p.ip
                    and not self._is_blacklisted(p.fingerprint)
                    and now - p.last_seen < PEER_TIMEOUT
                    and p.fingerprint != sender_fp):
                    coordinator_fp = p.fingerprint
                    break

        if not coordinator_fp:
            logger.warning("onion: sin coordinador para enviar hs2")
            return

        # Pedir circuito onion al coordinador hacia sender
        circuit = self._fetch_onion_circuit(sender_fp, coordinator_fp)
        if not circuit:
            logger.warning("onion: coordinador no dio circuito para hs2")
            return

        # Construir payload hs2 firmado
        # peer firma "onion_hs2|my_eph_pk|responds_to|peer_eph_pk_del_iniciador"
        # pero no conocemos eph_pk del iniciador aqui — lo pasamos como string vacio
        # En lugar, reutilizamos my_eph_pk para cerrar el ciclo: firmamos
        # "onion_hs2|my_eph_pk|responds_to|our_eph_pk"  (A verifica con our_eph_pk de A)
        # IMPORTANTE: necesitamos que A verifique con SU eph_pk_A. Pasamos our_eph_pk
        # = eph_pk_A (que deberia estar en PunchManager._onion_sessions o lo miramos)
        # Simplificacion: usamos una firma distinta que incluye responds_to y my_eph_pk.
        # A verificara y confia en que el nonce responds_to es unico.

        from nacl.signing import SigningKey
        sk = SigningKey(bytes.fromhex(self._signing_key))
        # Firmamos bob_eph_pk + responds_to + alice_eph_pk (binding bidireccional)
        to_sign = (
            b"onion_hs2|"
            + my_eph_pk.hex().encode()
            + b"|" + responds_to.encode()
            + b"|" + peer_eph_pk.hex().encode()
        )
        sig = sk.sign(to_sign).signature.hex()

        hs2 = json.dumps({
            "t": "onion_hs2",
            "v": PROTOCOL_VERSION,
            "sender_fp": self._fingerprint,
            "sender_vk": self._verify_key,
            "eph_pk": my_eph_pk.hex(),
            "responds_to": responds_to,
            "sig": sig,
        }).encode("utf-8")

        # Enviar hs2 via onion
        target_peer = self._peers.get(sender_fp)
        target_ep = target_peer.punch_endpoint if target_peer else {}
        if not target_ep:
            logger.warning("onion: sin punch_endpoint del iniciador")
            return

        result = self._punch_manager.wrap_onion_message(hs2, circuit, target_ep)
        if result is None:
            return
        onion_bytes, first_hop = result
        try:
            self._punch_manager._udp_sock.sendto(onion_bytes, first_hop)
            logger.info("onion: hs2 enviado a %s", sender_fp[:8])
        except OSError as exc:
            logger.warning("onion: fallo envio hs2: %s", exc)

    def _send_onion_data_to(
        self, target_fp: str, circuit: list[dict[str, Any]],
    ) -> None:
        """Envia nuestros records cifrados al target via onion data message."""
        if self._punch_manager is None:
            return

        from pong.crypto import aead_encrypt
        session = self._punch_manager._onion_sessions.get(target_fp)
        if session is None or not session.session_key:
            return

        records_json = self._build_records_message()
        records_ct = aead_encrypt(
            session.session_key, records_json.encode("utf-8"),
        )
        records_ct_hex = records_ct.hex()

        from nacl.signing import SigningKey
        sk = SigningKey(bytes.fromhex(self._signing_key))
        to_sign = b"onion_data|" + records_ct_hex.encode()
        sig = sk.sign(to_sign).signature.hex()

        data = json.dumps({
            "t": "onion_data",
            "v": PROTOCOL_VERSION,
            "sender_fp": self._fingerprint,
            "records_ct": records_ct_hex,
            "sig": sig,
        }).encode("utf-8")

        target_peer = self._peers.get(target_fp)
        target_ep = target_peer.punch_endpoint if target_peer else {}
        if not target_ep:
            return

        result = self._punch_manager.wrap_onion_message(data, circuit, target_ep)
        if result is None:
            return
        onion_bytes, first_hop = result
        try:
            self._punch_manager._udp_sock.sendto(onion_bytes, first_hop)
            logger.info("onion: data enviado a %s", target_fp[:8])
        except OSError:
            pass

    def _fetch_onion_circuit(
        self, target_fp: str, coordinator_fp: str,
    ) -> list[dict[str, Any]]:
        """Pide al coordinador un circuito onion hacia target. Lista vacia si falla."""
        with self._lock:
            coord = self._peers.get(coordinator_fp)
            if not coord or not coord.ip:
                return []
            ip, port = coord.ip, coord.data_port
            expected_vk = coord.verify_key
            is_temp = coordinator_fp.startswith(("seed:", "beacon:"))

        msg = json.dumps({
            "type": "pongia_punch_req",
            "v": PROTOCOL_VERSION,
            "fp": self._fingerprint,
            "target_fp": target_fp,
        })
        raw = self._tcp_exchange(
            ip, port, msg,
            expected_fp="" if is_temp else coordinator_fp,
            expected_vk="" if is_temp else expected_vk,
        )
        if not raw:
            return []
        try:
            resp = json.loads(raw)
            if resp.get("type") != "pongia_punch_resp":
                return []
            if resp.get("tier") != "onion":
                return []
            circuit: list[dict[str, Any]] = resp.get("circuit", [])
            return circuit
        except (json.JSONDecodeError, KeyError):
            return []

    # ================================================================
    # Construccion y procesamiento de mensajes
    # ================================================================

    def _build_records_message(self) -> str:
        """Construye mensaje JSON con TODOS los records conocidos.

        Cada nodo retransmite las entries de otros jugadores, igual que
        Bitcoin retransmite transacciones. Las entries siguen firmadas
        por su autor original (Ed25519), asi que cualquier nodo puede
        verificarlas independientemente.

        Se incluye un directorio ``peers`` con la verify_key de cada
        autor para que el receptor pueda validar las firmas.
        """
        with self._lock:
            all_entries = list(self._local_entries) + list(self._remote_entries)
            # Deduplicar por (fingerprint, category) — quedarse con la mas reciente
            best: dict[tuple[str, str], LeaderboardEntry] = {}
            for e in all_entries:
                key = (e.fingerprint, e.category)
                prev = best.get(key)
                if prev is None or (e.date and (not prev.date or e.date > prev.date)):
                    best[key] = e
            deduped = list(best.values())

            # Directorio de verify_keys por fingerprint
            peers_dir: dict[str, dict[str, str]] = {}
            if self._verify_key:
                peers_dir[self._fingerprint] = {
                    "vk": self._verify_key,
                    "alias": self._alias,
                }
            for peer in self._peers.values():
                if (
                    peer.verify_key
                    and not peer.fingerprint.startswith(("seed:", "beacon:"))
                ):
                    peers_dir[peer.fingerprint] = {
                        "vk": peer.verify_key,
                        "alias": peer.alias,
                    }

        msg: dict[str, Any] = {
            "type": "pongia_records",
            "v": PROTOCOL_VERSION,
            "fp": self._fingerprint,
            "alias": self._alias,
            "vk": self._verify_key,
            "peers": peers_dir,
            "records": [e.to_dict() for e in deduped[:MAX_ENTRIES_PER_MESSAGE]],
        }
        # Campos NAT traversal (opcional, solo si PunchManager activo)
        if self._punch_manager is not None:
            try:
                ref = self._punch_manager.reflexive
                if ref is not None:
                    msg["punch_ep"] = ref.to_dict()
                if self._punch_manager.relay_volunteer:
                    msg["relay_capable"] = True
            except Exception:
                pass  # Degradacion silenciosa — el campo simplemente no se envia
        return json.dumps(msg)

    def _build_peers_message(self) -> str:
        """Construye mensaje JSON con nuestra lista de peers (sin IPs)."""
        with self._lock:
            peers = [
                {
                    "fp": p.fingerprint,
                    "alias": p.alias,
                }
                for p in self._peers.values()
                if time.time() - p.last_seen < PEER_TIMEOUT
                and not p.fingerprint.startswith(("seed:", "beacon:"))
                and not self._is_blacklisted(p.fingerprint)
            ]
        return json.dumps({
            "type": "pongia_peers",
            "v": PROTOCOL_VERSION,
            "fp": self._fingerprint,
            "peers": peers,
        })

    def _add_strike(self, fp: str) -> None:
        """Incrementa strikes de un peer por fingerprint."""
        with self._lock:
            self._peer_strikes[fp] = self._peer_strikes.get(fp, 0) + 1
            self._strike_times[fp] = time.time()
            if self._peer_strikes[fp] >= MAX_STRIKES:
                logger.warning("P2P: peer %s alcanza %d strikes — ignorado", fp, MAX_STRIKES)

    def _add_strike_by_ip(self, ip: str) -> None:
        """Incrementa strikes de un peer buscando por IP."""
        with self._lock:
            for peer in self._peers.values():
                if peer.ip == ip:
                    self._peer_strikes[peer.fingerprint] = (
                        self._peer_strikes.get(peer.fingerprint, 0) + 1
                    )
                    return

    _STRIKE_EXPIRY = 3600  # 1 hora: los strikes expiran y el peer puede reintentar

    def _is_blacklisted(self, fp: str) -> bool:
        """Comprueba si un peer esta en blacklist (strikes expiran tras 1h)."""
        strikes = self._peer_strikes.get(fp, 0)
        if strikes < MAX_STRIKES:
            return False
        # Expirar strikes si el ultimo fue hace mas de 1h
        last = self._strike_times.get(fp, 0)
        if time.time() - last > self._STRIKE_EXPIRY:
            self._peer_strikes.pop(fp, None)
            self._strike_times.pop(fp, None)
            return False
        return True

    @staticmethod
    def _merge_author_records(
        existing: list[LeaderboardEntry],
        incoming: list[LeaderboardEntry],
    ) -> list[LeaderboardEntry]:
        """Mergea records del mismo autor: por categoria, quedarse con el mas reciente."""
        by_cat: dict[str, LeaderboardEntry] = {e.category: e for e in existing}
        for e in incoming:
            prev = by_cat.get(e.category)
            if prev is None or (e.date and (not prev.date or e.date > prev.date)):
                by_cat[e.category] = e
        return list(by_cat.values())

    def _handle_records_message(self, msg: dict[str, Any], ip: str) -> None:
        """Procesa records recibidos de un peer.

        Un mensaje puede contener entries de multiples autores (relay).
        Cada entry se valida contra la verify_key de su autor original,
        no contra la del sender. El directorio ``peers`` proporciona
        las verify_keys necesarias.
        """
        sender_fp = msg.get("fp", "")
        sender_alias = msg.get("alias", "")
        sender_vk = msg.get("vk", "")
        raw_records = msg.get("records", [])
        peers_dir: dict[str, dict[str, str]] = msg.get("peers", {})

        if not sender_fp or sender_fp == self._fingerprint:
            return
        if self._is_blacklisted(sender_fp):
            return
        resolved_sender_vk = self._pin_verify_key(sender_fp, sender_vk)
        if resolved_sender_vk is None:
            return

        # Asegurar que el sender este en el directorio
        peers_dir.setdefault(sender_fp, {})
        peers_dir[sender_fp]["vk"] = resolved_sender_vk
        peers_dir[sender_fp].setdefault("alias", sender_alias)

        # Limitar entries por mensaje
        if len(raw_records) > MAX_ENTRIES_PER_MESSAGE:
            raw_records = raw_records[:MAX_ENTRIES_PER_MESSAGE]

        from datetime import datetime, timedelta, timezone
        now_ts = datetime.now(timezone.utc)

        entries_by_author: dict[str, list[LeaderboardEntry]] = {}
        invalid_count = 0

        for raw in raw_records:
            entry = LeaderboardEntry.from_dict(raw)
            author_fp = entry.fingerprint

            if not author_fp or author_fp == self._fingerprint:
                continue
            if self._is_blacklisted(author_fp):
                continue

            # Buscar vk del autor en el directorio de peers
            author_info = peers_dir.get(author_fp, {})
            author_vk = author_info.get("vk", "")
            if not author_vk:
                continue  # Sin vk no se puede verificar

            resolved_author_vk = self._pin_verify_key(author_fp, author_vk)
            if resolved_author_vk is None:
                continue

            # Validacion de timestamp
            if entry.date:
                try:
                    entry_date = datetime.fromisoformat(entry.date)
                    if entry_date.tzinfo is None:
                        entry_date = entry_date.replace(tzinfo=timezone.utc)
                    if entry_date > now_ts + timedelta(hours=24):
                        continue
                    if entry_date < now_ts - timedelta(days=365):
                        continue
                except (ValueError, TypeError):
                    pass

            # Verificacion de firma contra la vk del AUTOR (no del sender)
            if verify_entry(entry, resolved_author_vk):
                if check_plausibility(entry):
                    entries_by_author.setdefault(author_fp, []).append(entry)
                else:
                    logger.warning(
                        "P2P: record implausible rechazado de %s: %s=%s",
                        author_fp, entry.category, entry.value,
                    )
            else:
                invalid_count += 1

        if invalid_count > 0:
            self._add_strike(sender_fp)

        with self._lock:
            now = time.time()

            # Actualizar peer info del sender
            if sender_fp in self._peers:
                self._peers[sender_fp].last_seen = now
                self._peers[sender_fp].alias = sender_alias
                self._peers[sender_fp].ip = ip
                self._peers[sender_fp].verify_key = resolved_sender_vk
            elif len(self._peers) < MAX_PEERS:
                self._peers_ever_seen += 1
                self._peers[sender_fp] = PeerInfo(
                    fingerprint=sender_fp,
                    alias=sender_alias,
                    ip=ip,
                    data_port=DATA_PORT,
                    verify_key=resolved_sender_vk,
                )

            # Almacenar records agrupados por autor
            for author_fp, new_entries in entries_by_author.items():
                if author_fp in self._peers:
                    self._peers[author_fp].records = self._merge_author_records(
                        self._peers[author_fp].records, new_entries,
                    )
                elif len(self._peers) < MAX_PEERS:
                    author_info = peers_dir.get(author_fp, {})
                    self._peers_ever_seen += 1
                    self._peers[author_fp] = PeerInfo(
                        fingerprint=author_fp,
                        alias=author_info.get("alias", ""),
                        ip="",
                        data_port=0,
                        records=new_entries,
                        verify_key=author_info.get("vk", ""),
                    )

            # Reconstruir lista completa de entries remotas
            self._remote_entries = []
            for peer in self._peers.values():
                self._remote_entries.extend(peer.records)

            # Campos NAT traversal del sender (si los incluyo en el mensaje)
            punch_ep = msg.get("punch_ep")
            if isinstance(punch_ep, dict) and sender_fp in self._peers:
                self._peers[sender_fp].punch_endpoint = punch_ep
            if msg.get("relay_capable") and sender_fp in self._peers:
                self._peers[sender_fp].relay_capable = True

            # Registrar intercambio exitoso (para consent del punch)
            self._exchanged_with.add(sender_fp)

    def _handle_peers_message(self, msg: dict[str, Any]) -> None:
        """Procesa lista de peers recibida via gossip (sin IPs — solo identidades)."""
        raw_peers = msg.get("peers", [])

        for raw in raw_peers:
            fp = raw.get("fp", "")
            if not fp or fp == self._fingerprint:
                continue
            if self._is_blacklisted(fp):
                continue

            with self._lock:
                if fp not in self._peers:
                    if len(self._peers) >= MAX_PEERS:
                        break
                    # Solo registrar identidad; sin IP no es contactable
                    # directamente (se necesita beacon LAN o seed WAN)
                    self._peers[fp] = PeerInfo(
                        fingerprint=fp,
                        alias=raw.get("alias", ""),
                        ip="",
                        data_port=0,
                        last_seen=0,
                    )
                else:
                    peer = self._peers[fp]
                    if raw.get("alias"):
                        peer.alias = raw["alias"]

    # ================================================================
    # Cache
    # ================================================================

    def _cache_save_loop(self) -> None:
        """Guarda el cache de peers periodicamente."""
        while self._running:
            for _ in range(CACHE_SAVE_INTERVAL):
                if not self._running:
                    return
                time.sleep(1)
            self._save_cache()

    def _save_cache(self) -> None:
        """Persiste los peers conocidos a disco."""
        with self._lock:
            peers = [
                {
                    "ip": p.ip,
                    "port": p.data_port,
                    "fp": p.fingerprint,
                    "alias": p.alias,
                    "vk": p.verify_key,
                    "last_seen": p.last_seen,
                }
                for p in self._peers.values()
                if not p.fingerprint.startswith("seed:")
            ]
        existing = load_peer_cache(self._cache_path)
        merged = merge_peer_cache(existing, peers)
        save_peer_cache(self._cache_path, merged)

    # ================================================================
    # Handshake cifrado (X25519 efimero + XChaCha20-Poly1305 + Ed25519)
    # ================================================================

    def _static_curve25519_keys(self) -> tuple[bytes, bytes] | None:
        """Devuelve (private, public) Curve25519 derivados de las Ed25519 estaticas."""
        try:
            from nacl.signing import SigningKey, VerifyKey

            sk = SigningKey(bytes.fromhex(self._signing_key))
            vk = VerifyKey(bytes.fromhex(self._verify_key))
            return (
                bytes(sk.to_curve25519_private_key()),
                bytes(vk.to_curve25519_public_key()),
            )
        except Exception:
            return None

    @staticmethod
    def _peer_curve25519_public(peer_vk_hex: str) -> bytes:
        """Convierte verify_key Ed25519 (hex) a Curve25519 public key (bytes)."""
        from nacl.signing import VerifyKey

        return bytes(VerifyKey(bytes.fromhex(peer_vk_hex)).to_curve25519_public_key())

    def _derive_session_key(
        self,
        my_eph_sk: bytes,
        peer_eph_pk: bytes,
        peer_vk_hex: str,
    ) -> bytes:
        """Triple ECDH → session key con forward secrecy.

        session_key = Blake2b(
            key = ECDH(eph, eph),
            data = ECDH(static, peer_eph) || ECDH(my_eph, peer_static),
        )
        """
        ecdh_ee = ecdh(my_eph_sk, peer_eph_pk)

        static_keys = self._static_curve25519_keys()
        if static_keys is None:
            return derive_key(ecdh_ee, salt=b"pongia-session-4.0")
        my_static_sk, _ = static_keys
        peer_static_pk = self._peer_curve25519_public(peer_vk_hex)

        ecdh_se = ecdh(my_static_sk, peer_eph_pk)
        ecdh_es = ecdh(my_eph_sk, peer_static_pk)

        # Orden canonico: ambos lados deben producir el mismo context
        # independientemente de quien es client o server.
        pair = sorted([ecdh_se, ecdh_es])
        return derive_key(
            ecdh_ee,
            salt=b"pongia-session-4.0",
            context=pair[0] + pair[1],
        )

    def _handshake_client(
        self,
        sock: socket.socket,
        *,
        expected_fp: str = "",
        expected_vk: str = "",
    ) -> bytes | None:
        """Handshake cifrado desde el primer byte + forward secrecy.

        Paso 1: intercambio efimero X25519 (lo unico plaintext, no revela identidad)
        Paso 2: auth mutua cifrada con XChaCha20-Poly1305 (dentro del canal cifrado)
        Paso 3: session key via triple ECDH
        """
        try:
            if not self._signing_key or not self._verify_key or not self._fingerprint:
                return None

            # --- Paso 1: intercambio efimero ---
            my_eph_sk, my_eph_pk = generate_ephemeral_x25519()
            eph_hello = json.dumps({
                "t": "eph",
                "v": PROTOCOL_VERSION,
                "pk": my_eph_pk.hex(),
            })
            self._send_message(sock, eph_hello)

            raw = self._recv_message(sock)
            if not raw:
                return None
            eph_resp = json.loads(raw)
            if eph_resp.get("t") != "eph" or eph_resp.get("v") != PROTOCOL_VERSION:
                return None

            pk_hex = eph_resp.get("pk", "")
            if len(pk_hex) != 64:  # X25519 = 32 bytes = 64 hex
                return None
            peer_eph_pk = bytes.fromhex(pk_hex)
            ecdh_ee = ecdh(my_eph_sk, peer_eph_pk)
            temp_key = derive_key(ecdh_ee, salt=b"pongia-hs-4.0")

            # --- Paso 2: recibir auth del server (cifrada) ---
            raw_enc = self._recv_raw(sock)
            if raw_enc is None:
                return None
            try:
                auth_bytes = aead_decrypt(temp_key, raw_enc)
            except Exception:
                return None
            server_auth = json.loads(auth_bytes.decode("utf-8"))

            server_fp = server_auth.get("fp", "")
            server_vk = server_auth.get("vk", "")
            server_nonce = server_auth.get("nonce", "")
            server_sig = server_auth.get("sig", "")

            if expected_fp and server_fp != expected_fp:
                return None
            if expected_vk and server_vk != expected_vk:
                return None
            if not self._has_consistent_identity(server_fp, server_vk):
                return None

            # El server firmo SIN conocer al client → verificar con campos vacios
            # client_eph_pk y server_eph_pk desde la perspectiva correcta:
            #   my_eph_pk = client's eph pk ; peer_eph_pk = server's eph pk
            server_payload = self._handshake_payload(
                role="server",
                client_fp="",
                client_vk="",
                client_nonce="",
                client_eph_pk=my_eph_pk.hex(),
                server_fp=server_fp,
                server_vk=server_vk,
                server_nonce=server_nonce,
                server_eph_pk=peer_eph_pk.hex(),
            )
            if not self._verify_handshake_signature(
                server_payload, server_sig, server_vk,
            ):
                return None

            self._pin_verify_key(server_fp, server_vk)

            # Enviar auth del client (cifrada)
            client_nonce = secrets.token_hex(16)
            client_payload = self._handshake_payload(
                role="client",
                client_fp=self._fingerprint,
                client_vk=self._verify_key,
                client_nonce=client_nonce,
                client_eph_pk=my_eph_pk.hex(),
                server_fp=server_fp,
                server_vk=server_vk,
                server_nonce=server_nonce,
                server_eph_pk=peer_eph_pk.hex(),
            )
            auth_msg = json.dumps({
                "fp": self._fingerprint,
                "vk": self._verify_key,
                "nonce": client_nonce,
                "sig": self._sign_handshake_payload(client_payload),
            })
            ct = aead_encrypt(temp_key, auth_msg.encode("utf-8"))
            self._send_raw(sock, ct)

            # --- Paso 3: session key con forward secrecy ---
            return self._derive_session_key(my_eph_sk, peer_eph_pk, server_vk)
        except Exception as exc:
            logger.warning("P2P: handshake cliente fallido: %s", exc)
            return None

    def _handshake_server(self, sock: socket.socket, ip: str) -> bytes | None:
        """Handshake servidor cifrado desde el primer byte + forward secrecy."""
        try:
            if not self._signing_key or not self._verify_key or not self._fingerprint:
                return None

            # --- Paso 1: recibir efimero del client ---
            raw = self._recv_message(sock)
            if not raw:
                return None
            eph_hello = json.loads(raw)
            if eph_hello.get("t") != "eph" or eph_hello.get("v") != PROTOCOL_VERSION:
                return None

            pk_hex = eph_hello.get("pk", "")
            if len(pk_hex) != 64:  # X25519 = 32 bytes = 64 hex
                return None
            peer_eph_pk = bytes.fromhex(pk_hex)

            # Generar nuestro efimero y enviarlo
            my_eph_sk, my_eph_pk = generate_ephemeral_x25519()
            eph_resp = json.dumps({
                "t": "eph",
                "v": PROTOCOL_VERSION,
                "pk": my_eph_pk.hex(),
            })
            self._send_message(sock, eph_resp)

            ecdh_ee = ecdh(my_eph_sk, peer_eph_pk)
            temp_key = derive_key(ecdh_ee, salt=b"pongia-hs-4.0")

            # --- Paso 2: enviar auth del server (cifrada) ---
            server_nonce = secrets.token_hex(16)
            server_payload = self._handshake_payload(
                role="server",
                client_fp="",
                client_vk="",
                client_nonce="",
                client_eph_pk=peer_eph_pk.hex(),
                server_fp=self._fingerprint,
                server_vk=self._verify_key,
                server_nonce=server_nonce,
                server_eph_pk=my_eph_pk.hex(),
            )
            auth_msg = json.dumps({
                "fp": self._fingerprint,
                "vk": self._verify_key,
                "nonce": server_nonce,
                "sig": self._sign_handshake_payload(server_payload),
            })
            ct = aead_encrypt(temp_key, auth_msg.encode("utf-8"))
            self._send_raw(sock, ct)

            # Recibir auth del client (cifrada)
            raw_enc = self._recv_raw(sock)
            if raw_enc is None:
                return None
            try:
                auth_bytes = aead_decrypt(temp_key, raw_enc)
            except Exception:
                self._add_strike_by_ip(ip)
                return None
            client_auth = json.loads(auth_bytes.decode("utf-8"))

            client_fp = client_auth.get("fp", "")
            client_vk = client_auth.get("vk", "")
            client_nonce = client_auth.get("nonce", "")
            client_sig = client_auth.get("sig", "")

            if not self._has_consistent_identity(client_fp, client_vk):
                self._add_strike_by_ip(ip)
                return None

            client_payload = self._handshake_payload(
                role="client",
                client_fp=client_fp,
                client_vk=client_vk,
                client_nonce=client_nonce,
                client_eph_pk=peer_eph_pk.hex(),
                server_fp=self._fingerprint,
                server_vk=self._verify_key,
                server_nonce=server_nonce,
                server_eph_pk=my_eph_pk.hex(),
            )
            if not self._verify_handshake_signature(
                client_payload, client_sig, client_vk,
            ):
                self._add_strike_by_ip(ip)
                return None

            self._pin_verify_key(client_fp, client_vk)

            # --- Paso 3: session key con forward secrecy ---
            return self._derive_session_key(my_eph_sk, peer_eph_pk, client_vk)
        except Exception as exc:
            logger.warning("P2P: handshake servidor fallido: %s", exc)
            return None

    # ================================================================
    # Transporte de mensajes (length-prefixed, XChaCha20-Poly1305)
    # ================================================================

    @staticmethod
    def _send_raw(sock: socket.socket, data: bytes) -> None:
        """Envia bytes con prefijo de longitud (4 bytes big-endian)."""
        if len(data) > MAX_MSG_SIZE:
            data = data[:MAX_MSG_SIZE]
        header = struct.pack("!I", len(data))
        sock.sendall(header + data)

    @staticmethod
    def _recv_raw(sock: socket.socket) -> bytes | None:
        """Recibe bytes con prefijo de longitud."""
        try:
            header = b""
            while len(header) < 4:
                chunk = sock.recv(4 - len(header))
                if not chunk:
                    return None
                header += chunk

            (length,) = struct.unpack("!I", header)
            if length > MAX_MSG_SIZE:
                return None

            data = b""
            while len(data) < length:
                chunk = sock.recv(min(length - len(data), 4096))
                if not chunk:
                    return None
                data += chunk
            return data
        except OSError:
            return None

    @staticmethod
    def _send_message(
        sock: socket.socket, msg: str, key: bytes | None = None,
    ) -> None:
        """Envia un mensaje JSON con prefijo de longitud.

        Si ``key`` se proporciona, el mensaje se cifra con XChaCha20-Poly1305.
        """
        data = msg.encode("utf-8")
        if key is not None:
            data = aead_encrypt(key, data)
        PeerNetwork._send_raw(sock, data)

    @staticmethod
    def _recv_message(sock: socket.socket, key: bytes | None = None) -> str | None:
        """Recibe un mensaje JSON con prefijo de longitud.

        Si ``key`` se proporciona, el mensaje se descifra con XChaCha20-Poly1305.
        """
        try:
            data = PeerNetwork._recv_raw(sock)
            if data is None:
                return None
            if key is not None:
                data = aead_decrypt(key, data)
            return data.decode("utf-8")
        except (UnicodeDecodeError, OSError):
            return None
        except Exception:
            logger.debug("P2P: error descifrando mensaje")
            return None
