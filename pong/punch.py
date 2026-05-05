"""
pong/punch.py -- NAT traversal con privacidad adaptativa.

Tres niveles de privacidad segun el tamanio de la red:
  DIRECT (< 8 peers)  — UDP hole punch directo entre peers
  RELAY  (8-14 peers) — 1-hop relay, solo el relay ve ambas IPs
  ONION  (>= 15 peers) — 3-hop onion routing, nadie sabe ambos extremos

Dependencias: pong.crypto (XChaCha20-Poly1305, X25519, Blake2b).
"""

from __future__ import annotations

import enum
import json
import logging
import secrets
import socket
import struct
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pong.crypto import (
    aead_decrypt,
    aead_encrypt,
    derive_key,
    ecdh,
    generate_ephemeral_x25519,
)

if TYPE_CHECKING:
    from pong.p2p import PeerNetwork

logger = logging.getLogger("pongia.punch")

# ================================================================
# Constantes
# ================================================================

PUNCH_PORT = 19849
STUN_INTERVAL = 25
PUNCH_INTERVAL = 0.5
PUNCH_TIMEOUT = 30
KEEPALIVE_INTERVAL = 20
MAX_PUNCH_REQ_PER_MIN = 5
TIER_RELAY = 8
TIER_ONION = 15
ONION_HOPS = 3
MAX_UDP_SIZE = 65536
STUN_TIMEOUT = 3
ENDPOINT_EXPIRY = 60
RELAY_CIRCUIT_TTL = 300
MAX_RELAY_PACKETS_PER_MIN = 100

PROTOCOL_VERSION = "4.0"

MAX_RELAY_CIRCUITS = 50  # limite de circuitos relay simultaneos


def _is_private_ip(ip: str) -> bool:
    """Devuelve True si la IP es privada, loopback o reservada."""
    import ipaddress
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_private or addr.is_loopback or addr.is_reserved
    except ValueError:
        return True  # IP invalida → bloquear


# ================================================================
# Enums y dataclasses
# ================================================================

class PrivacyTier(enum.Enum):
    DIRECT = "direct"
    RELAY = "relay"
    ONION = "onion"


@dataclass
class ReflexiveEndpoint:
    """Endpoint publico observado por STUN (IP:puerto tras NAT)."""
    ip: str = ""
    port: int = 0
    timestamp: float = 0
    is_public: bool = False

    def is_fresh(self) -> bool:
        return bool(self.ip) and time.time() - self.timestamp < ENDPOINT_EXPIRY

    def to_dict(self) -> dict[str, Any]:
        return {"ip": self.ip, "port": self.port, "ts": self.timestamp}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ReflexiveEndpoint:
        return cls(
            ip=str(d.get("ip", "")),
            port=int(d.get("port", 0)),
            timestamp=float(d.get("ts", 0)),
        )


@dataclass
class PunchState:
    """Estado de un intento de punch en curso."""
    target_fp: str
    target_endpoint: tuple[str, int]
    target_vk: str
    circuit_id: str
    phase: str = "punching"
    started: float = field(default_factory=time.time)
    session_key: bytes | None = None
    my_eph_sk: bytes = b""
    my_eph_pk: bytes = b""
    peer_eph_pk: bytes = b""
    last_activity: float = field(default_factory=time.time)
    # Si no es None, el trafico para este circuito va envuelto \x02|cid|...
    # y dirigido a via_relay (en vez de direct a target_endpoint).
    via_relay: tuple[str, int] | None = None


@dataclass
class RelayCircuit:
    """Circuito relay/onion activo."""
    circuit_id: str
    tier: PrivacyTier
    hops: list[dict[str, Any]] = field(default_factory=list)
    target_fp: str = ""
    target_vk: str = ""
    created: float = field(default_factory=time.time)
    peer_a_endpoint: tuple[str, int] = ("", 0)
    peer_b_endpoint: tuple[str, int] = ("", 0)
    packets_forwarded: int = 0
    last_activity: float = field(default_factory=time.time)


@dataclass
class OnionHandshake:
    """Estado de un handshake onion iniciado (esperando hs2).

    Se crea en el iniciador (A) al enviar onion_hs1. Se consume cuando
    recibimos onion_hs2 del mismo nonce para derivar la session_key.
    """
    peer_fp: str
    peer_vk: str            # vk conocida del peer (para verificar firma hs2)
    my_eph_sk: bytes
    my_eph_pk: bytes
    nonce: str
    circuit: list[dict[str, Any]] = field(default_factory=list)
    started: float = field(default_factory=time.time)


@dataclass
class OnionSession:
    """Sesion onion establecida — session_key cacheada con expiracion."""
    peer_fp: str
    peer_vk: str
    session_key: bytes
    created: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)


# Expiracion de handshakes pendientes / sesiones
ONION_HS_TIMEOUT = 30          # Segundos esperando hs2 antes de abortar
ONION_SESSION_TTL = 600        # Segundos de vida de session_key cacheada


# ================================================================
# Helpers
# ================================================================

def current_tier(active_peers: int) -> PrivacyTier:
    """Determina el tier de privacidad segun peers activos."""
    if active_peers >= TIER_ONION:
        return PrivacyTier.ONION
    if active_peers >= TIER_RELAY:
        return PrivacyTier.RELAY
    return PrivacyTier.DIRECT


def subnet_24(ip: str) -> str:
    """Extrae prefijo /24 de una IP (primeros 3 octetos)."""
    parts = ip.split(".")
    return ".".join(parts[:3]) if len(parts) == 4 else ip


def _peer_curve25519_public(vk_hex: str) -> bytes:
    """Convierte Ed25519 verify_key (hex) a Curve25519 public (bytes)."""
    from nacl.signing import VerifyKey
    return bytes(VerifyKey(bytes.fromhex(vk_hex)).to_curve25519_public_key())


