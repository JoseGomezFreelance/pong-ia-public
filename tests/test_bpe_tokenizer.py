"""Tests para pong/bpe_tokenizer.py — tokenizador BPE manual.

Verifica:
- Tabla byte <-> unicode de GPT-2
- Pre-tokenizacion con regex GPT-2
- Construccion desde vocab.json + merges.txt
- Encode/decode roundtrip
- Tokens especiales (EOS)
- Manejo de errores (archivos faltantes)
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pong.bpe_tokenizer import (
    TOKENIZER_FILES,
    BPETokenizer,
    _GPT2_PAT,
    _bytes_to_unicode,
    _get_pairs,
    _unicode_to_bytes,
)


# ============================================================
# Tabla byte <-> unicode
# ============================================================


class TestBytesUnicode(unittest.TestCase):

    def test_256_entries(self) -> None:
        """La tabla debe mapear los 256 valores de byte."""
        table = _bytes_to_unicode()
        self.assertEqual(len(table), 256)

    def test_all_bytes_covered(self) -> None:
        table = _bytes_to_unicode()
        for b in range(256):
            self.assertIn(b, table)

    def test_printable_ascii_maps_to_self(self) -> None:
        """Caracteres ASCII imprimibles se mapean a si mismos."""
        table = _bytes_to_unicode()
        for b in range(ord("!"), ord("~") + 1):
            self.assertEqual(table[b], chr(b))

    def test_roundtrip(self) -> None:
        """byte -> unicode -> byte es identidad."""
        b2u = _bytes_to_unicode()
        u2b = _unicode_to_bytes()
        for byte_val, uni_char in b2u.items():
            self.assertEqual(u2b[uni_char], byte_val)

    def test_unique_unicode_chars(self) -> None:
        """Todos los caracteres unicode son unicos."""
        table = _bytes_to_unicode()
        values = list(table.values())
        self.assertEqual(len(values), len(set(values)))


# ============================================================
# Helpers BPE
# ============================================================


class TestGetPairs(unittest.TestCase):

    def test_basic_pairs(self) -> None:
        word = ("a", "b", "c")
        self.assertEqual(_get_pairs(word), {("a", "b"), ("b", "c")})

    def test_single_char(self) -> None:
        word = ("a",)
        self.assertEqual(_get_pairs(word), set())

    def test_two_chars(self) -> None:
        word = ("x", "y")
        self.assertEqual(_get_pairs(word), {("x", "y")})


# ============================================================
# Regex GPT-2
# ============================================================


class TestGPT2Regex(unittest.TestCase):

    def test_splits_words(self) -> None:
        tokens = _GPT2_PAT.findall("Hello world")
        self.assertEqual(tokens, ["Hello", " world"])

    def test_contractions(self) -> None:
        tokens = _GPT2_PAT.findall("I'm don't")
        self.assertIn("'m", tokens)
        self.assertIn("'t", tokens)

    def test_numbers(self) -> None:
        tokens = _GPT2_PAT.findall("test 123 abc")
        self.assertIn(" 123", tokens)

    def test_punctuation(self) -> None:
        tokens = _GPT2_PAT.findall("Hello!")
        self.assertIn("!", tokens)


# ============================================================
# Mini tokenizer de prueba
# ============================================================

def _make_mini_tokenizer(tmp_dir: Path) -> BPETokenizer:
    """Crea un tokenizer minimo con vocabulario reducido para tests.

    Solo contiene tokens para "hello" y " world" en formato GPT-2.
    """
    b2u = _bytes_to_unicode()

    # Tokens individuales: todos los bytes como caracteres unicode
    vocab: dict[str, int] = {}
    idx = 0
    for byte_val in range(256):
        vocab[b2u[byte_val]] = idx
        idx += 1

    # Merges para "he", "ll", "lo", "hel", "hell", "hello"
    merges = [
        (b2u[ord("h")], b2u[ord("e")]),  # h + e -> he
        (b2u[ord("l")], b2u[ord("l")]),  # l + l -> ll
        (b2u[ord("h")] + b2u[ord("e")], b2u[ord("l")]),  # he + l -> hel
        (b2u[ord("h")] + b2u[ord("e")] + b2u[ord("l")], b2u[ord("l")] + b2u[ord("l")]),  # hel + ll -> helll? No...
    ]
    # Agregar tokens de merge al vocab
    for first, second in merges:
        merged = first + second
        if merged not in vocab:
            vocab[merged] = idx
            idx += 1

    # EOS token
    vocab["<|endoftext|>"] = idx

    # Escribir archivos
    vocab_path = tmp_dir / "vocab.json"
    merges_path = tmp_dir / "merges.txt"

    with open(vocab_path, "w", encoding="utf-8") as f:
        json.dump(vocab, f, ensure_ascii=False)

    with open(merges_path, "w", encoding="utf-8") as f:
        f.write("#version: 0.2\n")
        for first, second in merges:
            f.write(f"{first} {second}\n")

    return BPETokenizer.from_dir(tmp_dir)


# ============================================================
# BPETokenizer — construccion
# ============================================================


class TestTokenizerConstruction(unittest.TestCase):

    def test_from_dir_missing_vocab(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "merges.txt").write_text("#version: 0.2\n")
            with self.assertRaises(FileNotFoundError):
                BPETokenizer.from_dir(tmp_path)

    def test_from_dir_missing_merges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "vocab.json").write_text("{}")
            with self.assertRaises(FileNotFoundError):
                BPETokenizer.from_dir(tmp_path)

    def test_mini_tokenizer_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tok = _make_mini_tokenizer(Path(tmp))
            self.assertGreater(tok.vocab_size, 256)
            self.assertIsInstance(tok.eos_token_id, int)

    def test_empty_merges(self) -> None:
        """Tokenizer con vocab pero sin merges funciona (no fusiona nada)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            b2u = _bytes_to_unicode()
            vocab = {b2u[b]: b for b in range(256)}
            vocab["<|endoftext|>"] = 256

            (tmp_path / "vocab.json").write_text(
                json.dumps(vocab, ensure_ascii=False)
            )
            (tmp_path / "merges.txt").write_text("#version: 0.2\n")

            tok = BPETokenizer.from_dir(tmp_path)
            # Sin merges, cada byte es un token separado
            ids = tok.encode("hi")
            self.assertEqual(len(ids), 2)


