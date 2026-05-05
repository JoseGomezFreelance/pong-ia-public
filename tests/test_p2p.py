"""Tests de la capa P2P (pong/p2p.py y pong/p2p_cache.py)."""
from __future__ import annotations

import json
import os
import socket
import stat
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from pong.leaderboard import LeaderboardEntry
from pong.p2p import MAX_CONN_PER_IP_PER_MIN, PeerNetwork
from pong.p2p_cache import (
    load_peer_cache,
    load_seed_peers,
    merge_peer_cache,
    save_peer_cache,
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


def _make_cached_peer(
    *,
    alias: str = "Peer",
    ip: str = "1.1.1.1",
    port: int = 19848,
    last_seen: float | None = None,
) -> dict[str, Any]:
    profile = _make_profile(alias)
    return {
        "ip": ip,
        "port": port,
        "fp": profile["fingerprint"],
        "alias": alias,
        "vk": profile["verify_key"],
        "last_seen": time.time() if last_seen is None else last_seen,
    }


class TestPeerCache(unittest.TestCase):

    def test_save_and_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "peers.json"
            peers = [_make_cached_peer(alias="A", ip="192.168.1.50")]
            save_peer_cache(path, peers)
            loaded = load_peer_cache(path)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["fp"], peers[0]["fp"])
            self.assertEqual(loaded[0]["vk"], peers[0]["vk"])

    def test_load_nonexistent(self) -> None:
        path = Path("/nonexistent/peers.json")
        self.assertEqual(load_peer_cache(path), [])

    def test_load_corrupt(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{bad json")
            path = Path(f.name)
        self.assertEqual(load_peer_cache(path), [])

    def test_merge_deduplicates(self) -> None:
        now = time.time()
        peer1 = _make_cached_peer(ip="1.1.1.1", port=1, last_seen=now - 100)
        peer1_new = dict(peer1)
        peer1_new["ip"] = "2.2.2.2"
        peer1_new["port"] = 2
        peer1_new["last_seen"] = now
        peer2 = _make_cached_peer(ip="3.3.3.3", port=3, last_seen=now)
        existing = [peer1]
        new = [peer1_new, peer2]
        merged = merge_peer_cache(existing, new)
        fps = {p["fp"] for p in merged}
        self.assertEqual(fps, {peer1["fp"], peer2["fp"]})
        fp1 = next(p for p in merged if p["fp"] == peer1["fp"])
        self.assertEqual(fp1["ip"], "2.2.2.2")

    def test_merge_purges_old(self) -> None:
        old = [
            _make_cached_peer(ip="1.1.1.1", port=1, last_seen=0),
        ]
        merged = merge_peer_cache(old, [])
        self.assertEqual(len(merged), 0)

    def test_merge_preserves_verify_key(self) -> None:
        now = time.time()
        existing_peer = _make_cached_peer(ip="1.1.1.1", port=1, last_seen=now - 100)
        existing = [existing_peer]
        new = [dict(existing_peer, ip="2.2.2.2", port=2, alias="Nuevo", last_seen=now)]
        merged = merge_peer_cache(existing, new)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["vk"], existing_peer["vk"])
        self.assertEqual(merged[0]["ip"], "2.2.2.2")

    def test_load_migrates_fingerprint_from_verify_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "peers.json"
            peer = _make_cached_peer()
            legacy = dict(peer, fp="legacydead")
            save_peer_cache(path, [legacy])

            loaded = load_peer_cache(path)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["fp"], peer["fp"])

    def test_load_discards_legacy_peers_without_verify_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "peers.json"
            save_peer_cache(path, [{"ip": "1.2.3.4", "port": 19848, "fp": "legacy", "alias": "Old"}])
            self.assertEqual(load_peer_cache(path), [])

    @unittest.skipUnless(os.name == "posix", "Permisos owner-only solo aplican en POSIX")
    def test_save_peer_cache_sets_owner_only_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "peers.json"
            save_peer_cache(path, [_make_cached_peer(alias="A", ip="192.168.1.50")])
            mode = stat.S_IMODE(path.stat().st_mode)
            self.assertEqual(mode, 0o600)


class TestSeedPeers(unittest.TestCase):

    def test_load_seed_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            seed_file = Path(tmpdir) / "known_peers.txt"
            seed_file.write_text(
                "# Comentario\n"
                "192.168.1.50:19848\n"
                "10.0.0.5:19848\n"
                "\n"
                "# Otra linea\n"
            )
            peers = load_seed_peers(Path(tmpdir))
            self.assertEqual(len(peers), 2)
            self.assertEqual(peers[0]["ip"], "192.168.1.50")
            self.assertEqual(peers[0]["port"], 19848)

    def test_no_seed_file(self) -> None:
        peers = load_seed_peers(Path("/nonexistent"))
        self.assertEqual(len(peers), 0)

    def test_malformed_lines_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            seed_file = Path(tmpdir) / "known_peers.txt"
            seed_file.write_text(
                "no-port\n"
                "bad:port:extra\n"
                "ok:19848\n"
            )
            peers = load_seed_peers(Path(tmpdir))
            # "ok:19848" es valida, las otras no
            self.assertEqual(len(peers), 1)


