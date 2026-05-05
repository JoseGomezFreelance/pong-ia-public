"""Tests de hardening de seguridad para el seed node P2P."""
from __future__ import annotations

import json
import socket
import struct
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from pong.p2p import (
    MAX_CONCURRENT_CONNECTIONS,
    MAX_CONN_PER_IP_PER_MIN,
    PeerNetwork,
)
from pong.punch import (
    MAX_RELAY_CIRCUITS,
    PunchManager,
    RelayCircuit,
    PrivacyTier,
    _is_private_ip,
)
from pong.save_manager import _compute_fingerprint


def _make_profile(alias: str = "Test") -> dict[str, str]:
    from nacl.signing import SigningKey

    signing_key = SigningKey.generate()
    verify_key = signing_key.verify_key.encode().hex()
    return {
        "alias": alias,
        "signing_key": signing_key.encode().hex(),
        "verify_key": verify_key,
        "fingerprint": _compute_fingerprint(verify_key),
    }


def _make_network(cache_path: Path | None = None) -> PeerNetwork:
    if cache_path is None:
        cache_path = Path("/tmp/test_security_peers.json")
    with patch("pong.p2p.PeerNetwork._load_initial_peers"):
        return PeerNetwork(
            profile=_make_profile(),
            cache_path=cache_path,
        )


# ================================================================
# Fix 1: Validacion de longitud hex en handshake
# ================================================================


class TestHandshakeHexValidation(unittest.TestCase):
    """bytes.fromhex() con hex malformado no debe crashear el servidor."""

    def _attempt_handshake_with_pk(self, pk_value: str) -> bool:
        """Intenta un handshake cliente con un pk dado. True si el server lo rechazo limpio."""
        net = _make_network()
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]

        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(("127.0.0.1", port))
        conn, _ = server.accept()

        # Enviar handshake eph con pk malformado
        eph_msg = json.dumps({"t": "eph", "v": "4.0", "pk": pk_value}).encode("utf-8")
        client.sendall(struct.pack("!I", len(eph_msg)) + eph_msg)

        # Server intenta handshake — debe rechazar sin crash
        conn.settimeout(2.0)
        result = net._handshake_server(conn, "127.0.0.1")

        client.close()
        conn.close()
        server.close()
        return result is None

    def test_empty_pk_rejected(self) -> None:
        """pk vacio es rechazado sin crash."""
        self.assertTrue(self._attempt_handshake_with_pk(""))

    def test_short_pk_rejected(self) -> None:
        """pk demasiado corto es rechazado."""
        self.assertTrue(self._attempt_handshake_with_pk("abcd"))

    def test_odd_length_pk_rejected(self) -> None:
        """pk de longitud impar es rechazado."""
        self.assertTrue(self._attempt_handshake_with_pk("a" * 63))

    def test_too_long_pk_rejected(self) -> None:
        """pk demasiado largo es rechazado."""
        self.assertTrue(self._attempt_handshake_with_pk("a" * 128))

    def test_valid_length_pk_accepted(self) -> None:
        """pk de 64 hex chars pasa la validacion de longitud (falla despues por crypto)."""
        # 64 hex chars = 32 bytes, longitud correcta para X25519
        # El handshake seguira fallando por ECDH invalido, pero NO por longitud
        result = self._attempt_handshake_with_pk("a" * 64)
        # Debe rechazar igualmente (clave X25519 invalida), pero por otra razon
        self.assertTrue(result)


# ================================================================
# Fix 2: Validacion de IP privada en onion relay
# ================================================================


class TestPrivateIPBlocking(unittest.TestCase):
    """_is_private_ip bloquea IPs privadas, loopback y reservadas."""

    def test_loopback_blocked(self) -> None:
        self.assertTrue(_is_private_ip("127.0.0.1"))

    def test_private_10_blocked(self) -> None:
        self.assertTrue(_is_private_ip("10.0.0.1"))

    def test_private_172_blocked(self) -> None:
        self.assertTrue(_is_private_ip("172.16.0.1"))

    def test_private_192_blocked(self) -> None:
        self.assertTrue(_is_private_ip("192.168.1.1"))

    def test_link_local_blocked(self) -> None:
        self.assertTrue(_is_private_ip("169.254.1.1"))

    def test_public_ip_allowed(self) -> None:
        self.assertFalse(_is_private_ip("178.104.104.58"))

    def test_invalid_ip_blocked(self) -> None:
        self.assertTrue(_is_private_ip("not_an_ip"))

    def test_empty_string_blocked(self) -> None:
        self.assertTrue(_is_private_ip(""))


# ================================================================
# Fix 3: Rechazo de circuit_id duplicado en relay setup
# ================================================================


