"""Proveedor LLM via ONNX Runtime para CPUs sin AVX2 (Tier -1).

Usa DistilGPT-2 cuantizado INT8 con onnxruntime como backend.
No requiere AVX2 — ONNX Runtime opera con SSE2 como baseline.

DistilGPT-2 es un modelo causal (no chat), asi que los mensajes
system/user se aplanan a texto plano antes de generar.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

__all__ = ["OnnxLLMProvider"]

# Directorio del modelo ONNX relativo a models/
_ONNX_MODEL_DIR = "onnx"
_ONNX_MODEL_FILE = "model_quantized.onnx"

# Tokens especiales de GPT-2
_EOS_TOKEN_ID = 50256


def _resolve_onnx_model_path() -> Path:
    """Busca el directorio del modelo ONNX en las ubicaciones conocidas."""
    from pong.providers import resolve_model_path

    # resolve_model_path espera un archivo, le pasamos el .onnx
    return resolve_model_path(
        Path("models") / _ONNX_MODEL_DIR / _ONNX_MODEL_FILE
    )


def _disable_ort_telemetry() -> None:
    """Desactiva telemetria de onnxruntime en Windows."""
    if sys.platform != "win32":
        return
    try:
        import onnxruntime as ort
        if hasattr(ort, "disable_telemetry_events"):
            ort.disable_telemetry_events()
    except Exception:
        pass


def _flatten_messages(messages: list[dict[str, str]]) -> str:
    """Convierte mensajes chat a texto plano para un modelo causal.

    DistilGPT-2 no entiende roles chat (system/user/assistant), asi
    que aplanamos los mensajes a un prompt de texto simple.
    """
    parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "").strip()
        if not content:
            continue
        if role == "system":
            parts.append(content)
        elif role == "user":
            parts.append(content)
        elif role == "assistant":
            parts.append(content)
        else:
            parts.append(content)

    return "\n".join(parts) + "\n"


class OnnxLLMProvider:
    """Proveedor LLM usando ONNX Runtime + DistilGPT-2 cuantizado.

    Implementa ``LLMProviderProtocol`` para ser usado como fallback
    en CPUs sin soporte AVX2.
    """

    def __init__(self) -> None:
        self._enabled: bool = False
        self._status_message: str = (
            "Narrador IA ONNX no disponible. Descarga el modelo desde "
            "la pantalla de instalacion."
        )
        self._session: Any = None  # ort.InferenceSession
        self._tokenizer: Any = None  # BPETokenizer
        self._load()

    def _load(self) -> None:
        """Intenta cargar el modelo ONNX y el tokenizer."""
        model_path = _resolve_onnx_model_path()
        if not model_path.exists():
            return

        tokenizer_dir = model_path.parent

        # Verificar archivos del tokenizer
        from pong.bpe_tokenizer import TOKENIZER_FILES
        for fname in TOKENIZER_FILES:
            if not (tokenizer_dir / fname).exists():
                self._status_message = (
                    f"Narrador IA ONNX: falta {fname} en {tokenizer_dir}"
                )
                return

        try:
            import onnxruntime as ort

            _disable_ort_telemetry()

            # Sesion ONNX con CPUExecutionProvider
            sess_options = ort.SessionOptions()
            sess_options.inter_op_num_threads = 1
            sess_options.intra_op_num_threads = 2
            sess_options.graph_optimization_level = (
                ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            )

            self._session = ort.InferenceSession(
                str(model_path),
                sess_options,
                providers=["CPUExecutionProvider"],
            )

            from pong.bpe_tokenizer import BPETokenizer
            self._tokenizer = BPETokenizer.from_dir(tokenizer_dir)

            self._enabled = True
            self._status_message = "Narrador IA activo: DistilGPT-2 ONNX (modo compatibilidad)"

        except ImportError:
            self._status_message = (
                "Error al cargar IA ONNX: falta el modulo 'onnxruntime'. "
                "Instala con: pip install onnxruntime"
            )
        except Exception as exc:
            self._status_message = f"Error al cargar IA ONNX: {exc}"

    def reload(self) -> None:
        """Recarga el modelo ONNX (tras descarga)."""
        if not self._enabled:
            self._session = None
            self._tokenizer = None
            self._load()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def status_message(self) -> str:
        return self._status_message

    def _generate(
        self,
        input_ids: list[int],
        max_tokens: int = 64,
        temperature: float = 0.85,
        top_p: float = 0.92,
        repeat_penalty: float = 1.18,
    ) -> list[int]:
        """Loop autorregresivo: genera tokens uno a uno.

        Args:
            input_ids: Token IDs del prompt.
            max_tokens: Maximo de tokens a generar.
            temperature: Temperatura de muestreo.
            top_p: Nucleus sampling (top-p).
            repeat_penalty: Penalizacion por repeticion.

        Returns:
            Lista de token IDs generados (sin el prompt).
        """
        generated: list[int] = []
        current_ids = list(input_ids)

        # DistilGPT-2 tiene contexto de 1024 tokens
        max_context = 1024

        for _ in range(max_tokens):
            # Truncar al contexto maximo (mantener los ultimos tokens)
            if len(current_ids) > max_context:
                current_ids = current_ids[-max_context:]

            # Preparar inputs para ONNX
            ids_array = np.array([current_ids], dtype=np.int64)
            attention_mask = np.ones_like(ids_array, dtype=np.int64)

            outputs = self._session.run(
                None,
                {
                    "input_ids": ids_array,
                    "attention_mask": attention_mask,
                },
            )

            # outputs[0] shape: (1, seq_len, vocab_size)
            logits = outputs[0][0, -1, :]  # Logits del ultimo token

            # Aplicar penalizacion por repeticion
            if repeat_penalty != 1.0:
                for token_id in set(current_ids + generated):
                    if token_id < len(logits):
                        if logits[token_id] > 0:
                            logits[token_id] /= repeat_penalty
                        else:
                            logits[token_id] *= repeat_penalty

            # Temperature scaling
            if temperature > 0:
                logits = logits / temperature
            else:
                # Greedy: tomar el argmax directamente
                next_token = int(np.argmax(logits))
                if next_token == _EOS_TOKEN_ID:
                    break
                generated.append(next_token)
                current_ids.append(next_token)
                continue

            # Top-p (nucleus) sampling
            sorted_indices = np.argsort(logits)[::-1]
            sorted_logits = logits[sorted_indices]

            # Softmax estable
            max_logit = sorted_logits[0]
            exp_logits = np.exp(sorted_logits - max_logit)
            probs = exp_logits / exp_logits.sum()

            cumulative_probs = np.cumsum(probs)
            # Encontrar el corte de top-p
            cutoff_idx = int(np.searchsorted(cumulative_probs, top_p)) + 1
            cutoff_idx = min(cutoff_idx, len(probs))

            # Filtrar y re-normalizar
            top_indices = sorted_indices[:cutoff_idx]
            top_probs = probs[:cutoff_idx]
            top_probs = top_probs / top_probs.sum()

            # Muestrear
            next_token = int(np.random.choice(top_indices, p=top_probs))

            if next_token == _EOS_TOKEN_ID:
                break

            generated.append(next_token)
            current_ids.append(next_token)

        return generated

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 64,
        temperature: float = 0.85,
        top_p: float = 0.92,
        repeat_penalty: float = 1.18,
        frequency_penalty: float = 0.0,
        stream: bool = False,
    ) -> Any:
        """Genera texto usando DistilGPT-2 via ONNX Runtime.

        Devuelve el mismo formato que llama-cpp-python para
        compatibilidad con el narrador::

            {"choices": [{"message": {"content": "texto generado"}}]}
        """
        prompt = _flatten_messages(messages)
        input_ids = self._tokenizer.encode(prompt)

        # Limitar prompt para dejar espacio a la generacion
        max_prompt = 1024 - max_tokens
        if len(input_ids) > max_prompt:
            input_ids = input_ids[-max_prompt:]

        generated_ids = self._generate(
            input_ids,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            repeat_penalty=repeat_penalty,
        )

        content = self._tokenizer.decode(generated_ids).strip()

        return {"choices": [{"message": {"content": content}}]}
