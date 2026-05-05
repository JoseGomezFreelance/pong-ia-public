"""Tokenizador BPE manual para GPT-2 / DistilGPT-2 (Python puro).

Implementa byte-level BPE compatible con el tokenizer de GPT-2 sin
depender de la libreria ``tokenizers`` (~20 MB de Rust bindings).

Los archivos ``vocab.json`` y ``merges.txt`` se descargan del repo de
HuggingFace y se cachean en el directorio de modelos ONNX.

Referencia:
    https://github.com/openai/gpt-2/blob/master/src/encoder.py
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)

__all__ = [
    "BPETokenizer",
    "download_tokenizer_files",
    "TOKENIZER_FILES",
]

# Archivos necesarios para el tokenizer (relativos al directorio del modelo)
TOKENIZER_FILES = ("vocab.json", "merges.txt")

# Repo HuggingFace de donde descargar los archivos del tokenizer
_HF_REPO = "distilbert/distilgpt2"

# Tokens especiales
_EOS_TOKEN = "<|endoftext|>"


# ============================================================
# Tabla byte <-> unicode (GPT-2)
# ============================================================

@lru_cache(maxsize=1)
def _bytes_to_unicode() -> dict[int, str]:
    """Construye la tabla de mapeo byte -> caracter unicode de GPT-2.

    GPT-2 mapea los 256 valores de byte a caracteres unicode
    imprimibles para evitar problemas con caracteres de control.
    """
    # Rangos imprimibles ASCII que se mapean a si mismos
    bs: list[int] = (
        list(range(ord("!"), ord("~") + 1))
        + list(range(ord("¡"), ord("¬") + 1))
        + list(range(ord("®"), ord("ÿ") + 1))
    )
    cs = list(bs)
    n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return dict(zip(bs, [chr(c) for c in cs]))


def _unicode_to_bytes() -> dict[str, int]:
    """Inversa de ``_bytes_to_unicode``."""
    return {v: k for k, v in _bytes_to_unicode().items()}


# ============================================================
# Helpers BPE
# ============================================================

def _get_pairs(word: tuple[str, ...]) -> set[tuple[str, str]]:
    """Devuelve el conjunto de pares de simbolos adyacentes."""
    pairs: set[tuple[str, str]] = set()
    prev = word[0]
    for symbol in word[1:]:
        pairs.add((prev, symbol))
        prev = symbol
    return pairs


# Patron de pre-tokenizacion de GPT-2
_GPT2_PAT = re.compile(
    r"""'s|'t|'re|'ve|'m|'ll|'d| ?\w+| ?\d+| ?[^\s\w\d]+|\s+(?!\S)|\s+""",
)


# ============================================================
# Descarga de archivos del tokenizer
# ============================================================

def _resolve_onnx_dir() -> Path:  # pragma: no cover
    """Devuelve el directorio ``models/onnx/`` escribible."""
    from pong.config.media import _resolve_writable_dir

    return _resolve_writable_dir("models") / "onnx"


def download_tokenizer_files(  # pragma: no cover
    dest_dir: Path | None = None,
    *,
    repo_id: str = _HF_REPO,
) -> Path:
    """Descarga vocab.json y merges.txt al directorio del modelo ONNX.

    Si los archivos ya existen, no los re-descarga.

    Args:
        dest_dir: Directorio destino (default: ``models/onnx/``).
        repo_id: Repo HuggingFace del modelo.

    Returns:
        Directorio donde se guardaron los archivos.
    """
    import ssl
    import urllib.request

    import certifi

    if dest_dir is None:
        dest_dir = _resolve_onnx_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)

    ssl_ctx = ssl.create_default_context(cafile=certifi.where())

    for fname in TOKENIZER_FILES:
        dest_path = dest_dir / fname
        if dest_path.exists() and dest_path.stat().st_size > 0:
            continue
        url = f"https://huggingface.co/{repo_id}/resolve/main/{fname}"
        logger.info("Descargando %s desde %s", fname, repo_id)
        req = urllib.request.Request(url, headers={"User-Agent": "PongIA/1.0"})
        with urllib.request.urlopen(req, timeout=30, context=ssl_ctx) as resp:
            data = resp.read()
        dest_path.write_bytes(data)
        logger.info("Guardado: %s (%d bytes)", dest_path, len(data))

    return dest_dir


# ============================================================
# BPETokenizer
# ============================================================

