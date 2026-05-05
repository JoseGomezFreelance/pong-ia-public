"""Tests de integracion para pong/punch.py — NAT traversal (DIRECT/RELAY/ONION)."""

from __future__ import annotations

import json
import socket
import struct
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from nacl.signing import SigningKey

from pong.crypto import (
    aead_decrypt,
    aead_encrypt,
    derive_key,
    ecdh,
    generate_ephemeral_x25519,
)
from pong.p2p import PeerInfo, PeerNetwork
from pong.punch import (
    MAX_PUNCH_REQ_PER_MIN,
    PROTOCOL_VERSION,
    OnionHandshake,
    OnionSession,
    PrivacyTier,
    PunchManager,
    PunchState,
    ReflexiveEndpoint,
    RelayCircuit,
    current_tier,
    subnet_24,
    TIER_ONION,
    TIER_RELAY,
    _peer_curve25519_public,
    _static_curve25519_private,
)
from pong.save_manager import _compute_fingerprint


# ================================================================
# Helpers
# ================================================================

def _make_profile(alias: str) -> dict[str, str]:
    sk = SigningKey.generate()
    vk = sk.verify_key.encode().hex()
    return {
        "alias": alias,
        "fingerprint": _compute_fingerprint(vk),
        "signing_key": sk.encode().hex(),
        "verify_key": vk,
    }


def _bootstrap_punch_manager(net: PeerNetwork) -> PunchManager:
    """Monta un PunchManager con socket UDP en puerto aleatorio (localhost)."""
    pm = PunchManager(net)
    pm._allow_private_relay = True  # tests usan 127.0.0.1
    pm._running = True
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(1.0)
    pm._udp_sock = sock
    t = threading.Thread(target=pm._udp_listener_loop, daemon=True)
    t.start()
    return pm


def _pm_sock(pm: PunchManager) -> socket.socket:
    """Helper typed para acceder al socket sin errores de mypy."""
    assert pm._udp_sock is not None
    return pm._udp_sock


def _pm_port(pm: PunchManager) -> int:
    """Helper typed para obtener el puerto del socket."""
    return int(_pm_sock(pm).getsockname()[1])


def _make_net(alias: str, tmp: Path) -> PeerNetwork:
    """Crea un PeerNetwork sin cargar peers iniciales."""
    with patch("pong.p2p.PeerNetwork._load_initial_peers"):
        return PeerNetwork(
            profile=_make_profile(alias),
            cache_path=tmp / f"{alias}.json",
        )


# ================================================================
# Unit tests — logica pura
# ================================================================

class TestPrivacyTier(unittest.TestCase):
    """Seleccion de tier segun cantidad de peers."""

    def test_tier_direct_when_few(self) -> None:
        self.assertEqual(current_tier(0), PrivacyTier.DIRECT)
        self.assertEqual(current_tier(TIER_RELAY - 1), PrivacyTier.DIRECT)

    def test_tier_relay_at_threshold(self) -> None:
        self.assertEqual(current_tier(TIER_RELAY), PrivacyTier.RELAY)
        self.assertEqual(current_tier(TIER_ONION - 1), PrivacyTier.RELAY)

    def test_tier_onion_at_threshold(self) -> None:
        self.assertEqual(current_tier(TIER_ONION), PrivacyTier.ONION)
        self.assertEqual(current_tier(100), PrivacyTier.ONION)


class TestSubnet24(unittest.TestCase):
    """Extraccion de prefijo /24 para evitar colocar relays en misma subred."""

    def test_normal_ipv4(self) -> None:
        self.assertEqual(subnet_24("192.168.1.50"), "192.168.1")

    def test_hostname_not_ip(self) -> None:
        self.assertEqual(subnet_24("example.com"), "example.com")