def _static_curve25519_private(signing_key_hex: str) -> bytes:
    """Convierte Ed25519 signing_key (hex) a Curve25519 private (bytes)."""
    from nacl.signing import SigningKey
    return bytes(SigningKey(bytes.fromhex(signing_key_hex)).to_curve25519_private_key())


# ================================================================
# PunchManager
# ================================================================

class PunchManager:
    """Gestiona NAT traversal, relay y onion routing."""

    # Permite relay a IPs privadas (solo para tests en localhost)
    _allow_private_relay: bool = False

    def __init__(self, network: PeerNetwork) -> None:
        self._network = network
        self._lock = threading.Lock()
        self._running = False

        self._reflexive: ReflexiveEndpoint = ReflexiveEndpoint()
        self._stun_servers: list[tuple[str, int]] = []
        self._udp_sock: socket.socket | None = None
        self._punch_states: dict[str, PunchState] = {}
        self._relay_circuits: dict[str, RelayCircuit] = {}
        self._relay_volunteer = False

        # Onion: handshakes en curso (keyed por nonce) y sesiones establecidas
        # (keyed por peer_fp)
        self._onion_pending: dict[str, OnionHandshake] = {}
        self._onion_sessions: dict[str, OnionSession] = {}
        self._punch_rate: dict[str, list[float]] = {}
        self._threads: list[threading.Thread] = []

    # ---- Properties ----

    @property
    def reflexive(self) -> ReflexiveEndpoint | None:
        with self._lock:
            return self._reflexive if self._reflexive.is_fresh() else None

    @property
    def relay_volunteer(self) -> bool:
        with self._lock:
            return self._relay_volunteer

    @property
    def current_tier(self) -> PrivacyTier:
        telemetry = self._network.get_telemetry()
        return current_tier(telemetry.get("active_peers", 0))

    # ---- Lifecycle ----

    def start(self) -> None:
        """Inicia STUN refresh y listener UDP."""
        self._running = True
        try:
            self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                self._udp_sock.bind(("", PUNCH_PORT))
            except OSError:
                self._udp_sock.bind(("", 0))
                logger.warning("punch: puerto %d ocupado, usando %d",
                               PUNCH_PORT, self._udp_sock.getsockname()[1])
            self._udp_sock.settimeout(1.0)
        except OSError as exc:
            logger.warning("punch: no se pudo crear socket UDP: %s", exc)
            self._udp_sock = None
            return

        self._discover_stun_servers()

        for name, target in [
            ("pongia-stun", self._stun_refresh_loop),
            ("pongia-punch-listener", self._udp_listener_loop),
        ]:
            t = threading.Thread(target=target, name=name, daemon=True)
            t.start()
            self._threads.append(t)

        logger.info("punch: iniciado en puerto %d", self._udp_sock.getsockname()[1])

    def stop(self) -> None:
        self._running = False
        if self._udp_sock:
            try:
                self._udp_sock.close()
            except OSError:
                pass

    def _discover_stun_servers(self) -> None:
        """Extrae STUN servers de los seeds conocidos."""
        with self._network._lock:
            for peer in self._network._peers.values():
                if peer.fingerprint.startswith("seed:") and peer.ip:
                    self._stun_servers.append((peer.ip, PUNCH_PORT))

    # ================================================================
    # STUN
    # ================================================================

    def _stun_refresh_loop(self) -> None:
        while self._running:
            self._do_stun()
            for _ in range(STUN_INTERVAL):
                if not self._running:
                    return
                time.sleep(1)

    def _do_stun(self) -> None:
        if not self._udp_sock or not self._stun_servers:
            return

        req = json.dumps({
            "t": "stun_req",
            "v": PROTOCOL_VERSION,
            "fp": self._network._fingerprint,
        }).encode("utf-8")

        for server_ip, server_port in self._stun_servers:
            try:
                self._udp_sock.sendto(req, (server_ip, server_port))
            except OSError:
                continue

            deadline = time.time() + STUN_TIMEOUT
            while time.time() < deadline:
                try:
                    data, addr = self._udp_sock.recvfrom(MAX_UDP_SIZE)
                    msg = json.loads(data.decode("utf-8"))
                    if msg.get("t") == "stun_resp" and msg.get("v") == PROTOCOL_VERSION:
                        ip = msg.get("ip", "")
                        port = msg.get("port", 0)
                        if ip and port:
                            with self._lock:
                                self._reflexive = ReflexiveEndpoint(
                                    ip=ip, port=port,
                                    timestamp=time.time(),
                                    is_public=(ip == self._get_local_ip()),
                                )
                                self._relay_volunteer = self._reflexive.is_public
                            logger.debug("punch: STUN -> %s:%d", ip, port)
                            return
                except socket.timeout:
                    break
                except (json.JSONDecodeError, OSError):
                    continue

    @staticmethod
    def _get_local_ip() -> str:
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe.connect(("8.8.8.8", 80))
            ip: str = probe.getsockname()[0]
            probe.close()
            return ip
        except OSError:
            return ""

    def handle_stun_request(self, data: bytes, addr: tuple[str, int]) -> None:
        """Responde a un STUN request."""
        if not self._udp_sock:
            return
        try:
            msg = json.loads(data.decode("utf-8"))
            if msg.get("t") != "stun_req" or msg.get("v") != PROTOCOL_VERSION:
                return
            resp = json.dumps({
                "t": "stun_resp",
                "v": PROTOCOL_VERSION,
                "ip": addr[0],
                "port": addr[1],
            }).encode("utf-8")
            self._udp_sock.sendto(resp, addr)
        except (json.JSONDecodeError, OSError):
            pass

    # ================================================================
    # Rate limiting + consent
    # ================================================================

    def _check_punch_rate(self, fp: str) -> bool:
        now = time.time()
        with self._lock:
            timestamps = self._punch_rate.get(fp, [])
            timestamps = [t for t in timestamps if now - t < 60]
            if len(timestamps) >= MAX_PUNCH_REQ_PER_MIN:
                return False
            timestamps.append(now)
            self._punch_rate[fp] = timestamps
        return True

    def _check_consent(self, requester_fp: str, target_fp: str) -> bool:
        exchanged = self._network._exchanged_with
        return requester_fp in exchanged and target_fp in exchanged

    # ================================================================
    # Punch coordination (coordinador)
    # ================================================================

    def handle_punch_request(
        self, msg: dict[str, Any], requester_ip: str,
    ) -> str | None:
        requester_fp = msg.get("fp", "")
        target_fp = msg.get("target_fp", "")

        if not requester_fp or not target_fp or requester_fp == target_fp:
            return None
        if not self._check_punch_rate(requester_fp):
            return None
        if not self._check_consent(requester_fp, target_fp):
            return None

        with self._network._lock:
            target = self._network._peers.get(target_fp)
            if not target:
                return None
            target_ep = getattr(target, "punch_endpoint", {})
            target_vk = target.verify_key

        if not target_ep or not target_ep.get("ip") or not target_ep.get("port"):
            return None

        tier = self.current_tier
        circuit_id = secrets.token_hex(16)

        if tier == PrivacyTier.DIRECT:
            return json.dumps({
                "type": "pongia_punch_resp", "v": PROTOCOL_VERSION,
                "tier": "direct", "circuit_id": circuit_id,
                "target_fp": target_fp, "target_ep": target_ep,
                "target_vk": target_vk,
            })

        if tier == PrivacyTier.RELAY:
            relay = self._select_relay_peer(
                exclude_fps={requester_fp, target_fp},
                exclude_subnets={subnet_24(requester_ip), subnet_24(target_ep.get("ip", ""))},
            )
            if relay is None:
                return json.dumps({
                    "type": "pongia_punch_resp", "v": PROTOCOL_VERSION,
                    "tier": "direct", "circuit_id": circuit_id,
                    "target_fp": target_fp, "target_ep": target_ep,
                    "target_vk": target_vk,
                })
            return json.dumps({
                "type": "pongia_punch_resp", "v": PROTOCOL_VERSION,
                "tier": "relay", "circuit_id": circuit_id,
                "relay": {"fp": relay.fingerprint, "ep": relay.punch_endpoint, "vk": relay.verify_key},
                "target_fp": target_fp, "target_vk": target_vk,
            })

        # ONION
        relays = self._select_relay_peers(
            count=ONION_HOPS,
            exclude_fps={requester_fp, target_fp},
            exclude_subnets={subnet_24(requester_ip), subnet_24(target_ep.get("ip", ""))},
        )
        if len(relays) < ONION_HOPS:
            if relays:
                r = relays[0]
                return json.dumps({
                    "type": "pongia_punch_resp", "v": PROTOCOL_VERSION,
                    "tier": "relay", "circuit_id": circuit_id,
                    "relay": {"fp": r.fingerprint, "ep": r.punch_endpoint, "vk": r.verify_key},
                    "target_fp": target_fp, "target_vk": target_vk,
                })
            return json.dumps({
                "type": "pongia_punch_resp", "v": PROTOCOL_VERSION,
                "tier": "direct", "circuit_id": circuit_id,
                "target_fp": target_fp, "target_ep": target_ep,
                "target_vk": target_vk,
            })

        return json.dumps({
            "type": "pongia_punch_resp", "v": PROTOCOL_VERSION,
            "tier": "onion", "circuit_id": circuit_id,
            "circuit": [{"fp": r.fingerprint, "ep": r.punch_endpoint, "vk": r.verify_key} for r in relays],
            "target_fp": target_fp, "target_vk": target_vk,
        })

    # ================================================================
    # Relay peer selection
    # ================================================================

    def _select_relay_peer(self, exclude_fps: set[str], exclude_subnets: set[str]) -> Any | None:
        peers = self._select_relay_peers(1, exclude_fps, exclude_subnets)
        return peers[0] if peers else None

    def _select_relay_peers(self, count: int, exclude_fps: set[str], exclude_subnets: set[str]) -> list[Any]:
        now = time.time()
        from pong.p2p import PEER_TIMEOUT
        with self._network._lock:
            candidates = [
                p for p in self._network._peers.values()
                if getattr(p, "relay_capable", False)
                and getattr(p, "punch_endpoint", None)
                and isinstance(getattr(p, "punch_endpoint", None), dict)
                and getattr(p, "punch_endpoint", {}).get("ip")
                and p.fingerprint not in exclude_fps
                and not self._network._is_blacklisted(p.fingerprint)
                and now - p.last_seen < PEER_TIMEOUT
            ]

        rng = secrets.SystemRandom()
        rng.shuffle(candidates)
        selected = []
        used_subnets = set(exclude_subnets)
        for c in candidates:
            sub = subnet_24(c.punch_endpoint.get("ip", ""))
            if sub not in used_subnets:
                selected.append(c)
                used_subnets.add(sub)
                if len(selected) >= count:
                    break
        return selected

    # ================================================================
    # UDP Punch (DIRECT)
    # ================================================================

    def initiate_punch(self, target_fp: str, target_ep: dict[str, Any], target_vk: str, circuit_id: str) -> None:
        ep = (target_ep.get("ip", ""), int(target_ep.get("port", 0)))
        if not ep[0] or not ep[1]:
            return
        eph_sk, eph_pk = generate_ephemeral_x25519()
        state = PunchState(
            target_fp=target_fp, target_endpoint=ep,
            target_vk=target_vk, circuit_id=circuit_id,
            my_eph_sk=eph_sk, my_eph_pk=eph_pk,
        )
        with self._lock:
            self._punch_states[target_fp] = state
        t = threading.Thread(target=self._punch_loop, args=(target_fp,), daemon=True)
        t.start()

    def _sendto_punch(self, data: bytes, state: PunchState) -> None:
        """Envia data al peer, directo o envuelto por relay segun state.via_relay.

        Si via_relay esta set: envuelve data como \\x02 | cid (16B) | data y
        lo envia al endpoint del relay. El relay forward a target. Mantiene
        forward secrecy porque data puede ser JSON efimero o ciphertext AEAD;
        el relay nunca ve las claves.

        Si via_relay es None: envia data directamente a target_endpoint.
        """
        if not self._udp_sock:
            return
        try:
            if state.via_relay is not None:
                cid_bytes = bytes.fromhex(state.circuit_id)
                wrapped = b"\x02" + cid_bytes + data
                if len(wrapped) <= MAX_UDP_SIZE:
                    self._udp_sock.sendto(wrapped, state.via_relay)
            else:
                self._udp_sock.sendto(data, state.target_endpoint)
        except OSError:
            pass

    def _punch_loop(self, target_fp: str) -> None:
        with self._lock:
            state = self._punch_states.get(target_fp)
        if not state or not self._udp_sock:
            return
        syn = json.dumps({
            "t": "punch_syn", "v": PROTOCOL_VERSION,
            "fp": self._network._fingerprint, "cid": state.circuit_id,
        }).encode("utf-8")
        deadline = time.time() + PUNCH_TIMEOUT
        while self._running and time.time() < deadline:
            with self._lock:
                s = self._punch_states.get(target_fp)
                if not s or s.phase != "punching":
                    return
            self._sendto_punch(syn, state)
            time.sleep(PUNCH_INTERVAL)
        with self._lock:
            s = self._punch_states.get(target_fp)
            if s and s.phase == "punching":
                s.phase = "failed"
                logger.info("punch: timeout con %s", target_fp)

    def _handle_punch_syn(
        self, msg: dict[str, Any], addr: tuple[str, int],
        via_relay: tuple[str, int] | None = None,
    ) -> None:
        peer_fp = msg.get("fp", "")
        cid = msg.get("cid", "")
        if not peer_fp or not cid or not self._udp_sock:
            return

        # Crear state reactivo si no existe (recepcion de punch iniciado por otro)
        with self._lock:
            state = self._punch_states.get(peer_fp)
            if state is None:
                # Buscar vk del peer para completar handshake
                peer_info = self._network._peers.get(peer_fp)
                peer_vk = peer_info.verify_key if peer_info else ""
                if not peer_vk:
                    return  # Sin vk no podemos completar el handshake
                eph_sk, eph_pk = generate_ephemeral_x25519()
                state = PunchState(
                    target_fp=peer_fp,
                    target_endpoint=addr,
                    target_vk=peer_vk,
                    circuit_id=cid,
                    phase="handshake",
                    my_eph_sk=eph_sk,
                    my_eph_pk=eph_pk,
                    via_relay=via_relay,
                )
                self._punch_states[peer_fp] = state
            elif state.phase == "punching":
                state.phase = "handshake"
                state.target_endpoint = addr
                if via_relay is not None and state.via_relay is None:
                    state.via_relay = via_relay

        # Enviar ack (con helper — decide direct vs relay wrap)
        ack = json.dumps({
            "t": "punch_ack", "v": PROTOCOL_VERSION,
            "fp": self._network._fingerprint, "cid": cid,
        }).encode("utf-8")
        self._sendto_punch(ack, state)
        # Enviar nuestra eph
        self._send_punch_eph(state, addr)

    def _handle_punch_ack(
        self, msg: dict[str, Any], addr: tuple[str, int],
        via_relay: tuple[str, int] | None = None,
    ) -> None:
        peer_fp = msg.get("fp", "")
        if not peer_fp:
            return
        with self._lock:
            state = self._punch_states.get(peer_fp)
            if state and state.phase == "punching":
                state.phase = "handshake"
                state.target_endpoint = addr
                if via_relay is not None and state.via_relay is None:
                    state.via_relay = via_relay
        if state:
            self._send_punch_eph(state, addr)

    def _send_punch_eph(self, state: PunchState, addr: tuple[str, int]) -> None:
        if not self._udp_sock:
            return
        msg = json.dumps({
            "t": "punch_eph", "v": PROTOCOL_VERSION,
            "fp": self._network._fingerprint,
            "vk": self._network._verify_key,
            "pk": state.my_eph_pk.hex(), "cid": state.circuit_id,
        }).encode("utf-8")
        self._sendto_punch(msg, state)

    def _handle_punch_eph(self, msg: dict[str, Any], addr: tuple[str, int]) -> None:
        peer_fp = msg.get("fp", "")
        peer_vk = msg.get("vk", "")
        peer_eph_pk_hex = msg.get("pk", "")
        if not peer_fp or not peer_eph_pk_hex:
            return
        with self._lock:
            state = self._punch_states.get(peer_fp)
            if not state or state.phase not in ("handshake", "punching"):
                return
            state.peer_eph_pk = bytes.fromhex(peer_eph_pk_hex)
            try:
                ecdh_ee = ecdh(state.my_eph_sk, state.peer_eph_pk)
                my_curve_sk = _static_curve25519_private(self._network._signing_key)
                peer_curve_pk = _peer_curve25519_public(peer_vk or state.target_vk)
                ecdh_se = ecdh(my_curve_sk, state.peer_eph_pk)
                ecdh_es = ecdh(state.my_eph_sk, peer_curve_pk)
                pair = sorted([ecdh_se, ecdh_es])
                state.session_key = derive_key(
                    ecdh_ee, salt=b"pongia-punch-4.0", context=pair[0] + pair[1],
                )
                state.phase = "established"
                logger.info("punch: conexion establecida con %s", peer_fp)
            except Exception as exc:
                logger.warning("punch: handshake fallido con %s: %s", peer_fp, exc)
                state.phase = "failed"
                return
        self._send_punch_records(peer_fp, addr)

    def _send_punch_records(self, peer_fp: str, addr: tuple[str, int]) -> None:
        if not self._udp_sock:
            return
        with self._lock:
            state = self._punch_states.get(peer_fp)
            if not state or state.phase != "established" or not state.session_key:
                return
        records_msg = self._network._build_records_message()
        try:
            ct = aead_encrypt(state.session_key, records_msg.encode("utf-8"))
            cid_bytes = bytes.fromhex(state.circuit_id)
            packet = b"\x01" + cid_bytes + ct
            if len(packet) <= MAX_UDP_SIZE:
                self._sendto_punch(packet, state)
                with self._lock:
                    state.last_activity = time.time()
        except Exception as exc:
            logger.debug("punch: error enviando records a %s: %s", peer_fp, exc)

    def _handle_punch_data(self, data: bytes, addr: tuple[str, int]) -> None:
        if len(data) < 33:
            return
        cid_hex = data[1:17].hex()
        with self._lock:
            state = None
            for s in self._punch_states.values():
                if s.circuit_id == cid_hex and s.phase == "established" and s.session_key:
                    state = s
                    s.last_activity = time.time()
                    break
        if not state or state.session_key is None:
            return
        try:
            plaintext = aead_decrypt(state.session_key, data[17:])
            msg = json.loads(plaintext.decode("utf-8"))
            if msg.get("type") == "pongia_records":
                self._network._handle_records_message(msg, addr[0])
        except Exception:
            pass

    # ================================================================
    # Relay
    # ================================================================

    def handle_relay_setup(self, msg: dict[str, Any]) -> bool:
        cid = msg.get("circuit_id", "")
        peer_a = msg.get("peer_a", {})
        peer_b = msg.get("peer_b", {})
        if not cid or not peer_a or not peer_b:
            return False
        a_ep = (peer_a.get("ep", {}).get("ip", ""), peer_a.get("ep", {}).get("port", 0))
        b_ep = (peer_b.get("ep", {}).get("ip", ""), peer_b.get("ep", {}).get("port", 0))
        if not a_ep[0] or not b_ep[0]:
            return False
        with self._lock:
            if cid in self._relay_circuits:
                logger.warning("punch: relay setup rechazado — circuit_id duplicado")
                return False
            if len(self._relay_circuits) >= MAX_RELAY_CIRCUITS:
                logger.warning("punch: relay setup rechazado — limite de circuitos")
                return False
            self._relay_circuits[cid] = RelayCircuit(
                circuit_id=cid, tier=PrivacyTier.RELAY,
                peer_a_endpoint=a_ep, peer_b_endpoint=b_ep,
            )
        return True

    def _dispatch_relay_or_endpoint(
        self, data: bytes, addr: tuple[str, int],
    ) -> None:
        """Recibe \\x02 | cid | inner. Forward si soy relay, unwrap si soy endpoint."""
        if len(data) < 17:
            return
        cid_hex = data[1:17].hex()

        # Si estoy configurado como relay para este cid, forward
        with self._lock:
            is_relay = cid_hex in self._relay_circuits

        if is_relay:
            self._handle_relay_forward(data, addr)
            return

        # Si no, ver si soy endpoint de este circuito
        with self._lock:
            matching_state = None
            for s in self._punch_states.values():
                if s.circuit_id == cid_hex:
                    matching_state = s
                    if s.via_relay is None:
                        s.via_relay = addr  # aprender quien es el relay
                    break

        if matching_state is None:
            return  # Ni relay ni endpoint — ignorar

        # Desempaquetar y dispatch como si hubiera llegado directo
        inner = data[17:]
        if not inner:
            return
        inner_first = inner[0:1]
        if inner_first == b"\x01":
            # Punch data cifrado — procesarlo con la state adecuada
            self._handle_punch_data(inner, addr)
        elif inner_first == b"{":
            try:
                inner_msg = json.loads(inner.decode("utf-8"))
                t = inner_msg.get("t", "")
                # Guardamos via_relay = addr para que las respuestas se envuelvan
                if t == "punch_syn":
                    self._handle_punch_syn(inner_msg, addr, via_relay=addr)
                elif t == "punch_ack":
                    self._handle_punch_ack(inner_msg, addr, via_relay=addr)
                elif t == "punch_eph":
                    self._handle_punch_eph(inner_msg, addr)
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

    def _handle_relay_forward(self, data: bytes, addr: tuple[str, int]) -> None:
        if len(data) < 17 or not self._udp_sock:
            return
        cid_hex = data[1:17].hex()
        with self._lock:
            circuit = self._relay_circuits.get(cid_hex)
            if not circuit:
                return
            circuit.packets_forwarded += 1
            circuit.last_activity = time.time()
            if circuit.packets_forwarded > MAX_RELAY_PACKETS_PER_MIN:
                return
        if addr[0] == circuit.peer_a_endpoint[0]:
            dest = circuit.peer_b_endpoint
        elif addr[0] == circuit.peer_b_endpoint[0]:
            dest = circuit.peer_a_endpoint
        else:
            return
        try:
            self._udp_sock.sendto(data, dest)
        except OSError:
            pass

    # ================================================================
    # Onion
    # ================================================================

    # ================================================================
    # Onion handshake + data (Option B: full forward secrecy)
    # ================================================================

    def _sign_onion_payload(self, payload: bytes) -> str:
        """Firma Ed25519 un payload para autenticar mensajes onion."""
        from nacl.signing import SigningKey
        sk = SigningKey(bytes.fromhex(self._network._signing_key))
        sig_hex: str = sk.sign(payload).signature.hex()
        return sig_hex

    @staticmethod
    def _verify_onion_signature(
        payload: bytes, sig_hex: str, vk_hex: str,
    ) -> bool:
        """Verifica firma Ed25519 sobre payload."""
        try:
            from nacl.exceptions import BadSignatureError
            from nacl.signing import VerifyKey
            vk = VerifyKey(bytes.fromhex(vk_hex))
            vk.verify(payload, bytes.fromhex(sig_hex))
            return True
        except (BadSignatureError, TypeError, ValueError):
            return False

    def initiate_onion_handshake(
        self,
        target_fp: str,
        target_vk: str,
        target_ep: dict[str, Any],
        circuit: list[dict[str, Any]],
    ) -> bool:
        """Inicia un handshake onion enviando hs1 al target via circuit.

        Genera eph_sk_A efimero y nonce, guarda handshake pendiente,
        construye mensaje firmado y lo envia via wrap_onion_message.
        """
        if not self._udp_sock:
            return False

        eph_sk, eph_pk = generate_ephemeral_x25519()
        nonce = secrets.token_hex(16)

        # Payload canonico que se firma: type || eph_pk || nonce || target_vk
        to_sign = (
            b"onion_hs1|"
            + eph_pk.hex().encode()
            + b"|" + nonce.encode()
            + b"|" + target_vk.encode()
        )
        sig = self._sign_onion_payload(to_sign)

        hs1 = json.dumps({
            "t": "onion_hs1",
            "v": PROTOCOL_VERSION,
            "sender_fp": self._network._fingerprint,
            "sender_vk": self._network._verify_key,
            "eph_pk": eph_pk.hex(),
            "nonce": nonce,
            "sig": sig,
        }).encode("utf-8")

        # Envolver en onion y enviar al primer hop
        result = self.wrap_onion_message(hs1, circuit, target_ep)
        if result is None:
            return False
        onion_bytes, first_hop = result

        # Guardar handshake pendiente para cuando llegue hs2
        with self._lock:
            self._onion_pending[nonce] = OnionHandshake(
                peer_fp=target_fp,
                peer_vk=target_vk,
                my_eph_sk=eph_sk,
                my_eph_pk=eph_pk,
                nonce=nonce,
                circuit=list(circuit),
            )

        try:
            self._udp_sock.sendto(onion_bytes, first_hop)
            logger.info(
                "onion: hs1 enviado a %s via R1=%s (nonce=%s)",
                target_fp[:8], first_hop[0], nonce[:8],
            )
            return True
        except OSError:
            with self._lock:
                self._onion_pending.pop(nonce, None)
            return False

    def wrap_onion_message(
        self, payload: bytes, circuit: list[dict[str, Any]], target_ep: dict[str, Any],
    ) -> tuple[bytes, tuple[str, int]] | None:
        """Envuelve payload en N capas onion binarias.

        Formato por capa (compacto, sin hex/JSON overhead):
          \\x03 [1B marker]
          eph_pk [32B]
          ct_len [4B BE]
          ct [ct_len B]  (AEAD: nonce 24B + ciphertext + tag 16B)

        Plaintext interno de ct:
          next_len [2B BE]
          next_str (UTF-8, ej "127.0.0.1:54321") [next_len B]
          payload [resto]
        """
        if not circuit:
            return None
        current = payload
        all_hops = list(circuit) + [{"ep": target_ep}]
        for i in range(len(circuit) - 1, -1, -1):
            hop = circuit[i]
            hop_vk = hop.get("vk", "")
            if not hop_vk:
                return None
            next_hop = all_hops[i + 1]
            next_ep = next_hop.get("ep", {})
            next_str = f"{next_ep.get('ip','')}:{next_ep.get('port',0)}".encode("utf-8")
            eph_sk, eph_pk = generate_ephemeral_x25519()
            try:
                hop_key = derive_key(
                    ecdh(eph_sk, _peer_curve25519_public(hop_vk)),
                    salt=b"pongia-onion-4.0",
                )
            except Exception:
                return None
            inner = struct.pack("!H", len(next_str)) + next_str + current
            ct = aead_encrypt(hop_key, inner)
            current = (
                b"\x03"
                + eph_pk
                + struct.pack("!I", len(ct))
                + ct
            )
        first_hop_ep = circuit[0].get("ep", {})
        return current, (first_hop_ep.get("ip", ""), first_hop_ep.get("port", 0))

    def _handle_onion_hs1(
        self, msg: dict[str, Any], addr: tuple[str, int],
    ) -> None:
        """Recibe hs1 (llegado tras despelar onion). Verifica firma, genera
        eph propia, cachea sesion y responde con hs2 via su propio circuito.
        """
        sender_fp = msg.get("sender_fp", "")
        sender_vk = msg.get("sender_vk", "")
        peer_eph_pk_hex = msg.get("eph_pk", "")
        nonce = msg.get("nonce", "")
        sig = msg.get("sig", "")

        if not all([sender_fp, sender_vk, peer_eph_pk_hex, nonce, sig]):
            return
        if sender_fp == self._network._fingerprint:
            return

        # Verificar consistencia fp == sha256(vk)[:16]
        from pong.save_manager import _compute_fingerprint
        if _compute_fingerprint(sender_vk) != sender_fp:
            return

        # Verificar firma: sender firmo "onion_hs1|eph_pk|nonce|my_vk"
        to_verify = (
            b"onion_hs1|"
            + peer_eph_pk_hex.encode()
            + b"|" + nonce.encode()
            + b"|" + self._network._verify_key.encode()
        )
        if not self._verify_onion_signature(to_verify, sig, sender_vk):
            logger.warning("onion: firma hs1 invalida de %s", sender_fp[:8])
            return

        # Generar nuestra efimera, derivar session_key
        my_eph_sk, my_eph_pk = generate_ephemeral_x25519()
        peer_eph_pk = bytes.fromhex(peer_eph_pk_hex)
        session_key = derive_key(
            ecdh(my_eph_sk, peer_eph_pk),
            salt=b"pongia-onion-session-4.0",
        )

        # Cachear sesion
        with self._lock:
            self._onion_sessions[sender_fp] = OnionSession(
                peer_fp=sender_fp,
                peer_vk=sender_vk,
                session_key=session_key,
            )

        logger.info(
            "onion: hs1 validado de %s, session key derivada", sender_fp[:8],
        )

        # Pedir al network que inicie hs2 de vuelta (usa su propio circuito)
        try:
            self._network._send_onion_hs2_response(
                sender_fp=sender_fp,
                sender_vk=sender_vk,
                my_eph_pk=my_eph_pk,
                peer_eph_pk=peer_eph_pk,
                responds_to=nonce,
            )
        except Exception as exc:
            logger.warning("onion: no se pudo enviar hs2: %s", exc)

    def _handle_onion_hs2(
        self, msg: dict[str, Any], addr: tuple[str, int],
    ) -> None:
        """Recibe hs2 tras haber enviado hs1. Deriva session_key y completa."""
        sender_fp = msg.get("sender_fp", "")
        sender_vk = msg.get("sender_vk", "")
        peer_eph_pk_hex = msg.get("eph_pk", "")
        responds_to = msg.get("responds_to", "")
        sig = msg.get("sig", "")

        if not all([sender_fp, sender_vk, peer_eph_pk_hex, responds_to, sig]):
            return

        with self._lock:
            pending = self._onion_pending.get(responds_to)
        if pending is None:
            logger.debug("onion: hs2 con nonce desconocido")
            return

        if pending.peer_fp != sender_fp or pending.peer_vk != sender_vk:
            logger.warning(
                "onion: hs2 sender no coincide con pending (%s vs %s)",
                sender_fp[:8], pending.peer_fp[:8],
            )
            return

        # Verificar firma: peer firmo "onion_hs2|peer_eph_pk|responds_to|our_eph_pk"
        to_verify = (
            b"onion_hs2|"
            + peer_eph_pk_hex.encode()
            + b"|" + responds_to.encode()
            + b"|" + pending.my_eph_pk.hex().encode()
        )
        if not self._verify_onion_signature(to_verify, sig, sender_vk):
            logger.warning("onion: firma hs2 invalida de %s", sender_fp[:8])
            return

        peer_eph_pk = bytes.fromhex(peer_eph_pk_hex)
        session_key = derive_key(
            ecdh(pending.my_eph_sk, peer_eph_pk),
            salt=b"pongia-onion-session-4.0",
        )

        with self._lock:
            self._onion_sessions[sender_fp] = OnionSession(
                peer_fp=sender_fp,
                peer_vk=sender_vk,
                session_key=session_key,
            )
            self._onion_pending.pop(responds_to, None)

        logger.info(
            "onion: hs2 validado de %s — session establecida", sender_fp[:8],
        )

        # Ahora enviamos nuestros records cifrados via onion
        try:
            self._network._send_onion_data_to(sender_fp, pending.circuit)
        except Exception as exc:
            logger.warning("onion: no se pudo enviar data: %s", exc)

    def _handle_onion_data(
        self, msg: dict[str, Any], addr: tuple[str, int],
    ) -> None:
        """Recibe records cifrados via onion. Descifra con session_key cacheada."""
        sender_fp = msg.get("sender_fp", "")
        records_ct_hex = msg.get("records_ct", "")
        sig = msg.get("sig", "")

        if not all([sender_fp, records_ct_hex, sig]):
            return

        with self._lock:
            session = self._onion_sessions.get(sender_fp)
        if session is None:
            logger.debug("onion: data sin sesion establecida para %s", sender_fp[:8])
            return

        # Verificar firma sobre el ciphertext (solo el sender puede producirla)
        to_verify = b"onion_data|" + records_ct_hex.encode()
        if not self._verify_onion_signature(to_verify, sig, session.peer_vk):
            logger.warning("onion: firma data invalida de %s", sender_fp[:8])
            return

        try:
            records_ct = bytes.fromhex(records_ct_hex)
            plaintext = aead_decrypt(session.session_key, records_ct)
            records_msg = json.loads(plaintext.decode("utf-8"))
            if records_msg.get("type") == "pongia_records":
                self._network._handle_records_message(records_msg, addr[0])
                with self._lock:
                    session.last_activity = time.time()
                logger.info("onion: records recibidos de %s", sender_fp[:8])
        except Exception as exc:
            logger.warning("onion: error descifrando data: %s", exc)

    def _handle_onion_layer(self, data: bytes, addr: tuple[str, int]) -> None:
        """Despela una capa onion (formato binario) y reenvia al siguiente hop."""
        if not self._udp_sock:
            return
        if len(data) < 1 + 32 + 4:
            return
        try:
            # [0] marker \x03
            # [1..33] eph_pk (32 bytes)
            # [33..37] ct_len (4B BE)
            # [37..37+ct_len] ct
            eph_pk = data[1:33]
            (ct_len,) = struct.unpack("!I", data[33:37])
            if ct_len > MAX_UDP_SIZE or 37 + ct_len > len(data):
                return
            ct = data[37:37 + ct_len]
            my_curve_sk = _static_curve25519_private(self._network._signing_key)
            hop_key = derive_key(ecdh(my_curve_sk, eph_pk), salt=b"pongia-onion-4.0")
            plaintext = aead_decrypt(hop_key, ct)
            # Parse inner: [next_len 2B BE][next_str][payload]
            if len(plaintext) < 2:
                return
            (next_len,) = struct.unpack("!H", plaintext[0:2])
            if 2 + next_len > len(plaintext):
                return
            next_str = plaintext[2:2 + next_len].decode("utf-8")
            payload = plaintext[2 + next_len:]
            if ":" not in next_str:
                return
            next_ip, next_port_s = next_str.rsplit(":", 1)
            next_port = int(next_port_s)
            if not next_ip or not (1 <= next_port <= 65535):
                return
            # Bloquear reenvio a redes privadas/loopback (anti-amplificacion)
            if not self._allow_private_relay and _is_private_ip(next_ip):
                logger.debug("onion: bloqueado reenvio a IP privada %s", next_ip)
                return
            self._udp_sock.sendto(payload, (next_ip, next_port))
        except Exception as exc:
            logger.debug("onion: error peel: %s", exc)

    # ================================================================
    # UDP listener
    # ================================================================

    def _udp_listener_loop(self) -> None:
        sock = self._udp_sock
        if not sock:
            return
        while self._running:
            try:
                data, addr = sock.recvfrom(MAX_UDP_SIZE)
            except socket.timeout:
                continue
            except OSError:
                continue
            if not data:
                continue
            first = data[0:1]
            if first == b"\x00":
                continue  # keepalive
            elif first == b"\x01":
                self._handle_punch_data(data, addr)
            elif first == b"\x02":
                # Puede ser: (a) yo soy relay -> forward, o
                # (b) yo soy endpoint de este circuito -> unwrap + dispatch
                self._dispatch_relay_or_endpoint(data, addr)
            elif first == b"\x03":
                # Capa onion binaria
                self._handle_onion_layer(data, addr)
            elif first == b"{":
                try:
                    msg = json.loads(data.decode("utf-8"))
                    t = msg.get("t", "")
                    if t == "stun_req":
                        self.handle_stun_request(data, addr)
                    elif t == "punch_syn":
                        self._handle_punch_syn(msg, addr)
                    elif t == "punch_ack":
                        self._handle_punch_ack(msg, addr)
                    elif t == "punch_eph":
                        self._handle_punch_eph(msg, addr)
                    elif t == "onion_hs1":
                        self._handle_onion_hs1(msg, addr)
                    elif t == "onion_hs2":
                        self._handle_onion_hs2(msg, addr)
                    elif t == "onion_data":
                        self._handle_onion_data(msg, addr)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass

    # ================================================================
    # Gossip integration + keepalive
    # ================================================================

    def gossip_via_punches(self) -> None:
        """Envia records a todos los peers con punch establecido."""
        if not self._udp_sock:
            return
        with self._lock:
            established = [
                (fp, s.target_endpoint)
                for fp, s in self._punch_states.items()
                if s.phase == "established" and s.session_key
            ]
        for fp, endpoint in established:
            self._send_punch_records(fp, endpoint)

    def _send_keepalive(self) -> None:
        """Ping a punches idle para mantener NAT mapping."""
        if not self._udp_sock:
            return
        now = time.time()
        with self._lock:
            idle = [
                s for s in self._punch_states.values()
                if s.phase == "established" and s.session_key
                and now - s.last_activity > KEEPALIVE_INTERVAL
            ]
        for state in idle:
            self._sendto_punch(b"\x00", state)
            with self._lock:
                state.last_activity = now

    def attempt_pending_punches(self) -> None:
        """Llamado desde gossip loop."""
        if not self._udp_sock:
            return
        self.gossip_via_punches()
        self._send_keepalive()
        now = time.time()
        with self._lock:
            expired = [
                fp for fp, s in self._punch_states.items()
                if s.phase == "failed" or now - s.started > PUNCH_TIMEOUT * 2
            ]
            for fp in expired:
                del self._punch_states[fp]
            expired_circuits = [
                cid for cid, c in self._relay_circuits.items()
                if now - c.last_activity > RELAY_CIRCUIT_TTL
            ]
            for cid in expired_circuits:
                del self._relay_circuits[cid]
            # Podar onion handshakes expirados (hs pendientes + sesiones)
            expired_hs = [
                nonce for nonce, hs in self._onion_pending.items()
                if now - hs.started > ONION_HS_TIMEOUT
            ]
            for nonce in expired_hs:
                del self._onion_pending[nonce]
            expired_sess = [
                fp for fp, sess in self._onion_sessions.items()
                if now - sess.created > ONION_SESSION_TTL
            ]
            for fp in expired_sess:
                del self._onion_sessions[fp]

    def get_punch_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "reflexive_endpoint": self._reflexive.to_dict() if self._reflexive.is_fresh() else None,
                "privacy_tier": self.current_tier.value,
                "active_punches": sum(
                    1 for s in self._punch_states.values()
                    if s.phase in ("punching", "handshake", "established")
                ),
                "established_punches": sum(
                    1 for s in self._punch_states.values()
                    if s.phase == "established"
                ),
                "relay_circuits": len(self._relay_circuits),
                "relay_volunteer": self._relay_volunteer,
            }