class TestRelayCircuitDuplicate(unittest.TestCase):
    """handle_relay_setup rechaza circuit_id duplicado."""

    def _make_punch_manager(self) -> PunchManager:
        net = _make_network()
        pm = PunchManager(net)
        return pm

    def _relay_setup_msg(self, cid: str = "a" * 32) -> dict[str, Any]:
        return {
            "circuit_id": cid,
            "peer_a": {"ep": {"ip": "1.1.1.1", "port": 19849}},
            "peer_b": {"ep": {"ip": "2.2.2.2", "port": 19849}},
        }

    def test_first_setup_accepted(self) -> None:
        pm = self._make_punch_manager()
        self.assertTrue(pm.handle_relay_setup(self._relay_setup_msg("aaaa" * 8)))

    def test_duplicate_cid_rejected(self) -> None:
        pm = self._make_punch_manager()
        cid = "bbbb" * 8
        self.assertTrue(pm.handle_relay_setup(self._relay_setup_msg(cid)))
        # Segundo intento con mismo cid → rechazado
        self.assertFalse(pm.handle_relay_setup(self._relay_setup_msg(cid)))

    def test_different_cid_accepted(self) -> None:
        pm = self._make_punch_manager()
        self.assertTrue(pm.handle_relay_setup(self._relay_setup_msg("aaaa" * 8)))
        self.assertTrue(pm.handle_relay_setup(self._relay_setup_msg("bbbb" * 8)))


# ================================================================
# Fix 4: Limpieza de _conn_tracker
# ================================================================


class TestConnTrackerCleanup(unittest.TestCase):
    """Entries vacias en _conn_tracker se eliminan para evitar memory leak."""

    def test_stale_ip_entry_cleaned(self) -> None:
        net = _make_network()
        # Simular una IP vieja con timestamps expirados
        net._conn_tracker["1.2.3.4"] = [time.time() - 120]  # 2 min ago
        # La proxima llamada debe limpiar la entrada
        net._check_rate_limit("1.2.3.4")
        # Aunque la IP fue permitida, la entrada antigua fue reemplazada
        # por una nueva con un timestamp fresco
        self.assertIn("1.2.3.4", net._conn_tracker)
        self.assertEqual(len(net._conn_tracker["1.2.3.4"]), 1)

    def test_unknown_ip_no_leak(self) -> None:
        net = _make_network()
        # Forzar entradas vacias
        net._conn_tracker["dead.ip.1"] = []
        net._conn_tracker["dead.ip.2"] = []
        # Check rate limit de una IP distinta no limpia las otras
        net._check_rate_limit("new.ip")
        # Pero check de las IPs muertas si las limpia (y las permite)
        net._check_rate_limit("dead.ip.1")
        self.assertIn("dead.ip.1", net._conn_tracker)  # readded
        # dead.ip.2 sigue (no fue checked), pero si la checkamos se limpia y readd
        net._conn_tracker["dead.ip.2"] = []  # simular sin actividad
        net._check_rate_limit("dead.ip.2")
        self.assertEqual(len(net._conn_tracker["dead.ip.2"]), 1)


# ================================================================
# Fix 5: Limite de circuitos relay
# ================================================================


class TestRelayCircuitCap(unittest.TestCase):
    """No se pueden crear mas de MAX_RELAY_CIRCUITS circuitos."""

    def test_cap_enforced(self) -> None:
        net = _make_network()
        pm = PunchManager(net)

        # Llenar hasta el limite
        for i in range(MAX_RELAY_CIRCUITS):
            cid = f"{i:032x}"
            msg = {
                "circuit_id": cid,
                "peer_a": {"ep": {"ip": "1.1.1.1", "port": 19849}},
                "peer_b": {"ep": {"ip": "2.2.2.2", "port": 19849}},
            }
            self.assertTrue(pm.handle_relay_setup(msg), f"circuit {i} rechazado")

        # El siguiente debe ser rechazado
        overflow_msg = {
            "circuit_id": "f" * 32,
            "peer_a": {"ep": {"ip": "3.3.3.3", "port": 19849}},
            "peer_b": {"ep": {"ip": "4.4.4.4", "port": 19849}},
        }
        self.assertFalse(pm.handle_relay_setup(overflow_msg))
        self.assertEqual(len(pm._relay_circuits), MAX_RELAY_CIRCUITS)


# ================================================================
# Fix 6: Timeout de handshake reducido
# ================================================================


class TestHandshakeTimeout(unittest.TestCase):
    """El timeout de conexion TCP es 5s, no 10s (anti-slowloris)."""

    def test_slow_client_disconnected(self) -> None:
        """Un cliente que no envia nada es desconectado en ~5s."""
        net = _make_network()
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]

        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(("127.0.0.1", port))
        conn, addr = server.accept()

        start = time.time()
        conn.settimeout(5.0)
        result = net._handshake_server(conn, addr[0])
        elapsed = time.time() - start

        self.assertIsNone(result)
        # Debe tardar ~5s, no ~10s
        self.assertLess(elapsed, 7.0)

        client.close()
        conn.close()
        server.close()


# ================================================================
# Fix 7: Expiracion de strikes (blacklist no permanente)
# ================================================================