# ============================================================
# BPETokenizer — encode/decode
# ============================================================


class TestTokenizerEncodeDecode(unittest.TestCase):

    def test_encode_returns_ints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tok = _make_mini_tokenizer(Path(tmp))
            ids = tok.encode("hello")
            self.assertIsInstance(ids, list)
            self.assertTrue(all(isinstance(i, int) for i in ids))

    def test_decode_returns_str(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tok = _make_mini_tokenizer(Path(tmp))
            ids = tok.encode("test")
            text = tok.decode(ids)
            self.assertIsInstance(text, str)

    def test_roundtrip_ascii(self) -> None:
        """encode -> decode es identidad para ASCII simple."""
        with tempfile.TemporaryDirectory() as tmp:
            tok = _make_mini_tokenizer(Path(tmp))
            for text in ("a", "hello", "test 123"):
                ids = tok.encode(text)
                decoded = tok.decode(ids)
                self.assertEqual(decoded, text, f"Roundtrip fallo para: {text!r}")

    def test_empty_string(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tok = _make_mini_tokenizer(Path(tmp))
            self.assertEqual(tok.encode(""), [])
            self.assertEqual(tok.decode([]), "")

    def test_decode_unknown_id(self) -> None:
        """IDs no reconocidos se ignoran silenciosamente."""
        with tempfile.TemporaryDirectory() as tmp:
            tok = _make_mini_tokenizer(Path(tmp))
            result = tok.decode([999999])
            self.assertEqual(result, "")


# ============================================================
# BPETokenizer — propiedades
# ============================================================


class TestTokenizerProperties(unittest.TestCase):

    def test_vocab_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tok = _make_mini_tokenizer(Path(tmp))
            self.assertEqual(tok.vocab_size, len(tok.encoder))

    def test_eos_token_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tok = _make_mini_tokenizer(Path(tmp))
            self.assertIn(tok.eos_token_id, tok.decoder)


# ============================================================
# TOKENIZER_FILES constante
# ============================================================


class TestTokenizerFiles(unittest.TestCase):

    def test_contains_expected_files(self) -> None:
        self.assertIn("vocab.json", TOKENIZER_FILES)
        self.assertIn("merges.txt", TOKENIZER_FILES)

    def test_exactly_two(self) -> None:
        self.assertEqual(len(TOKENIZER_FILES), 2)


if __name__ == "__main__":
    unittest.main()