class TestReflexiveEndpoint(unittest.TestCase):
    """ReflexiveEndpoint serializable y con expiracion."""

    def test_fresh_within_ttl(self) -> None:
        ep = ReflexiveEndpoint(ip="1.2.3.4", port=19849, timestamp=time.time())
        self.assertTrue(ep.is_fresh())

    def test_stale_after_ttl(self) -> None:
        ep = ReflexiveEndpoint(ip="1.2.3.4", port=19849, timestamp=time.time() - 1000)
        self.assertFalse(ep.is_fresh())

    def test_empty_ip_not_fresh(self) -> None:
        self.assertFalse(ReflexiveEndpoint().is_fresh())

    def test_roundtrip_dict(self) -> None:
        ep = ReflexiveEndpoint(ip="1.2.3.4", port=19849, timestamp=100.0)
        ep2 = ReflexiveEndpoint.from_dict(ep.to_dict())
        self.assertEqual((ep2.ip, ep2.port), ("1.2.3.4", 19849))


class TestRateLimit(unittest.TestCase):
    """Rate limit de solicitudes de punch por peer."""

    def test_below_limit_allowed(self) -> None:
        net = MagicMock()
        pm = PunchManager(net)
        for _ in range(MAX_PUNCH_REQ_PER_MIN):
            self.assertTrue(pm._check_punch_rate("peer1"))

    def test_above_limit_blocked(self) -> None:
        net = MagicMock()
        pm = PunchManager(net)
        for _ in range(MAX_PUNCH_REQ_PER_MIN):
            pm._check_punch_rate("peer1")
        self.assertFalse(pm._check_punch_rate("peer1"))

    def test_different_peers_independent(self) -> None:
        net = MagicMock()
        pm = PunchManager(net)
        for _ in range(MAX_PUNCH_REQ_PER_MIN):
            pm._check_punch_rate("peer1")
        # otro peer tiene su propio contador
        self.assertTrue(pm._check_punch_rate("peer2"))


class TestConsent(unittest.TestCase):
    """Consent: solo peers que intercambiaron records."""

    def test_mutual_exchange_allowed(self) -> None:
        net = MagicMock()
        net._exchanged_with = {"alice", "bob"}
        pm = PunchManager(net)
        self.assertTrue(pm._check_consent("alice", "bob"))

    def test_one_side_missing(self) -> None:
        net = MagicMock()
        net._exchanged_with = {"alice"}
        pm = PunchManager(net)
        self.assertFalse(pm._check_consent("alice", "bob"))
        self.assertFalse(pm._check_consent("bob", "alice"))


# ================================================================
# Integration tests — requieren sockets UDP
# ================================================================

class TestSTUNRoundtrip(unittest.TestCase):
    """STUN request/response entre dos PunchManagers reales."""

    def test_stun_returns_sender_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            server_net = _make_net("Srv", tmp_path)
            server_pm = _bootstrap_punch_manager(server_net)
            server_port = _pm_port(server_pm)

            # Cliente suelto (no PunchManager) envia STUN req
            client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client.bind(("127.0.0.1", 0))
            client.settimeout(2.0)
            client_port = client.getsockname()[1]

            req = json.dumps({
                "t": "stun_req", "v": PROTOCOL_VERSION, "fp": "client_fp",
            }).encode()
            client.sendto(req, ("127.0.0.1", server_port))

            data, _ = client.recvfrom(65536)
            resp = json.loads(data.decode())
            self.assertEqual(resp["t"], "stun_resp")
            self.assertEqual(resp["ip"], "127.0.0.1")
            self.assertEqual(resp["port"], client_port)

            client.close()
            server_pm._running = False
            _pm_sock(server_pm).close()