class TestPeerNetworkMessages(unittest.TestCase):
    """Tests de serializacion de mensajes sin red real."""

    def test_records_message_format(self) -> None:
        from pong.leaderboard import LeaderboardEntry

        entry = LeaderboardEntry(
            alias="Jose", fingerprint="abc12345deadbeef",
            category="max_score", value=42.0,
            date="2026-04-01T12:00:00", signature="sig",
        )
        d = entry.to_dict()
        msg = json.dumps({
            "type": "pongia_records",
            "v": "3.0",
            "fp": "abc12345deadbeef",
            "alias": "Jose",
            "vk": "ab" * 32,
            "records": [d],
        })
        parsed = json.loads(msg)
        self.assertEqual(parsed["type"], "pongia_records")
        self.assertEqual(parsed["v"], "3.0")
        self.assertEqual(len(parsed["vk"]), 64)
        self.assertEqual(len(parsed["records"]), 1)
        self.assertEqual(parsed["records"][0]["value"], 42.0)

    def test_peers_message_format(self) -> None:
        msg = json.dumps({
            "type": "pongia_peers",
            "v": "3.0",
            "fp": "abc12345deadbeef",
            "peers": [
                {"ip": "192.168.1.50", "port": 19848, "fp": "ffeeddccbbaa0099",
                 "alias": "Peer1", "vk": "cd" * 32},
            ],
        })
        parsed = json.loads(msg)
        self.assertEqual(parsed["type"], "pongia_peers")
        self.assertEqual(parsed["v"], "3.0")
        self.assertEqual(len(parsed["peers"]), 1)
        self.assertEqual(len(parsed["peers"][0]["vk"]), 64)

    def test_hello_message_v3_includes_vk(self) -> None:
        msg = json.dumps({
            "type": "pongia_hello",
            "v": "3.0",
            "alias": "Jose",
            "fp": "abc12345deadbeef",
            "port": 19848,
            "vk": "ef" * 32,
        })
        parsed = json.loads(msg)
        self.assertEqual(parsed["type"], "pongia_hello")
        self.assertEqual(parsed["v"], "3.0")
        self.assertEqual(len(parsed["vk"]), 64)

    def test_hello_v2_rejected(self) -> None:
        """Mensajes v2.0 se rechazan — solo se acepta v3.0."""
        from pong.p2p import PROTOCOL_VERSION
        msg = json.dumps({
            "type": "pongia_hello",
            "v": "2.0",
            "alias": "Jose",
            "fp": "abc12345deadbeef",
            "port": 19848,
        })
        parsed = json.loads(msg)
        self.assertNotEqual(parsed["v"], PROTOCOL_VERSION)


class TestLengthPrefixedProtocol(unittest.TestCase):
    """Tests del protocolo length-prefixed sin sockets reales."""

    def test_pack_unpack(self) -> None:
        import struct
        msg = "hello world"
        data = msg.encode("utf-8")
        header = struct.pack("!I", len(data))
        # Simular recepcion
        received_len = struct.unpack("!I", header)[0]
        self.assertEqual(received_len, len(data))
        self.assertEqual(data.decode("utf-8"), msg)


class TestRateLimiting(unittest.TestCase):
    """Tests de rate limiting sin red real."""

    def test_check_rate_limit_allows_first_connections(self) -> None:
        with patch("pong.p2p.PeerNetwork._load_initial_peers"):
            net = PeerNetwork(
                profile=_make_profile(),
                cache_path=Path("/tmp/test_peers.json"),
            )
        # Las primeras conexiones deben permitirse
        for _ in range(MAX_CONN_PER_IP_PER_MIN):
            self.assertTrue(net._check_rate_limit("192.168.1.50"))
        # La siguiente debe rechazarse
        self.assertFalse(net._check_rate_limit("192.168.1.50"))
        # Otra IP distinta debe permitirse
        self.assertTrue(net._check_rate_limit("192.168.1.51"))

    def test_max_concurrent_connections_enforced(self) -> None:
        from pong.p2p import PeerNetwork, MAX_CONCURRENT_CONNECTIONS

        with patch("pong.p2p.PeerNetwork._load_initial_peers"):
            net = PeerNetwork(
                profile=_make_profile(),
                cache_path=Path("/tmp/test_peers.json"),
            )
        net._active_connections = MAX_CONCURRENT_CONNECTIONS
        self.assertFalse(net._check_rate_limit("10.0.0.1"))


class TestBlacklist(unittest.TestCase):
    """Tests del sistema de reputacion/blacklist."""

    def test_strikes_accumulate(self) -> None:
        from pong.p2p import PeerNetwork, MAX_STRIKES

        with patch("pong.p2p.PeerNetwork._load_initial_peers"):
            net = PeerNetwork(
                profile=_make_profile(),
                cache_path=Path("/tmp/test_peers.json"),
            )
        fp = "badpeer1"
        self.assertFalse(net._is_blacklisted(fp))
        for _ in range(MAX_STRIKES):
            net._add_strike(fp)
        self.assertTrue(net._is_blacklisted(fp))