class BPETokenizer:
    """Tokenizador BPE byte-level compatible con GPT-2 / DistilGPT-2.

    Carga ``vocab.json`` y ``merges.txt`` desde un directorio local.

    Uso tipico::

        tok = BPETokenizer.from_dir(Path("models/onnx"))
        ids = tok.encode("Hola mundo")
        texto = tok.decode(ids)
    """

    def __init__(
        self,
        encoder: dict[str, int],
        bpe_merges: list[tuple[str, str]],
    ) -> None:
        self.encoder = encoder
        self.decoder: dict[int, str] = {v: k for k, v in encoder.items()}
        self.bpe_ranks: dict[tuple[str, str], int] = dict(
            zip(bpe_merges, range(len(bpe_merges)))
        )
        self._byte_encoder = _bytes_to_unicode()
        self._byte_decoder = _unicode_to_bytes()
        self._cache: dict[str, str] = {}

        # Token especial
        self.eos_token_id: int = encoder.get(_EOS_TOKEN, 50256)

    @classmethod
    def from_dir(cls, directory: Path) -> BPETokenizer:
        """Carga el tokenizer desde ``vocab.json`` y ``merges.txt``.

        Args:
            directory: Directorio que contiene ambos archivos.

        Raises:
            FileNotFoundError: Si falta alguno de los archivos.
        """
        vocab_path = directory / "vocab.json"
        merges_path = directory / "merges.txt"

        if not vocab_path.exists():
            raise FileNotFoundError(f"No se encontro: {vocab_path}")
        if not merges_path.exists():
            raise FileNotFoundError(f"No se encontro: {merges_path}")

        with open(vocab_path, encoding="utf-8") as f:
            encoder = json.load(f)

        with open(merges_path, encoding="utf-8") as f:
            lines = f.read().split("\n")

        # merges.txt tiene una cabecera "#version: ..." y lineas vacias
        bpe_merges: list[tuple[str, str]] = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) == 2:
                bpe_merges.append((parts[0], parts[1]))

        return cls(encoder, bpe_merges)

    def _bpe(self, token: str) -> str:
        """Aplica BPE a un token pre-tokenizado."""
        if token in self._cache:
            return self._cache[token]

        word = tuple(token)
        pairs = _get_pairs(word)
        if not pairs:
            return token

        while True:
            # Encontrar el par con menor rank (mayor prioridad)
            bigram = min(pairs, key=lambda pair: self.bpe_ranks.get(pair, float("inf")))
            if bigram not in self.bpe_ranks:
                break

            first, second = bigram
            new_word: list[str] = []
            i = 0
            while i < len(word):
                # Buscar la siguiente ocurrencia de 'first'
                try:
                    j = word.index(first, i)
                except ValueError:
                    new_word.extend(word[i:])
                    break
                new_word.extend(word[i:j])
                i = j

                if i < len(word) - 1 and word[i] == first and word[i + 1] == second:
                    new_word.append(first + second)
                    i += 2
                else:
                    new_word.append(word[i])
                    i += 1

            word = tuple(new_word)
            if len(word) == 1:
                break
            pairs = _get_pairs(word)

        result = " ".join(word)
        self._cache[token] = result
        return result

    def encode(self, text: str) -> list[int]:
        """Codifica texto a una lista de token IDs.

        Args:
            text: Texto en formato string.

        Returns:
            Lista de enteros (token IDs).
        """
        token_ids: list[int] = []
        for match in _GPT2_PAT.finditer(text):
            # Convertir cada byte del texto a su caracter unicode GPT-2
            token = "".join(
                self._byte_encoder[b] for b in match.group(0).encode("utf-8")
            )
            # Aplicar BPE y mapear subwords al vocabulario
            bpe_tokens = self._bpe(token).split(" ")
            for bpe_token in bpe_tokens:
                if bpe_token in self.encoder:
                    token_ids.append(self.encoder[bpe_token])
            # Si un subword no esta en el vocabulario, se ignora
            # (esto no deberia pasar con vocab.json completo)
        return token_ids

    def decode(self, token_ids: Sequence[int]) -> str:
        """Decodifica una secuencia de token IDs a texto.

        Args:
            token_ids: Secuencia de enteros (token IDs).

        Returns:
            Texto decodificado.
        """
        # Unir los tokens en texto unicode GPT-2
        text = "".join(self.decoder.get(tid, "") for tid in token_ids)
        # Convertir caracteres unicode GPT-2 de vuelta a bytes
        byte_list = bytearray(
            self._byte_decoder[c] for c in text if c in self._byte_decoder
        )
        return byte_list.decode("utf-8", errors="replace")

    @property
    def vocab_size(self) -> int:
        """Numero de tokens en el vocabulario."""
        return len(self.encoder)