class TestDirectPunch(unittest.TestCase):
    """DIRECT tier: dos PunchManagers hacen handshake X25519 directo."""

    def test_two_peers_establish_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            alice_net = _make_net("Alice", tmp_path)
            bob_net = _make_net("Bob", tmp_path)
            alice_pm = _bootstrap_punch_manager(alice_net)
            bob_pm = _bootstrap_punch_manager(bob_net)
            alice_net._punch_manager = alice_pm
            bob_net._punch_manager = bob_pm

            # Ambos se conocen (necesario para el handshake reactivo)
            alice_net._peers[bob_net._fingerprint] = PeerInfo(
                fingerprint=bob_net._fingerprint, alias="Bob",
                ip="127.0.0.1", data_port=0, verify_key=bob_net._verify_key,
            )
            bob_net._peers[alice_net._fingerprint] = PeerInfo(
                fingerprint=alice_net._fingerprint, alias="Alice",
                ip="127.0.0.1", data_port=0, verify_key=alice_net._verify_key,
            )

            bob_port = _pm_port(bob_pm)
            alice_pm.initiate_punch(
                target_fp=bob_net._fingerprint,
                target_ep={"ip": "127.0.0.1", "port": bob_port},
                target_vk=bob_net._verify_key,
                circuit_id="00" * 16,
            )

            # Esperar a establecer
            for _ in range(20):
                time.sleep(0.2)
                a = alice_pm._punch_states.get(bob_net._fingerprint)
                b = bob_pm._punch_states.get(alice_net._fingerprint)
                if a and b and a.phase == "established" and b.phase == "established":
                    break

            a = alice_pm._punch_states.get(bob_net._fingerprint)
            b = bob_pm._punch_states.get(alice_net._fingerprint)
            self.assertIsNotNone(a)
            self.assertIsNotNone(b)
            assert a is not None and b is not None
            self.assertEqual(a.phase, "established")
            self.assertEqual(b.phase, "established")
            # Claves de sesion identicas (handshake triple ECDH simetrico)
            self.assertEqual(a.session_key, b.session_key)

            alice_pm._running = False
            bob_pm._running = False
            _pm_sock(alice_pm).close()
            _pm_sock(bob_pm).close()


class TestRelayForwarding(unittest.TestCase):
    """RELAY tier: A->R->B con full forward secrecy."""

    def test_handshake_through_relay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            alice_net = _make_net("Alice", tmp_path)
            bob_net = _make_net("Bob", tmp_path)
            relay_net = _make_net("Relay", tmp_path)

            alice_pm = _bootstrap_punch_manager(alice_net)
            bob_pm = _bootstrap_punch_manager(bob_net)
            relay_pm = _bootstrap_punch_manager(relay_net)
            alice_net._punch_manager = alice_pm
            bob_net._punch_manager = bob_pm
            relay_net._punch_manager = relay_pm

            alice_net._peers[bob_net._fingerprint] = PeerInfo(
                fingerprint=bob_net._fingerprint, alias="Bob",
                ip="127.0.0.1", data_port=0, verify_key=bob_net._verify_key,
            )
            bob_net._peers[alice_net._fingerprint] = PeerInfo(
                fingerprint=alice_net._fingerprint, alias="Alice",
                ip="127.0.0.1", data_port=0, verify_key=alice_net._verify_key,
            )

            alice_port = _pm_port(alice_pm)
            bob_port = _pm_port(bob_pm)
            relay_port = _pm_port(relay_pm)

            cid = "cafe" * 8  # 32 chars = 16 bytes hex
            # Configurar relay
            relay_pm.handle_relay_setup({
                "circuit_id": cid,
                "peer_a": {"fp": alice_net._fingerprint,
                           "ep": {"ip": "127.0.0.1", "port": alice_port}},
                "peer_b": {"fp": bob_net._fingerprint,
                           "ep": {"ip": "127.0.0.1", "port": bob_port}},
            })

            # Alice inicia punch hacia Bob via relay
            alice_pm.initiate_punch(
                target_fp=bob_net._fingerprint,
                target_ep={"ip": "127.0.0.1", "port": bob_port},
                target_vk=bob_net._verify_key,
                circuit_id=cid,
            )
            with alice_pm._lock:
                st = alice_pm._punch_states[bob_net._fingerprint]
                st.via_relay = ("127.0.0.1", relay_port)

            for _ in range(20):
                time.sleep(0.2)
                a = alice_pm._punch_states.get(bob_net._fingerprint)
                b = bob_pm._punch_states.get(alice_net._fingerprint)
                if a and b and a.phase == "established" and b.phase == "established":
                    break

            a = alice_pm._punch_states.get(bob_net._fingerprint)
            b = bob_pm._punch_states.get(alice_net._fingerprint)
            assert a is not None and b is not None
            self.assertEqual(a.phase, "established")
            self.assertEqual(b.phase, "established")
            self.assertEqual(a.session_key, b.session_key)
            # El relay forward paquetes pero no ve contenido cifrado
            self.assertGreater(relay_pm._relay_circuits[cid].packets_forwarded, 0)

            for pm in (alice_pm, bob_pm, relay_pm):
                pm._running = False
                _pm_sock(pm).close()