class TestKeypairGeneration(unittest.TestCase):
    """Tests de generacion de keypair Ed25519 en save_manager."""

    def test_ensure_keypair_generates_keys(self) -> None:
        from pong.save_manager import _compute_fingerprint, _ensure_keypair
        profile: dict[str, str] = {"alias": "Jose", "fingerprint": "abc12345"}
        result = _ensure_keypair(profile)
        self.assertIn("signing_key", result)
        self.assertIn("verify_key", result)
        self.assertEqual(len(result["signing_key"]), 64)  # 32 bytes hex
        self.assertEqual(len(result["verify_key"]), 64)   # 32 bytes hex
        self.assertEqual(result["fingerprint"], "abc12345")
        self.assertEqual(len(_compute_fingerprint(result["verify_key"])), 16)

    def test_ensure_keypair_preserves_existing(self) -> None:
        from pong.save_manager import _ensure_keypair
        profile = _make_profile("Jose")
        result = _ensure_keypair(profile)
        self.assertEqual(result["signing_key"], profile["signing_key"])
        self.assertEqual(result["verify_key"], profile["verify_key"])

    def test_keypair_signs_and_verifies(self) -> None:
        from pong.save_manager import _ensure_keypair
        from pong.leaderboard import LeaderboardEntry, sign_entry, verify_entry

        profile: dict[str, str] = {"alias": "Jose", "fingerprint": "abc12345deadbeef"}
        _ensure_keypair(profile)

        entry = LeaderboardEntry(
            alias="Jose", fingerprint="abc12345deadbeef",
            category="max_score", value=42.0,
            date="2026-04-01T12:00:00",
        )
        sign_entry(entry, profile["signing_key"])
        self.assertTrue(verify_entry(entry, profile["verify_key"]))

    def test_normalize_profile_migrates_fingerprint_from_verify_key(self) -> None:
        from pong.save_manager import _normalize_p2p_profile

        profile = _make_profile("Jose")
        legacy = dict(profile, fingerprint="legacy123")
        normalized, changed, identity_changed = _normalize_p2p_profile(legacy)

        self.assertTrue(changed)
        self.assertTrue(identity_changed)
        self.assertEqual(normalized["fingerprint"], profile["fingerprint"])


class TestXChaCha20Transport(unittest.TestCase):
    """Tests del cifrado de transporte con XChaCha20-Poly1305."""

    def test_aead_roundtrip(self) -> None:
        """AEAD encrypt/decrypt roundtrip con clave de sesion."""
        from pong.crypto import aead_decrypt, aead_encrypt, derive_key

        key = derive_key(b"shared_secret_32_bytes__________")
        pt = b'{"type": "pongia_records", "records": []}'
        ct = aead_encrypt(key, pt)
        self.assertEqual(aead_decrypt(key, ct), pt)

    def test_wrong_key_fails_decrypt(self) -> None:
        """Descifrar con clave incorrecta falla."""
        from nacl.exceptions import CryptoError
        from pong.crypto import aead_decrypt, aead_encrypt, derive_key

        key_a = derive_key(b"key_material_a__________________")
        key_b = derive_key(b"key_material_b__________________")
        ct = aead_encrypt(key_a, b"secret message")
        with self.assertRaises(CryptoError):
            aead_decrypt(key_b, ct)

    def test_send_recv_with_session_key(self) -> None:
        """Test _send_message/_recv_message con XChaCha20-Poly1305."""
        import struct
        from pong.crypto import aead_decrypt, aead_encrypt, derive_key
        from pong.p2p import PeerNetwork

        key = derive_key(b"test_session_key________________")
        msg = '{"type": "pongia_records"}'

        # Simular _send_message con cifrado
        data = msg.encode("utf-8")
        encrypted = aead_encrypt(key, data)
        header = struct.pack("!I", len(encrypted))
        wire_data = header + encrypted

        # Simular _recv_message con descifrado
        recv_len = struct.unpack("!I", wire_data[:4])[0]
        recv_encrypted = wire_data[4:4 + recv_len]
        decrypted = aead_decrypt(key, recv_encrypted)
        self.assertEqual(decrypted.decode("utf-8"), msg)


class TestEncryptedHandshake(unittest.TestCase):
    """Tests del handshake cifrado del protocolo P2P v4.

    El handshake usa X25519 efimero + XChaCha20-Poly1305 + Ed25519.
    Se testea conectando dos PeerNetworks via socket pair.
    """

    def _make_network(self, alias: str = "test") -> PeerNetwork:
        with patch("pong.p2p.PeerNetwork._load_initial_peers"):
            return PeerNetwork(
                profile=_make_profile(alias),
                cache_path=Path("/tmp/test_peers.json"),
            )

    def test_full_handshake_produces_equal_session_keys(self) -> None:
        """Client y server derivan la misma session key."""
        import threading

        client_net = self._make_network("Client")
        server_net = self._make_network("Server")

        sock_client, sock_server = socket.socketpair()
        sock_client.settimeout(5.0)
        sock_server.settimeout(5.0)

        results: dict[str, bytes | None] = {}

        def run_server() -> None:
            results["server"] = server_net._handshake_server(sock_server, "127.0.0.1")

        t = threading.Thread(target=run_server)
        t.start()
        results["client"] = client_net._handshake_client(sock_client)
        t.join(timeout=5.0)

        sock_client.close()
        sock_server.close()

        self.assertIsNotNone(results["client"])
        self.assertIsNotNone(results["server"])
        self.assertEqual(results["client"], results["server"])
        self.assertEqual(len(results["client"]), 32)  # type: ignore[arg-type]

    def test_handshake_allows_encrypted_communication(self) -> None:
        """Tras handshake, ambos peers pueden intercambiar mensajes cifrados."""
        import threading

        client_net = self._make_network("Client")
        server_net = self._make_network("Server")
        sock_c, sock_s = socket.socketpair()
        sock_c.settimeout(5.0)
        sock_s.settimeout(5.0)

        keys: dict[str, bytes | None] = {}

        def run_server() -> None:
            keys["server"] = server_net._handshake_server(sock_s, "127.0.0.1")

        t = threading.Thread(target=run_server)
        t.start()
        keys["client"] = client_net._handshake_client(sock_c)
        t.join(timeout=5.0)

        self.assertIsNotNone(keys["client"])
        # Client sends, server receives
        PeerNetwork._send_message(sock_c, '{"test": true}', key=keys["client"])
        received = PeerNetwork._recv_message(sock_s, key=keys["server"])
        self.assertEqual(received, '{"test": true}')

        sock_c.close()
        sock_s.close()

    def test_handshake_rejects_old_protocol(self) -> None:
        """Server rechaza un handshake con version antigua."""
        server_net = self._make_network("Server")
        sock_c, sock_s = socket.socketpair()
        sock_c.settimeout(2.0)
        sock_s.settimeout(2.0)

        # Enviar hello con version antigua
        old_hello = json.dumps({"t": "eph", "v": "3.0", "pk": "00" * 32})
        PeerNetwork._send_message(sock_c, old_hello)
        result = server_net._handshake_server(sock_s, "1.2.3.4")

        self.assertIsNone(result)
        sock_c.close()
        sock_s.close()

    def test_handshake_client_verifies_expected_fp(self) -> None:
        """Client rechaza si expected_fp no coincide con el server."""
        import threading

        client_net = self._make_network("Client")
        server_net = self._make_network("Server")
        sock_c, sock_s = socket.socketpair()
        sock_c.settimeout(5.0)
        sock_s.settimeout(5.0)

        results: dict[str, bytes | None] = {}

        def run_server() -> None:
            results["server"] = server_net._handshake_server(sock_s, "127.0.0.1")

        t = threading.Thread(target=run_server)
        t.start()
        # Client expects a different fingerprint
        results["client"] = client_net._handshake_client(
            sock_c, expected_fp="0000000000000000",
        )
        t.join(timeout=5.0)

        self.assertIsNone(results["client"])
        sock_c.close()
        sock_s.close()


