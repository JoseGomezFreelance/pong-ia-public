"""Definicion de niveles de modelo LLM y logica de recomendacion.

Cinco niveles de calidad creciente (Qwen 2.5 Instruct GGUF Q4_K_M),
con umbrales de RAM/VRAM para clasificar cada nivel como recomendado,
justo o no recomendado segun el hardware del usuario.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pong.config.models import LLMModelConfig
from pong.system_info import SystemInfo

__all__ = [
    "LLMTier",
    "TierRecommendation",
    "TIER_ONNX_FALLBACK",
    "TIER_0_FALLBACK",
    "LLM_TIERS",
    "evaluate_tier",
    "evaluate_all_tiers",
    "best_recommended_tier",
    "tier_to_llm_config",
    "is_onnx_tier_viable",
    "is_onnx_runtime_available",
]


# ============================================================
# Dataclass de nivel
# ============================================================

@dataclass(frozen=True)
class LLMTier:
    """Un nivel de modelo LLM."""

    level: int                   # 1-5
    display_name: str            # "Nivel 1: Qwen 2.5 3B"
    model_size_label: str        # "~2 GB"
    model_size_bytes: int        # Tamano aproximado en bytes
    ram_recommended_gb: float    # Verde: funciona holgadamente
    ram_tight_gb: float          # Amarillo: funciona justo (por debajo = rojo)
    filename: str                # Archivo principal (single o primer split)
    repo_id: str                 # HuggingFace repo (ej: "Qwen/Qwen2.5-3B-Instruct-GGUF")
    gguf_pattern: str            # Patron glob para archivos GGUF del tier
    download_url: str            # URL directa (solo para single-file; "" si split)
    split: bool                  # True si el modelo usa archivos split
    context_window: int
    threads: int                 # Hilos por defecto para este nivel


# ============================================================
# Tier -1: fallback ONNX para CPUs sin AVX2
# ============================================================
# No se incluye en LLM_TIERS — solo se activa si la CPU no
# tiene AVX2 y onnxruntime esta disponible.
# Usa DistilGPT-2 cuantizado INT8 (~84 MB) via ONNX Runtime.

TIER_ONNX_FALLBACK = LLMTier(
    level=-1,
    display_name="Nivel ONNX: DistilGPT-2",
    model_size_label="~87 MB",
    model_size_bytes=87_000_000,
    ram_recommended_gb=2.0,
    ram_tight_gb=1.0,
    filename="model_quantized.onnx",
    repo_id="Xenova/distilgpt2",
    gguf_pattern="",  # No es GGUF
    download_url=(
        "https://huggingface.co/Xenova/distilgpt2/resolve/main/"
        "onnx/model_quantized.onnx?download=true"
    ),
    split=False,
    context_window=512,
    threads=2,
)


# ============================================================
# Tier 0: fallback oculto para hardware muy limitado
# ============================================================
# No se incluye en LLM_TIERS — solo se activa si todos los
# tiers normales estan en rojo o si el tier 1 falla el benchmark.

TIER_0_FALLBACK = LLMTier(
    level=0,
    display_name="Nivel 0: Qwen 2.5 1.5B",
    model_size_label="~1 GB",
    model_size_bytes=1_000_000_000,
    ram_recommended_gb=4.0,
    ram_tight_gb=2.0,
    filename="qwen2.5-1.5b-instruct-q4_k_m.gguf",
    repo_id="Qwen/Qwen2.5-1.5B-Instruct-GGUF",
    gguf_pattern="qwen2.5-1.5b-instruct-q4_k_m*.gguf",
    download_url=(
        "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/"
        "resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf?download=true"
    ),
    split=False,
    context_window=2048,
    threads=2,
)


# ============================================================
# Los 5 niveles principales
# ============================================================

LLM_TIERS: tuple[LLMTier, ...] = (
    LLMTier(
        level=1,
        display_name="Nivel 1: Qwen 2.5 3B",
        model_size_label="~2 GB",
        model_size_bytes=2_000_000_000,
        ram_recommended_gb=8.0,
        ram_tight_gb=4.0,
        filename="qwen2.5-3b-instruct-q4_k_m.gguf",
        repo_id="Qwen/Qwen2.5-3B-Instruct-GGUF",
        gguf_pattern="qwen2.5-3b-instruct-q4_k_m*.gguf",
        download_url=(
            "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/"
            "resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf?download=true"
        ),
        split=False,
        context_window=4096,
        threads=4,
    ),
    LLMTier(
        level=2,
        display_name="Nivel 2: Qwen 2.5 7B",
        model_size_label="~4.4 GB",
        model_size_bytes=4_680_000_000,
        ram_recommended_gb=12.0,
        ram_tight_gb=8.0,
        filename="qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf",
        repo_id="Qwen/Qwen2.5-7B-Instruct-GGUF",
        gguf_pattern="qwen2.5-7b-instruct-q4_k_m*.gguf",
        download_url="",
        split=True,
        context_window=4096,
        threads=4,
    ),
    LLMTier(
        level=3,
        display_name="Nivel 3: Qwen 2.5 14B",
        model_size_label="~9 GB",
        model_size_bytes=8_990_000_000,
        ram_recommended_gb=16.0,
        ram_tight_gb=12.0,
        filename="qwen2.5-14b-instruct-q4_k_m-00001-of-00003.gguf",
        repo_id="Qwen/Qwen2.5-14B-Instruct-GGUF",
        gguf_pattern="qwen2.5-14b-instruct-q4_k_m*.gguf",
        download_url="",
        split=True,
        context_window=8192,
        threads=4,
    ),
    LLMTier(
        level=4,
        display_name="Nivel 4: Qwen 2.5 32B",
        model_size_label="~20 GB",
        model_size_bytes=19_900_000_000,
        ram_recommended_gb=32.0,
        ram_tight_gb=24.0,
        filename="qwen2.5-32b-instruct-q4_k_m-00001-of-00005.gguf",
        repo_id="Qwen/Qwen2.5-32B-Instruct-GGUF",
        gguf_pattern="qwen2.5-32b-instruct-q4_k_m*.gguf",
        download_url="",
        split=True,
        context_window=8192,
        threads=4,
    ),
    LLMTier(
        level=5,
        display_name="Nivel 5: Qwen 2.5 72B",
        model_size_label="~41 GB",
        model_size_bytes=44_000_000_000,
        ram_recommended_gb=64.0,
        ram_tight_gb=48.0,
        filename="qwen2.5-72b-instruct-q4_k_m-00001-of-00012.gguf",
        repo_id="Qwen/Qwen2.5-72B-Instruct-GGUF",
        gguf_pattern="qwen2.5-72b-instruct-q4_k_m*.gguf",
        download_url="",
        split=True,
        context_window=16384,
        threads=4,
    ),
)


# ============================================================
# Recomendacion
# ============================================================

class TierRecommendation(Enum):
    """Resultado de evaluar un nivel contra el hardware."""

    RECOMMENDED = "recommended"              # Verde
    TIGHT = "tight"                          # Amarillo
    NOT_RECOMMENDED = "not_recommended"      # Rojo


# Reserva fija del OS + GPU driver en memoria unificada (Apple Silicon).
# macOS + WindowServer + kernel suelen ocupar ~4-5 GB; usamos 5 GB como
# techo conservador para evitar presion extrema que causa kernel panics.
_UNIFIED_OS_RESERVE_GB: float = 5.0


def _effective_memory_gb(info: SystemInfo) -> float:
    """Memoria efectiva disponible para el modelo LLM.

    En Apple Silicon (memoria unificada) se usa el menor valor entre:
      - RAM disponible real (lo libre ahora mismo)
      - RAM total - reserva fija del OS
    Esto evita ser demasiado optimista (ignorar lo que consume el OS)
    ni demasiado pesimista (penalizar por apps temporales abiertas).
    En CUDA es la VRAM de la GPU.
    En CPU es la RAM total del sistema.
    """
    if info.gpu_type == "cuda" and info.gpu_vram_gb > 0:
        return info.gpu_vram_gb
    if info.unified_memory:
        return max(0.0, info.total_ram_gb - _UNIFIED_OS_RESERVE_GB)
    return info.total_ram_gb


def evaluate_tier(tier: LLMTier, info: SystemInfo) -> TierRecommendation:
    """Evalua un nivel de modelo contra la informacion del sistema."""
    # CPU sin AVX2: llama-cpp-python no puede arrancar
    if not info.has_avx2:
        return TierRecommendation.NOT_RECOMMENDED

    mem = _effective_memory_gb(info)

    # Disco insuficiente: rojo independientemente
    min_disk = tier.model_size_bytes / 1e9 + 1.0
    if info.disk_free_gb < min_disk:
        return TierRecommendation.NOT_RECOMMENDED

    if mem >= tier.ram_recommended_gb:
        return TierRecommendation.RECOMMENDED
    if mem >= tier.ram_tight_gb:
        # En CUDA, si cabe justo en VRAM pero la RAM del sistema es alta,
        # sigue siendo amarillo (no verde) porque la VRAM limita
        return TierRecommendation.TIGHT
    return TierRecommendation.NOT_RECOMMENDED


def evaluate_all_tiers(
    info: SystemInfo,
) -> list[tuple[LLMTier, TierRecommendation]]:
    """Evalua todos los niveles y devuelve lista de (tier, recomendacion)."""
    return [(tier, evaluate_tier(tier, info)) for tier in LLM_TIERS]


def best_recommended_tier(info: SystemInfo) -> LLMTier:
    """Devuelve el nivel verde mas alto; si no hay verde, el amarillo mas alto; si no, nivel 1."""
    evaluations = evaluate_all_tiers(info)

    # Buscar el verde mas alto
    greens = [
        t for t, r in evaluations if r == TierRecommendation.RECOMMENDED
    ]
    if greens:
        return greens[-1]

    # Buscar el amarillo mas alto
    yellows = [
        t for t, r in evaluations if r == TierRecommendation.TIGHT
    ]
    if yellows:
        return yellows[-1]

    # Fallback: nivel 1
    return LLM_TIERS[0]


def tier_to_llm_config(tier: LLMTier) -> LLMModelConfig:
    """Convierte un ``LLMTier`` a ``LLMModelConfig``."""
    return LLMModelConfig(
        filename=tier.filename,
        download_url=tier.download_url,
        context_window=tier.context_window,
        threads=tier.threads,
        display_name=tier.display_name,
    )


# ============================================================
# Funciones helper para Tier ONNX
# ============================================================

def is_onnx_tier_viable(info: SystemInfo) -> bool:
    """True si el fallback ONNX puede funcionar en este hardware.

    Condiciones:
    - CPU sin AVX2 (si tiene AVX2, usa los tiers normales)
    - Al menos 1 GB de RAM
    - Al menos 200 MB de disco libre
    """
    if info.has_avx2:
        return False
    if info.total_ram_gb < 1.0:
        return False
    if info.disk_free_gb < 0.2:
        return False
    return True


def is_onnx_runtime_available() -> bool:
    """True si onnxruntime es importable."""
    try:
        import importlib
        importlib.import_module("onnxruntime")
        return True
    except (ImportError, ModuleNotFoundError):
        return False