class TestOnionBinaryFormat(unittest.TestCase):
    """Wrap/unwrap onion en formato binario compacto (\x03 | eph | ct_len | ct)."""

    def test_wrap_single_hop_roundtrip(self) -> None:
        """Una capa: envolver + despelar produce el payload original."""
        # Relay single-hop
        relay_sk = SigningKey.generate()
        relay_vk = relay_sk.verify_key.encode().hex()
        relay_curve_sk = _static_curve25519_private(relay_sk.encode().hex())

        # Mock PunchManager para usar wrap
        net = MagicMock()
        net._signing_key = SigningKey.generate().encode().hex()
        pm = PunchManager(net)

        payload = b"hello world"
        circuit = [{"fp": "r1", "ep": {"ip": "10.0.0.1", "port": 50000}, "vk": relay_vk}]
        target_ep = {"ip": "10.0.0.99", "port": 60000}

        result = pm.wrap_onion_message(payload, circuit, target_ep)
        self.assertIsNotNone(result)
        assert result is not None
        wrapped, first_hop = result
        self.assertEqual(first_hop, ("10.0.0.1", 50000))
        # Formato: \x03 | eph_pk(32B) | ct_len(4B) | ct
        self.assertEqual(wrapped[0:1], b"\x03")
        (ct_len,) = struct.unpack("!I", wrapped[33:37])
        self.assertEqual(len(wrapped), 37 + ct_len)

        # Relay despela
        eph_pk = wrapped[1:33]
        ct = wrapped[37:37 + ct_len]
        hop_key = derive_key(ecdh(relay_curve_sk, eph_pk), salt=b"pongia-onion-4.0")
        plaintext = aead_decrypt(hop_key, ct)
        (next_len,) = struct.unpack("!H", plaintext[0:2])
        next_str = plaintext[2:2 + next_len].decode()
        inner_payload = plaintext[2 + next_len:]
        self.assertEqual(next_str, "10.0.0.99:60000")
        self.assertEqual(inner_payload, payload)

    def test_wrap_three_hops_fits_udp(self) -> None:
        """3 hops no deben superar el limite UDP de macOS (~9KB)."""
        relay_vks = [SigningKey.generate().verify_key.encode().hex() for _ in range(3)]
        net = MagicMock()
        net._signing_key = SigningKey.generate().encode().hex()
        pm = PunchManager(net)

        # Payload realista (hs1 es ~400 bytes)
        payload = b"x" * 400
        circuit = [
            {"fp": f"r{i}", "ep": {"ip": f"10.0.{i}.1", "port": 50000 + i},
             "vk": relay_vks[i]}
            for i in range(3)
        ]
        target_ep = {"ip": "10.0.99.1", "port": 60000}
        result = pm.wrap_onion_message(payload, circuit, target_ep)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertLess(len(result[0]), 9000)  # macOS UDP limit

    def test_wrap_empty_circuit_returns_none(self) -> None:
        net = MagicMock()
        pm = PunchManager(net)
        self.assertIsNone(pm.wrap_onion_message(b"x", [], {"ip": "a", "port": 1}))