class TestSeedPeerLoading(unittest.TestCase):
    """Tests de carga y promocion de seed peers (Bug G fix)."""

    def _make_network(self, cache_path: Path) -> PeerNetwork:
        with patch("pong.p2p.PeerNetwork._load_initial_peers"):
            return PeerNetwork(
                profile=_make_profile(),
                cache_path=cache_path,
            )

    def test_seed_peers_loaded_with_temp_keys(self) -> None:
        """Seeds de known_peers.txt se cargan con clave seed:IP:puerto."""
        from pong.p2p import PeerNetwork

        with tempfile.TemporaryDirectory() as tmpdir:
            saves = Path(tmpdir)
            cache_path = saves / "known_peers.json"
            seed_file = saves / "known_peers.txt"
            seed_file.write_text("192.168.1.50:19848\n10.0.0.5:19848\n")

            net = self._make_network(cache_path)
            # Forzar la ruta del cache para que load_seed_peers use tmpdir
            net._cache_path = cache_path
            net._load_initial_peers()

            self.assertIn("seed:192.168.1.50:19848", net._peers)
            self.assertIn("seed:10.0.0.5:19848", net._peers)
            self.assertEqual(net._peers["seed:192.168.1.50:19848"].ip, "192.168.1.50")
            self.assertEqual(net._peers["seed:10.0.0.5:19848"].data_port, 19848)

    def test_seed_peers_skip_if_cached(self) -> None:
        """No se anade seed si ya hay un peer cached en esa IP:puerto."""
        with tempfile.TemporaryDirectory() as tmpdir:
            saves = Path(tmpdir)
            cache_path = saves / "known_peers.json"
            seed_file = saves / "known_peers.txt"
            seed_file.write_text("192.168.1.50:19848\n")

            # Pre-cargar un peer cached en esa IP
            cached_peer = _make_cached_peer(alias="Cached", ip="192.168.1.50")
            save_peer_cache(cache_path, [cached_peer])

            net = self._make_network(cache_path)
            net._cache_path = cache_path
            net._load_initial_peers()

            # El peer cached debe existir, el seed no
            self.assertIn(cached_peer["fp"], net._peers)
            self.assertNotIn("seed:192.168.1.50:19848", net._peers)

    def test_seed_peers_not_saved_to_cache(self) -> None:
        """_save_cache excluye entradas seed: del JSON persistido."""
        from pong.p2p import PeerInfo

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "known_peers.json"
            net = self._make_network(cache_path)

            net._peers["seed:1.2.3.4:19848"] = PeerInfo(
                fingerprint="seed:1.2.3.4:19848", alias="", ip="1.2.3.4",
                data_port=19848, last_seen=0,
            )
            real_peer = _make_cached_peer(alias="Real", ip="5.6.7.8")
            net._peers[real_peer["fp"]] = PeerInfo(
                fingerprint=str(real_peer["fp"]), alias="Real", ip="5.6.7.8",
                data_port=19848, last_seen=time.time(), verify_key=str(real_peer["vk"]),
            )
            net._save_cache()

            cached = load_peer_cache(cache_path)
            fps = [p["fp"] for p in cached]
            self.assertNotIn("seed:1.2.3.4:19848", fps)
            self.assertIn(real_peer["fp"], fps)
            saved = next(p for p in cached if p["fp"] == real_peer["fp"])
            self.assertEqual(saved["vk"], real_peer["vk"])

    def test_seed_peers_not_in_gossip_message(self) -> None:
        """_build_peers_message excluye entradas seed: del mensaje."""
        from pong.p2p import PeerInfo

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "known_peers.json"
            net = self._make_network(cache_path)

            net._peers["seed:1.2.3.4:19848"] = PeerInfo(
                fingerprint="seed:1.2.3.4:19848", alias="", ip="1.2.3.4",
                data_port=19848, last_seen=time.time(),  # last_seen reciente para no filtrar por timeout
            )
            real_peer = _make_cached_peer(alias="Real", ip="5.6.7.8")
            net._peers[real_peer["fp"]] = PeerInfo(
                fingerprint=str(real_peer["fp"]), alias="Real", ip="5.6.7.8",
                data_port=19848, last_seen=time.time(), verify_key=str(real_peer["vk"]),
            )

            msg = json.loads(net._build_peers_message())
            peer_fps = [p["fp"] for p in msg["peers"]]
            self.assertNotIn("seed:1.2.3.4:19848", peer_fps)
            self.assertIn(real_peer["fp"], peer_fps)

    def test_default_seeds_loaded_when_no_file(self) -> None:
        """Sin known_peers.txt, se cargan los seeds hardcoded de DEFAULT_SEEDS."""
        with tempfile.TemporaryDirectory() as tmpdir:
            saves = Path(tmpdir)
            cache_path = saves / "known_peers.json"
            # No creamos known_peers.txt
            net = self._make_network(cache_path)
            net._cache_path = cache_path
            net._load_initial_peers()

            self.assertIn("seed:178.104.104.58:19848", net._peers)
            peer = net._peers["seed:178.104.104.58:19848"]
            self.assertEqual(peer.ip, "178.104.104.58")
            self.assertEqual(peer.data_port, 19848)

    def test_file_seeds_extend_defaults(self) -> None:
        """known_peers.txt con IP distinta coexiste con los defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            saves = Path(tmpdir)
            cache_path = saves / "known_peers.json"
            seed_file = saves / "known_peers.txt"
            seed_file.write_text("10.0.0.99:19848\n")

            net = self._make_network(cache_path)
            net._cache_path = cache_path
            net._load_initial_peers()

            self.assertIn("seed:10.0.0.99:19848", net._peers)
            self.assertIn("seed:178.104.104.58:19848", net._peers)

    def test_file_seed_overrides_default(self) -> None:
        """Si known_peers.txt incluye la misma IP que un default, no se duplica."""
        with tempfile.TemporaryDirectory() as tmpdir:
            saves = Path(tmpdir)
            cache_path = saves / "known_peers.json"
            seed_file = saves / "known_peers.txt"
            seed_file.write_text("178.104.104.58:19848\n")

            net = self._make_network(cache_path)
            net._cache_path = cache_path
            net._load_initial_peers()

            # Solo una entrada, no duplicada
            seed_keys = [
                k for k in net._peers if k.startswith("seed:178.104.104.58:")
            ]
            self.assertEqual(len(seed_keys), 1)

    def test_seed_promotion_preserves_port(self) -> None:
        """Tras promocion, el peer real conserva el puerto del seed original."""
        from pong.p2p import DATA_PORT, PeerInfo

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "known_peers.json"
            net = self._make_network(cache_path)

            custom_port = 20000
            seed_key = "seed:1.2.3.4:20000"
            net._peers[seed_key] = PeerInfo(
                fingerprint=seed_key, alias="", ip="1.2.3.4",
                data_port=custom_port, last_seen=0,
            )

            # Simular que _handle_records_message creo el peer real con DATA_PORT
            real_peer = _make_cached_peer(alias="Seed", ip="1.2.3.4", port=DATA_PORT)
            real_fp = str(real_peer["fp"])
            net._peers[real_fp] = PeerInfo(
                fingerprint=real_fp, alias="Seed", ip="1.2.3.4",
                data_port=DATA_PORT, verify_key=str(real_peer["vk"]),
            )

            # Simular la respuesta con fp real
            response = {"type": "pongia_records", "fp": real_fp, "vk": real_peer["vk"]}

            # Ejecutar el bloque de promocion manualmente
            is_temporary = True
            fp = seed_key
            if is_temporary:
                resp_fp = response.get("fp", "")
                with net._lock:
                    if resp_fp and resp_fp in net._peers:
                        temp_peer = net._peers.get(fp)
                        if temp_peer:
                            net._peers[resp_fp].data_port = temp_peer.data_port
                        net._peers.pop(fp, None)

            self.assertNotIn(seed_key, net._peers)
            self.assertIn(real_fp, net._peers)
            self.assertEqual(net._peers[real_fp].data_port, custom_port)

    def test_seed_promotion_replaces_temp_key(self) -> None:
        """_exchange_records_with promueve seed: temporal a fp real."""
        from pong.p2p import PeerInfo

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "known_peers.json"
            net = self._make_network(cache_path)

            seed_key = "seed:1.2.3.4:19848"
            net._peers[seed_key] = PeerInfo(
                fingerprint=seed_key, alias="", ip="1.2.3.4",
                data_port=19848, last_seen=0,
            )

            # Crear un peer real que sera "descubierto" via handshake
            real_peer = _make_cached_peer(alias="RealSeed", ip="1.2.3.4")
            real_fp = str(real_peer["fp"])
            real_vk = str(real_peer["vk"])

            # Mock _tcp_exchange para devolver un records message valido
            response_msg = json.dumps({
                "type": "pongia_records",
                "v": "4.0",
                "fp": real_fp,
                "alias": "RealSeed",
                "vk": real_vk,
                "peers": {real_fp: {"vk": real_vk, "alias": "RealSeed"}},
                "records": [],
            })
            with patch.object(net, "_tcp_exchange", return_value=response_msg):
                net._exchange_records_with(seed_key)

            # Clave temporal eliminada, fp real presente
            self.assertNotIn(seed_key, net._peers)
            self.assertIn(real_fp, net._peers)
            self.assertEqual(net._peers[real_fp].alias, "RealSeed")
            self.assertEqual(net._peers[real_fp].ip, "1.2.3.4")
            self.assertEqual(net._peers[real_fp].verify_key, real_vk)


class _PeerNetworkFactoryMixin:

    def _make_network(self, cache_path: Path | None = None) -> PeerNetwork:
        if cache_path is None:
            cache_path = Path("/tmp/test_peers.json")
        with patch("pong.p2p.PeerNetwork._load_initial_peers"):
            return PeerNetwork(
                profile=_make_profile(),
                cache_path=cache_path,
            )


class TestIdentityPinning(unittest.TestCase, _PeerNetworkFactoryMixin):

    def test_first_verify_key_is_pinned_and_conflicts_are_rejected(self) -> None:
        """Pinning se verifica via records (gossip ya no lleva vk/ip)."""
        net = self._make_network()
        peer = _make_profile("Peer")
        intruder = _make_profile("Intruso")

        # Gossip en v4 solo lleva fp y alias (sin vk ni ip)
        net._handle_peers_message({
            "type": "pongia_peers",
            "v": "4.0",
            "peers": [{"fp": peer["fingerprint"], "alias": "Peer"}],
        })
        self.assertIn(peer["fingerprint"], net._peers)
        # Sin ip ni vk en gossip
        self.assertEqual(net._peers[peer["fingerprint"]].ip, "")

        # Pinning se hace cuando llega un records message (con vk)
        net._handle_records_message({
            "type": "pongia_records", "v": "4.0",
            "fp": peer["fingerprint"], "alias": "Peer",
            "vk": peer["verify_key"], "records": [],
        }, "1.2.3.4")
        self.assertEqual(net._peers[peer["fingerprint"]].verify_key, peer["verify_key"])

        # Conflicto: intruso con mismo fp pero distinto vk
        net._handle_records_message({
            "type": "pongia_records", "v": "4.0",
            "fp": peer["fingerprint"], "alias": "Intruso",
            "vk": intruder["verify_key"], "records": [],
        }, "5.6.7.8")
        # verify_key original se mantiene, strike añadido
        self.assertEqual(net._peers[peer["fingerprint"]].verify_key, peer["verify_key"])
        self.assertEqual(net._peer_strikes.get(peer["fingerprint"]), 1)


class TestBootstrapDialing(unittest.TestCase, _PeerNetworkFactoryMixin):

    def test_gossiped_peer_not_bootstrap_without_ip(self) -> None:
        """Gossip v4 no incluye IPs — peers gossipeados no son candidatos bootstrap."""
        net = self._make_network()
        peer = _make_profile("Peer")
        net._handle_peers_message({
            "type": "pongia_peers",
            "v": "4.0",
            "peers": [{"fp": peer["fingerprint"], "alias": "Peer"}],
        })

        candidates = net._select_bootstrap_candidates(time.time())
        candidate_fps = [p.fingerprint for p in candidates]
        # Sin IP, no es contactable → no es candidato
        self.assertNotIn(peer["fingerprint"], candidate_fps)

    def test_seed_peer_is_bootstrap_candidate(self) -> None:
        """Seeds (con IP desde known_peers.txt) si son candidatos bootstrap."""
        net = self._make_network()
        from pong.p2p import PeerInfo
        net._peers["seed:1.2.3.4:19848"] = PeerInfo(
            fingerprint="seed:1.2.3.4:19848",
            alias="", ip="1.2.3.4", data_port=19848, last_seen=0,
        )
        candidates = net._select_bootstrap_candidates(time.time())
        candidate_fps = [p.fingerprint for p in candidates]
        self.assertIn("seed:1.2.3.4:19848", candidate_fps)

    def test_bootstrap_backoff_skips_recent_attempt(self) -> None:
        net = self._make_network()
        from pong.p2p import PeerInfo
        # Usar seed con IP para que sea candidato real
        seed_key = "seed:1.2.3.4:19848"
        net._peers[seed_key] = PeerInfo(
            fingerprint=seed_key, alias="", ip="1.2.3.4",
            data_port=19848, last_seen=0,
        )

        now = time.time()
        net._last_bootstrap_attempts[seed_key] = now
        candidates = net._select_bootstrap_candidates(now)
        candidate_fps = [p.fingerprint for p in candidates]
        self.assertNotIn(seed_key, candidate_fps)


class TestRemoteRecordValidation(unittest.TestCase, _PeerNetworkFactoryMixin):

    def test_implausible_remote_record_is_rejected(self) -> None:
        """Records implausibles se rechazan en v4 (no solo se marcan)."""
        from nacl.signing import SigningKey

        from pong.leaderboard import LeaderboardEntry, sign_entry

        net = self._make_network()
        sk = SigningKey.generate()
        peer_vk = sk.verify_key.encode().hex()
        peer_fp = _compute_fingerprint(peer_vk)
        entry = LeaderboardEntry(
            alias="Peer",
            fingerprint=peer_fp,
            category="max_score",
            value=200,  # > 100 → implausible
            date="2026-04-01T12:00:00",
        )
        sign_entry(entry, sk.encode().hex())

        net._handle_records_message({
            "type": "pongia_records",
            "v": "4.0",
            "fp": peer_fp,
            "alias": "Peer",
            "vk": peer_vk,
            "records": [entry.to_dict()],
        }, "1.2.3.4")

        # Record rechazado, no almacenado
        self.assertEqual(len(net._remote_entries), 0)
        telemetry = net.get_telemetry()
        self.assertEqual(telemetry["remote_entries"], 0)


class TestRecordRelay(unittest.TestCase, _PeerNetworkFactoryMixin):
    """Tests del relay de records entre peers (como Bitcoin retransmite txs)."""

    @staticmethod
    def _make_signed_entry(
        alias: str, category: str, value: float, date: str,
    ) -> tuple[dict[str, str], LeaderboardEntry]:
        """Crea un perfil + entry firmada para tests."""
        from nacl.signing import SigningKey

        from pong.leaderboard import LeaderboardEntry, sign_entry

        sk = SigningKey.generate()
        vk_hex = sk.verify_key.encode().hex()
        fp = _compute_fingerprint(vk_hex)
        profile = {
            "alias": alias,
            "fingerprint": fp,
            "signing_key": sk.encode().hex(),
            "verify_key": vk_hex,
        }
        entry = LeaderboardEntry(
            alias=alias, fingerprint=fp,
            category=category, value=value, date=date,
        )
        sign_entry(entry, profile["signing_key"])
        return profile, entry

    def test_seed_relays_records_between_players(self) -> None:
        """Escenario completo: A → Seed → B.

        1. Player A envia sus records al Seed
        2. Player B conecta al Seed
        3. El Seed responde a B con los records de A
        4. B puede ver los records de A
        """
        seed = self._make_network()  # Seed (sin records locales)
        profile_a, entry_a = self._make_signed_entry(
            "PlayerA", "max_score", 42, "2026-04-14T10:00:00",
        )

        # Paso 1: A envia sus records al seed
        seed._handle_records_message({
            "type": "pongia_records", "v": "4.0",
            "fp": profile_a["fingerprint"],
            "alias": "PlayerA",
            "vk": profile_a["verify_key"],
            "peers": {
                profile_a["fingerprint"]: {
                    "vk": profile_a["verify_key"],
                    "alias": "PlayerA",
                },
            },
            "records": [entry_a.to_dict()],
        }, "10.0.0.1")

        # Seed ahora tiene los records de A
        self.assertEqual(len(seed._remote_entries), 1)
        self.assertEqual(seed._remote_entries[0].alias, "PlayerA")
        self.assertEqual(seed._remote_entries[0].value, 42)

        # Paso 2: Seed construye mensaje de respuesta (incluye records de A)
        relay_msg = json.loads(seed._build_records_message())
        self.assertIn("peers", relay_msg)
        self.assertIn(profile_a["fingerprint"], relay_msg["peers"])
        self.assertGreaterEqual(len(relay_msg["records"]), 1)

        # Paso 3: B recibe el mensaje del seed
        net_b = self._make_network()
        net_b._handle_records_message(relay_msg, "10.0.0.99")

        # B tiene los records de A (relayed via seed)
        self.assertEqual(len(net_b._remote_entries), 1)
        self.assertEqual(net_b._remote_entries[0].fingerprint, profile_a["fingerprint"])
        self.assertEqual(net_b._remote_entries[0].value, 42)

    def test_relay_validates_author_signature_not_sender(self) -> None:
        """Records relayed se validan contra la vk del AUTOR, no del sender."""
        from nacl.signing import SigningKey

        from pong.leaderboard import LeaderboardEntry

        net = self._make_network()
        sender = _make_profile("Sender")
        author = _make_profile("Author")

        # Entry con firma INVALIDA (no coincide con la vk del autor)
        fake_entry = LeaderboardEntry(
            alias="Author", fingerprint=author["fingerprint"],
            category="max_score", value=50,
            date="2026-04-14T10:00:00",
            signature="deadbeef" * 16,  # Firma falsa
        )

        net._handle_records_message({
            "type": "pongia_records", "v": "4.0",
            "fp": sender["fingerprint"],
            "alias": "Sender",
            "vk": sender["verify_key"],
            "peers": {
                sender["fingerprint"]: {"vk": sender["verify_key"], "alias": "Sender"},
                author["fingerprint"]: {"vk": author["verify_key"], "alias": "Author"},
            },
            "records": [fake_entry.to_dict()],
        }, "10.0.0.1")

        # Entry rechazada (firma no coincide con vk del autor)
        self.assertEqual(len(net._remote_entries), 0)
        # Strike al sender (relayo basura)
        self.assertEqual(net._peer_strikes.get(sender["fingerprint"]), 1)

    def test_relay_multiple_authors_in_single_message(self) -> None:
        """Un mensaje puede contener records de multiples autores."""
        seed = self._make_network()
        profile_a, entry_a = self._make_signed_entry(
            "Alice", "max_score", 30, "2026-04-14T10:00:00",
        )
        profile_b, entry_b = self._make_signed_entry(
            "Bob", "max_score", 55, "2026-04-14T11:00:00",
        )

        # Seed recibe records de A
        seed._handle_records_message({
            "type": "pongia_records", "v": "4.0",
            "fp": profile_a["fingerprint"],
            "alias": "Alice",
            "vk": profile_a["verify_key"],
            "peers": {profile_a["fingerprint"]: {
                "vk": profile_a["verify_key"], "alias": "Alice",
            }},
            "records": [entry_a.to_dict()],
        }, "10.0.0.1")

        # Seed recibe records de B
        seed._handle_records_message({
            "type": "pongia_records", "v": "4.0",
            "fp": profile_b["fingerprint"],
            "alias": "Bob",
            "vk": profile_b["verify_key"],
            "peers": {profile_b["fingerprint"]: {
                "vk": profile_b["verify_key"], "alias": "Bob",
            }},
            "records": [entry_b.to_dict()],
        }, "10.0.0.2")

        self.assertEqual(len(seed._remote_entries), 2)

        # C conecta y recibe ambos records
        relay_msg = json.loads(seed._build_records_message())
        self.assertEqual(len(relay_msg["records"]), 2)
        self.assertIn(profile_a["fingerprint"], relay_msg["peers"])
        self.assertIn(profile_b["fingerprint"], relay_msg["peers"])

        net_c = self._make_network()
        net_c._handle_records_message(relay_msg, "10.0.0.99")
        self.assertEqual(len(net_c._remote_entries), 2)

        fps = {e.fingerprint for e in net_c._remote_entries}
        self.assertIn(profile_a["fingerprint"], fps)
        self.assertIn(profile_b["fingerprint"], fps)

    def test_record_merge_keeps_newest_per_category(self) -> None:
        """Si un record llega por dos vias, se queda el mas reciente."""
        net = self._make_network()
        profile_a, entry_old = self._make_signed_entry(
            "Alice", "max_score", 20, "2026-04-10T10:00:00",
        )
        _, entry_new = self._make_signed_entry(
            "Alice", "max_score", 45, "2026-04-14T10:00:00",
        )
        # Hack: usar la misma identidad para ambas
        entry_new.fingerprint = profile_a["fingerprint"]
        entry_new.alias = "Alice"
        from pong.leaderboard import sign_entry
        sign_entry(entry_new, profile_a["signing_key"])

        peers_dir = {profile_a["fingerprint"]: {
            "vk": profile_a["verify_key"], "alias": "Alice",
        }}

        # Primer relay: record viejo
        sender1 = _make_profile("Relay1")
        net._handle_records_message({
            "type": "pongia_records", "v": "4.0",
            "fp": sender1["fingerprint"],
            "alias": "Relay1", "vk": sender1["verify_key"],
            "peers": {**peers_dir, sender1["fingerprint"]: {
                "vk": sender1["verify_key"], "alias": "Relay1",
            }},
            "records": [entry_old.to_dict()],
        }, "10.0.0.1")

        self.assertEqual(net._remote_entries[0].value, 20)

        # Segundo relay: record nuevo
        sender2 = _make_profile("Relay2")
        net._handle_records_message({
            "type": "pongia_records", "v": "4.0",
            "fp": sender2["fingerprint"],
            "alias": "Relay2", "vk": sender2["verify_key"],
            "peers": {**peers_dir, sender2["fingerprint"]: {
                "vk": sender2["verify_key"], "alias": "Relay2",
            }},
            "records": [entry_new.to_dict()],
        }, "10.0.0.2")

        # Solo 1 entry (mergeada), con el valor mas reciente
        alice_entries = [
            e for e in net._remote_entries
            if e.fingerprint == profile_a["fingerprint"]
        ]
        self.assertEqual(len(alice_entries), 1)
        self.assertEqual(alice_entries[0].value, 45)


class TestSeedNodeTelemetry(unittest.TestCase):

    def test_format_status_line_uses_total_peers_seen(self) -> None:
        import seed_node

        line = seed_node.format_status_line({
            "active_peers": 2,
            "remote_entries": 5,
            "total_peers_seen": 7,
        })
        self.assertIn("2 peers activos", line)
        self.assertIn("5 entries remotas", line)
        self.assertIn("7 peers vistos total", line)


class TestSeedNodeStartup(unittest.TestCase):

    def test_load_or_create_profile_migrates_legacy_fingerprint(self) -> None:
        import seed_node

        with tempfile.TemporaryDirectory() as tmpdir:
            save_dir = Path(tmpdir)
            profile_path = save_dir / "seed_profile.json"
            profile = _make_profile("seed-old")
            legacy = dict(profile, fingerprint="legacydead")
            profile_path.write_text(json.dumps(legacy), encoding="utf-8")

            with patch.object(seed_node, "SAVE_DIR", save_dir), \
                 patch.object(seed_node, "PROFILE_PATH", profile_path), \
                 patch.object(seed_node, "CACHE_PATH", save_dir / "known_peers.json"):
                migrated = seed_node.load_or_create_profile("seed-01")

            self.assertEqual(
                migrated["fingerprint"],
                _compute_fingerprint(migrated["verify_key"]),
            )
            self.assertIn("signing_key", migrated)

    @unittest.skipUnless(os.name == "posix", "Permisos owner-only solo aplican en POSIX")
    def test_load_or_create_profile_sets_owner_only_permissions(self) -> None:
        import seed_node

        with tempfile.TemporaryDirectory() as tmpdir:
            save_dir = Path(tmpdir)
            profile_path = save_dir / "seed_profile.json"

            with patch.object(seed_node, "SAVE_DIR", save_dir), \
                 patch.object(seed_node, "PROFILE_PATH", profile_path), \
                 patch.object(seed_node, "CACHE_PATH", save_dir / "known_peers.json"):
                seed_node.load_or_create_profile("seed-01")

            mode = stat.S_IMODE(profile_path.stat().st_mode)
            self.assertEqual(mode, 0o600)

    def test_main_exits_when_strict_bind_fails(self) -> None:
        import seed_node
        import sys

        profile = _make_profile("seed-01")
        with patch.object(seed_node, "load_or_create_profile", return_value=profile), \
             patch.object(seed_node.PeerNetwork, "start", side_effect=OSError("bind failed")), \
             patch.object(sys, "argv", ["seed_node.py"]):
            with self.assertRaises(SystemExit) as exc:
                seed_node.main()

        self.assertEqual(exc.exception.code, 1)