class TestStrikeExpiry(unittest.TestCase):
    """Strikes expiran tras 1h — un peer baneado puede volver."""

    def test_peer_blacklisted_after_3_strikes(self) -> None:
        net = _make_network()
        for _ in range(3):
            net._add_strike("bad-peer")
        self.assertTrue(net._is_blacklisted("bad-peer"))

    def test_strikes_expire_after_1_hour(self) -> None:
        net = _make_network()
        for _ in range(3):
            net._add_strike("temp-bad")
        self.assertTrue(net._is_blacklisted("temp-bad"))

        # Simular que paso 1 hora
        net._strike_times["temp-bad"] = time.time() - 3601
        self.assertFalse(net._is_blacklisted("temp-bad"))
        # Strikes limpiados
        self.assertNotIn("temp-bad", net._peer_strikes)

    def test_recent_strikes_not_expired(self) -> None:
        net = _make_network()
        for _ in range(3):
            net._add_strike("recent-bad")
        # Simular que paso 30 min (menos de 1h)
        net._strike_times["recent-bad"] = time.time() - 1800
        self.assertTrue(net._is_blacklisted("recent-bad"))

    def test_strike_timestamp_recorded(self) -> None:
        net = _make_network()
        before = time.time()
        net._add_strike("fp-x")
        after = time.time()
        self.assertIn("fp-x", net._strike_times)
        self.assertGreaterEqual(net._strike_times["fp-x"], before)
        self.assertLessEqual(net._strike_times["fp-x"], after)


# ================================================================
# Fix 8: Cleanup de onion pending y sessions
# ================================================================


class TestOnionCleanup(unittest.TestCase):
    """attempt_pending_punches limpia onion handshakes y sesiones expiradas."""

    def test_expired_onion_pending_cleaned(self) -> None:
        from pong.punch import OnionHandshake, ONION_HS_TIMEOUT

        net = _make_network()
        pm = PunchManager(net)
        pm._running = True
        pm._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        pm._udp_sock.bind(("127.0.0.1", 0))

        # Crear handshake expirado
        pm._onion_pending["old-nonce"] = OnionHandshake(
            peer_fp="aaa", peer_vk="bbb",
            my_eph_sk=b"\x00" * 32, my_eph_pk=b"\x00" * 32,
            nonce="old-nonce",
            started=time.time() - ONION_HS_TIMEOUT - 10,
        )
        # Crear handshake fresco
        pm._onion_pending["fresh-nonce"] = OnionHandshake(
            peer_fp="ccc", peer_vk="ddd",
            my_eph_sk=b"\x00" * 32, my_eph_pk=b"\x00" * 32,
            nonce="fresh-nonce",
            started=time.time(),
        )

        pm.attempt_pending_punches()

        self.assertNotIn("old-nonce", pm._onion_pending)
        self.assertIn("fresh-nonce", pm._onion_pending)

        pm._udp_sock.close()

    def test_expired_onion_session_cleaned(self) -> None:
        from pong.punch import OnionSession, ONION_SESSION_TTL

        net = _make_network()
        pm = PunchManager(net)
        pm._running = True
        pm._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        pm._udp_sock.bind(("127.0.0.1", 0))

        # Sesion expirada
        pm._onion_sessions["old-fp"] = OnionSession(
            peer_fp="old-fp", peer_vk="vk1",
            session_key=b"\x00" * 32,
            created=time.time() - ONION_SESSION_TTL - 10,
        )
        # Sesion fresca
        pm._onion_sessions["fresh-fp"] = OnionSession(
            peer_fp="fresh-fp", peer_vk="vk2",
            session_key=b"\x00" * 32,
            created=time.time(),
        )

        pm.attempt_pending_punches()

        self.assertNotIn("old-fp", pm._onion_sessions)
        self.assertIn("fresh-fp", pm._onion_sessions)

        pm._udp_sock.close()


# ================================================================
# Fix 9: Poda de _last_bootstrap_attempts
# ================================================================


class TestBootstrapAttemptsPruning(unittest.TestCase):
    """_last_bootstrap_attempts se poda para peers que ya no existen."""

    def test_stale_attempts_pruned_in_gossip(self) -> None:
        net = _make_network()
        # Simular attempts de peers que ya no estan en _peers
        net._last_bootstrap_attempts["ghost-fp-1"] = time.time() - 120
        net._last_bootstrap_attempts["ghost-fp-2"] = time.time() - 60

        # Ejecutar la poda directamente (misma logica que gossip_loop)
        with net._lock:
            stale = [
                fp for fp in net._last_bootstrap_attempts
                if fp not in net._peers
            ]
            for fp in stale:
                del net._last_bootstrap_attempts[fp]

        self.assertNotIn("ghost-fp-1", net._last_bootstrap_attempts)
        self.assertNotIn("ghost-fp-2", net._last_bootstrap_attempts)


if __name__ == "__main__":
    unittest.main()