class TestOnionFullHandshake(unittest.TestCase):
    """ONION full FS: Alice -> 3 relays -> Bob + respuesta + data."""

    def test_end_to_end_onion_handshake(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            alice_net = _make_net("Alice", tmp_path)
            bob_net = _make_net("Bob", tmp_path)
            r_nets = [_make_net(f"R{i}", tmp_path) for i in range(3)]

            alice_pm = _bootstrap_punch_manager(alice_net)
            bob_pm = _bootstrap_punch_manager(bob_net)
            r_pms = [_bootstrap_punch_manager(n) for n in r_nets]
            alice_net._punch_manager = alice_pm
            bob_net._punch_manager = bob_pm
            for i, n in enumerate(r_nets):
                n._punch_manager = r_pms[i]

            alice_net._peers[bob_net._fingerprint] = PeerInfo(
                fingerprint=bob_net._fingerprint, alias="Bob",
                ip="127.0.0.1", data_port=0, verify_key=bob_net._verify_key,
            )
            bob_net._peers[alice_net._fingerprint] = PeerInfo(
                fingerprint=alice_net._fingerprint, alias="Alice",
                ip="127.0.0.1", data_port=0, verify_key=alice_net._verify_key,
            )

            assert alice_pm._udp_sock is not None
            assert bob_pm._udp_sock is not None
            ports = {
                "Alice": alice_pm._udp_sock.getsockname()[1],
                "Bob": bob_pm._udp_sock.getsockname()[1],
            }
            for i, pm in enumerate(r_pms):
                assert pm._udp_sock is not None
                ports[f"R{i}"] = pm._udp_sock.getsockname()[1]

            circuit = [
                {"fp": r_nets[i]._fingerprint,
                 "ep": {"ip": "127.0.0.1", "port": ports[f"R{i}"]},
                 "vk": r_nets[i]._verify_key}
                for i in range(3)
            ]
            target_ep = {"ip": "127.0.0.1", "port": ports["Bob"]}

            # Bob: mock hs2 response para usar circuito inverso
            def mock_hs2(
                sender_fp: str, sender_vk: str,
                my_eph_pk: bytes, peer_eph_pk: bytes, responds_to: str,
            ) -> None:
                reverse = list(reversed(circuit))
                target_alice = {"ip": "127.0.0.1", "port": ports["Alice"]}
                sk = SigningKey(bytes.fromhex(bob_net._signing_key))
                to_sign = (
                    b"onion_hs2|" + my_eph_pk.hex().encode()
                    + b"|" + responds_to.encode()
                    + b"|" + peer_eph_pk.hex().encode()
                )
                sig = sk.sign(to_sign).signature.hex()
                hs2 = json.dumps({
                    "t": "onion_hs2", "v": PROTOCOL_VERSION,
                    "sender_fp": bob_net._fingerprint,
                    "sender_vk": bob_net._verify_key,
                    "eph_pk": my_eph_pk.hex(),
                    "responds_to": responds_to,
                    "sig": sig,
                }).encode()
                wrapped = bob_pm.wrap_onion_message(hs2, reverse, target_alice)
                if wrapped and bob_pm._udp_sock is not None:
                    bob_pm._udp_sock.sendto(wrapped[0], wrapped[1])

            bob_net._send_onion_hs2_response = mock_hs2  # type: ignore[method-assign]

            # Alice: mock data send (simplificado, envia algo y ya)
            def mock_data(target_fp: str, circ: list[dict[str, Any]]) -> None:
                session = alice_pm._onion_sessions.get(target_fp)
                if not session:
                    return
                alice_net._local_entries = []
                alice_net._remote_entries = []
                records_json = alice_net._build_records_message()
                ct = aead_encrypt(session.session_key, records_json.encode())
                sk = SigningKey(bytes.fromhex(alice_net._signing_key))
                to_sign = b"onion_data|" + ct.hex().encode()
                sig = sk.sign(to_sign).signature.hex()
                data = json.dumps({
                    "t": "onion_data", "v": PROTOCOL_VERSION,
                    "sender_fp": alice_net._fingerprint,
                    "records_ct": ct.hex(),
                    "sig": sig,
                }).encode()
                wrapped = alice_pm.wrap_onion_message(data, circuit, target_ep)
                if wrapped and alice_pm._udp_sock is not None:
                    alice_pm._udp_sock.sendto(wrapped[0], wrapped[1])

            alice_net._send_onion_data_to = mock_data  # type: ignore[method-assign,assignment]

            ok = alice_pm.initiate_onion_handshake(
                target_fp=bob_net._fingerprint,
                target_vk=bob_net._verify_key,
                target_ep=target_ep,
                circuit=circuit,
            )
            self.assertTrue(ok)

            # Esperar a que se complete
            for _ in range(30):
                time.sleep(0.2)
                a = alice_pm._onion_sessions.get(bob_net._fingerprint)
                b = bob_pm._onion_sessions.get(alice_net._fingerprint)
                if a and b:
                    break

            a = alice_pm._onion_sessions.get(bob_net._fingerprint)
            b = bob_pm._onion_sessions.get(alice_net._fingerprint)
            self.assertIsNotNone(a, "Alice no tiene sesion onion")
            self.assertIsNotNone(b, "Bob no tiene sesion onion")
            assert a is not None and b is not None
            # Mismas claves en ambos lados (handshake ECDH simetrico)
            self.assertEqual(a.session_key, b.session_key)
            self.assertEqual(len(a.session_key), 32)

            for pm in (alice_pm, bob_pm, *r_pms):
                pm._running = False
                if pm._udp_sock is not None:
                    pm._udp_sock.close()


class TestOnionSignatureVerification(unittest.TestCase):
    """Las firmas Ed25519 en hs1/hs2 se verifican correctamente."""

    def test_hs1_signature_valid_accepted(self) -> None:
        net = MagicMock()
        net._signing_key = SigningKey.generate().encode().hex()
        net._verify_key = "00" * 32
        net._fingerprint = "ff" * 8
        pm = PunchManager(net)
        eph_pk = b"\x01" * 32
        nonce = "abc123"
        to_sign = (
            b"onion_hs1|" + eph_pk.hex().encode()
            + b"|" + nonce.encode() + b"|" + net._verify_key.encode()
        )
        sig = pm._sign_onion_payload(to_sign)
        net_vk = SigningKey(bytes.fromhex(net._signing_key)).verify_key.encode().hex()
        self.assertTrue(pm._verify_onion_signature(to_sign, sig, net_vk))

    def test_hs1_signature_tampered_rejected(self) -> None:
        net = MagicMock()
        net._signing_key = SigningKey.generate().encode().hex()
        pm = PunchManager(net)
        eph_pk = b"\x01" * 32
        to_sign = b"onion_hs1|" + eph_pk.hex().encode() + b"|abc|fff"
        sig = pm._sign_onion_payload(to_sign)
        tampered = b"onion_hs1|" + (b"\x02" * 32).hex().encode() + b"|abc|fff"
        net_vk = SigningKey(bytes.fromhex(net._signing_key)).verify_key.encode().hex()
        self.assertFalse(pm._verify_onion_signature(tampered, sig, net_vk))


class TestDegradedMode(unittest.TestCase):
    """PunchManager fallido no rompe el resto de PeerNetwork."""

    def test_punch_request_rejected_when_no_manager(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            net = _make_net("Alone", tmp_path)
            net._punch_manager = None
            # _request_punch retorna False sin crashear
            self.assertFalse(net._request_punch("target_fp", "coord_fp"))


if __name__ == "__main__":
    unittest.main()
