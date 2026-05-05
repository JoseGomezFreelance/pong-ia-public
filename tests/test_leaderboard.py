"""Tests de rankings y leaderboard (pong/leaderboard.py y pong/save_manager.py)."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from pong.leaderboard import (
    LeaderboardEntry,
    _assign_display_aliases,
    _index_to_b64_suffix,
    check_plausibility,
    compute_entries_digest,
    format_entry_date,
    format_entry_value,
    get_local_entries,
    merge_entries,
    sign_entry,
    verify_entry,
)


class TestB64Suffix(unittest.TestCase):

    def test_first_index(self) -> None:
        self.assertEqual(_index_to_b64_suffix(0), "AAAA")

    def test_second_index(self) -> None:
        self.assertEqual(_index_to_b64_suffix(1), "AAAB")

    def test_large_index(self) -> None:
        # 64 = "AABA"
        self.assertEqual(_index_to_b64_suffix(64), "AABA")


class TestSignAndVerify(unittest.TestCase):

    def setUp(self) -> None:
        from nacl.signing import SigningKey
        self._sk = SigningKey.generate()
        self._sk_hex = self._sk.encode().hex()
        self._vk_hex = self._sk.verify_key.encode().hex()

    def _make_entry(self) -> LeaderboardEntry:
        return LeaderboardEntry(
            alias="Jose",
            fingerprint="a1b2c3d4",
            category="max_score",
            value=42.0,
            date="2026-04-01T12:00:00",
        )

    def test_sign_and_verify_ed25519(self) -> None:
        entry = self._make_entry()
        sign_entry(entry, self._sk_hex)
        self.assertTrue(entry.signature)
        self.assertTrue(verify_entry(entry, self._vk_hex))

    def test_tampered_entry_fails(self) -> None:
        entry = self._make_entry()
        sign_entry(entry, self._sk_hex)
        entry.value = 9999
        self.assertFalse(verify_entry(entry, self._vk_hex))

    def test_wrong_key_fails(self) -> None:
        from nacl.signing import SigningKey
        entry = self._make_entry()
        sign_entry(entry, self._sk_hex)
        other_vk = SigningKey.generate().verify_key.encode().hex()
        self.assertFalse(verify_entry(entry, other_vk))

    def test_unsigned_entry_fails(self) -> None:
        entry = self._make_entry()
        self.assertFalse(verify_entry(entry, self._vk_hex))

    def test_empty_verify_key_fails(self) -> None:
        entry = self._make_entry()
        sign_entry(entry, self._sk_hex)
        self.assertFalse(verify_entry(entry, ""))


class TestPlausibility(unittest.TestCase):

    def test_normal_values_pass(self) -> None:
        entry = LeaderboardEntry(
            alias="X", fingerprint="x", category="max_score",
            value=30, date="",
        )
        self.assertTrue(check_plausibility(entry))
        self.assertFalse(entry.is_suspicious)

    def test_impossible_score_flagged(self) -> None:
        entry = LeaderboardEntry(
            alias="X", fingerprint="x", category="max_score",
            value=200, date="",
        )
        self.assertFalse(check_plausibility(entry))
        self.assertTrue(entry.is_suspicious)

    def test_impossible_fastest_win_flagged(self) -> None:
        entry = LeaderboardEntry(
            alias="X", fingerprint="x", category="fastest_win",
            value=3.0, date="",
        )
        self.assertFalse(check_plausibility(entry))
        self.assertTrue(entry.is_suspicious)

    def test_normal_fastest_win_passes(self) -> None:
        entry = LeaderboardEntry(
            alias="X", fingerprint="x", category="fastest_win",
            value=45.0, date="",
        )
        self.assertTrue(check_plausibility(entry))

    def test_impossible_rally_flagged(self) -> None:
        entry = LeaderboardEntry(
            alias="X", fingerprint="x", category="longest_rally",
            value=500, date="",
        )
        self.assertFalse(check_plausibility(entry))
        self.assertTrue(entry.is_suspicious)


class TestGetLocalEntries(unittest.TestCase):

    def test_extracts_from_records(self) -> None:
        from nacl.signing import SigningKey
        sk = SigningKey.generate()
        history = {
            "records": {
                "max_score": {"value": 42, "date": "2026-04-01T12:00:00", "session_index": 0},
                "fastest_win": {"value": 30.5, "date": "2026-03-28T10:00:00", "session_index": 1},
            },
        }
        profile = {
            "alias": "Jose",
            "fingerprint": "abc12345",
            "signing_key": sk.encode().hex(),
            "verify_key": sk.verify_key.encode().hex(),
        }
        entries = get_local_entries(history, profile)
        self.assertEqual(len(entries), 2)
        self.assertTrue(all(e.is_local for e in entries))
        self.assertTrue(all(e.signature for e in entries))
        # Verificar que las firmas son validas
        vk_hex = profile["verify_key"]
        self.assertTrue(all(verify_entry(e, vk_hex) for e in entries))

    def test_empty_profile_returns_empty(self) -> None:
        history = {"records": {"max_score": {"value": 42, "date": "", "session_index": 0}}}
        entries = get_local_entries(history, {})
        self.assertEqual(len(entries), 0)

    def test_no_signing_key_still_works(self) -> None:
        history = {
            "records": {
                "max_score": {"value": 42, "date": "2026-04-01T12:00:00", "session_index": 0},
            },
        }
        profile = {"alias": "Jose", "fingerprint": "abc12345"}
        entries = get_local_entries(history, profile)
        self.assertEqual(len(entries), 1)
        # Sin signing_key, la entry no tiene firma
        self.assertEqual(entries[0].signature, "")


class TestMergeEntries(unittest.TestCase):

    def test_deduplicate_by_fingerprint(self) -> None:
        local = [
            LeaderboardEntry(
                alias="A", fingerprint="fp1", category="max_score",
                value=30, date="2026-04-01", is_local=True,
            ),
        ]
        remote = [
            LeaderboardEntry(
                alias="A", fingerprint="fp1", category="max_score",
                value=25, date="2026-03-28",
            ),
        ]
        result = merge_entries(local, remote)
        # Solo debe haber una entrada para fp1 (la mejor: 30)
        self.assertEqual(len(result["max_score"]), 1)
        self.assertEqual(result["max_score"][0].value, 30)

    def test_sort_descending_for_score(self) -> None:
        entries = [
            LeaderboardEntry(alias="A", fingerprint="fp1", category="max_score", value=10, date=""),
            LeaderboardEntry(alias="B", fingerprint="fp2", category="max_score", value=50, date=""),
        ]
        result = merge_entries(entries, [])
        self.assertEqual(result["max_score"][0].value, 50)

    def test_sort_ascending_for_fastest_win(self) -> None:
        entries = [
            LeaderboardEntry(alias="A", fingerprint="fp1", category="fastest_win", value=60, date=""),
            LeaderboardEntry(alias="B", fingerprint="fp2", category="fastest_win", value=30, date=""),
        ]
        result = merge_entries(entries, [])
        self.assertEqual(result["fastest_win"][0].value, 30)


class TestDisplayAliases(unittest.TestCase):

    def test_unique_aliases_validated_get_b64_suffix(self) -> None:
        entries = [
            LeaderboardEntry(alias="Jose", fingerprint="fp1", category="x", value=1, date=""),
            LeaderboardEntry(alias="Maria", fingerprint="fp2", category="x", value=2, date=""),
        ]
        _assign_display_aliases(entries, p2p_validated=True)
        self.assertEqual(entries[0].display_alias, "Jose-AAAA")
        self.assertEqual(entries[1].display_alias, "Maria-AAAA")

    def test_local_without_validation_gets_question_marks(self) -> None:
        entries = [
            LeaderboardEntry(alias="Jose", fingerprint="fp1", category="x",
                             value=1, date="", is_local=True),
        ]
        _assign_display_aliases(entries, p2p_validated=False)
        self.assertEqual(entries[0].display_alias, "Jose-????")

    def test_local_with_saved_suffix_uses_it(self) -> None:
        entries = [
            LeaderboardEntry(alias="Jose", fingerprint="fp1", category="x",
                             value=1, date="", is_local=True),
        ]
        _assign_display_aliases(entries, p2p_validated=False, saved_suffix="AAAB")
        self.assertEqual(entries[0].display_alias, "Jose-AAAB")

    def test_local_with_validation_gets_b64_suffix(self) -> None:
        entries = [
            LeaderboardEntry(alias="Jose", fingerprint="fp1", category="x",
                             value=1, date="", is_local=True),
        ]
        _assign_display_aliases(entries, p2p_validated=True)
        self.assertEqual(entries[0].display_alias, "Jose-AAAA")

    def test_duplicate_aliases_get_suffix(self) -> None:
        entries = [
            LeaderboardEntry(alias="Jose", fingerprint="fp2", category="x", value=1, date=""),
            LeaderboardEntry(alias="Jose", fingerprint="fp1", category="x", value=2, date=""),
        ]
        _assign_display_aliases(entries, p2p_validated=True)
        # Ordenados por fingerprint: fp1=AAAA, fp2=AAAB
        aliases = sorted([e.display_alias for e in entries])
        self.assertEqual(aliases, ["Jose-AAAA", "Jose-AAAB"])


class TestFormatting(unittest.TestCase):

    def test_format_score(self) -> None:
        entry = LeaderboardEntry(alias="X", fingerprint="x", category="max_score", value=42, date="")
        self.assertEqual(format_entry_value(entry), "42 pts")

    def test_format_fastest_win(self) -> None:
        entry = LeaderboardEntry(alias="X", fingerprint="x", category="fastest_win", value=95, date="")
        self.assertEqual(format_entry_value(entry), "1:35")

    def test_format_date(self) -> None:
        entry = LeaderboardEntry(alias="X", fingerprint="x", category="x", value=0, date="2026-04-01T12:00:00")
        self.assertEqual(format_entry_date(entry), "01/04/2026")

    def test_format_bad_date(self) -> None:
        entry = LeaderboardEntry(alias="X", fingerprint="x", category="x", value=0, date="invalid")
        self.assertEqual(format_entry_date(entry), "\u2014")


class TestEntriesDigest(unittest.TestCase):

    def test_digest_is_order_independent(self) -> None:
        entries_a = [
            LeaderboardEntry(alias="A", fingerprint="fp1", category="max_score", value=10, date="2026-04-01", signature="sig1"),
            LeaderboardEntry(alias="B", fingerprint="fp2", category="max_score", value=20, date="2026-04-02", signature="sig2"),
        ]
        entries_b = list(reversed(entries_a))
        self.assertEqual(compute_entries_digest(entries_a), compute_entries_digest(entries_b))

    def test_digest_changes_when_content_changes_with_same_count(self) -> None:
        base = [
            LeaderboardEntry(alias="A", fingerprint="fp1", category="max_score", value=10, date="2026-04-01", signature="sig1"),
            LeaderboardEntry(alias="B", fingerprint="fp2", category="max_score", value=20, date="2026-04-02", signature="sig2"),
        ]
        changed = [
            LeaderboardEntry(alias="A", fingerprint="fp1", category="max_score", value=11, date="2026-04-01", signature="sig1"),
            LeaderboardEntry(alias="B", fingerprint="fp2", category="max_score", value=20, date="2026-04-03", signature="sig3"),
        ]
        self.assertNotEqual(compute_entries_digest(base), compute_entries_digest(changed))


class TestEntrySerialization(unittest.TestCase):

    def test_roundtrip(self) -> None:
        original = LeaderboardEntry(
            alias="Jose", fingerprint="abc12345",
            category="max_score", value=42.0,
            date="2026-04-01T12:00:00", signature="sig123",
        )
        d = original.to_dict()
        restored = LeaderboardEntry.from_dict(d)
        self.assertEqual(restored.alias, "Jose")
        self.assertEqual(restored.fingerprint, "abc12345")
        self.assertEqual(restored.value, 42.0)
        self.assertEqual(restored.signature, "sig123")


class TestPlayerProfile(unittest.TestCase):

    def test_compute_fingerprint(self) -> None:
        from pong.save_manager import _compute_fingerprint
        verify_key_hex = "ab" * 32
        fp = _compute_fingerprint(verify_key_hex)
        self.assertEqual(len(fp), 16)
        fp2 = _compute_fingerprint(verify_key_hex)
        self.assertEqual(fp, fp2)

    def test_empty_history_has_player_profile(self) -> None:
        from pong.save_manager import _empty_history
        h = _empty_history()
        self.assertIn("player_profile", h)
        self.assertIsInstance(h["player_profile"], dict)
