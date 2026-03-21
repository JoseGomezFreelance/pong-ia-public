"""Configuracion de modelos de IA (LLM e imagen) via models.toml.

Lee el archivo ``models.toml`` de la raiz del proyecto para permitir al
usuario elegir que modelo LLM y que pipeline de imagen usar sin tocar codigo.

Si ``models.toml`` no existe, se usan los valores por defecto que reproducen
el comportamiento original del juego (Qwen 2.5 3B + Juggernaut Reborn).
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "LLMModelConfig",
    "LoRAConfig",
    "ImageModelConfig",
    "load_models_config",
]


# ============================================================
# Dataclasses de configuracion
# ============================================================

@dataclass(frozen=True)
class LLMModelConfig:
    """Configuracion del modelo LLM local (archivo GGUF)."""

    filename: str = "qwen2.5-3b-instruct-q4_k_m.gguf"
    download_url: str = (
        "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/"
        "resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf?download=true"
    )
    context_window: int = 4096
    threads: int = 4
    display_name: str = ""

    @property
    def resolved_display_name(self) -> str:
        """Nombre para mostrar en la UI; si no se especifica, usa el filename."""
        return self.display_name or Path(self.filename).stem


@dataclass(frozen=True)
class LoRAConfig:
    """Configuracion de un LoRA para el pipeline de imagen."""

    id: str
    source: str = "huggingface"   # "huggingface", "civitai", "local"
    weight: float = 1.0


@dataclass(frozen=True)
class ImageModelConfig:
    """Configuracion del pipeline de generacion de imagenes."""

    pipeline: str = "sd15"            # "sd15" o "sdxl"
    model_id: str = "stablediffusionapi/juggernaut-reborn"
    loras: tuple[LoRAConfig, ...] = (
        LoRAConfig(id="latent-consistency/lcm-lora-sdv1-5", source="huggingface"),
    )
    scheduler_type: str = "lcm"       # "lcm", "euler", "euler_a", "dpm", "default"
    steps: int = 4
    guidance_scale: float = 1.5
    width: int = 512
    height: int = 512


# ============================================================
# Parseo de models.toml
# ============================================================

def _load_toml(path: Path) -> dict[str, Any]:
    """Carga un archivo TOML usando tomllib (3.11+) o tomli (fallback)."""
    if sys.version_info >= (3, 11):
        import tomllib
    else:
        try:
            import tomli as tomllib  # type: ignore[no-redef,unused-ignore]
        except ImportError:
            logger.warning(
                "Python < 3.11 y 'tomli' no instalado; no se puede leer models.toml. "
                "Instala tomli con: pip install tomli"
            )
            return {}

    with open(path, "rb") as f:
        result: dict[str, Any] = tomllib.load(f)
        return result


def _parse_llm(data: dict[str, Any]) -> LLMModelConfig:
    """Construye LLMModelConfig desde la seccion [llm] del TOML."""
    return LLMModelConfig(
        filename=str(data.get("filename", LLMModelConfig.filename)),
        download_url=str(data.get("download_url", LLMModelConfig.download_url)),
        context_window=int(data.get("context_window", LLMModelConfig.context_window)),
        threads=int(data.get("threads", LLMModelConfig.threads)),
        display_name=str(data.get("display_name", "")),
    )


def _parse_image(data: dict[str, Any]) -> ImageModelConfig:
    """Construye ImageModelConfig desde la seccion [image] del TOML."""
    loras_raw = data.get("loras", [])
    loras: list[LoRAConfig] = []
    for lora_data in loras_raw:
        loras.append(
            LoRAConfig(
                id=str(lora_data["id"]),
                source=str(lora_data.get("source", "huggingface")),
                weight=float(lora_data.get("weight", 1.0)),
            )
        )
    # Si no se especifican LoRAs, usar el default
    if not loras and "loras" not in data:
        loras_tuple = ImageModelConfig.loras
    else:
        loras_tuple = tuple(loras)

    scheduler_type = str(
        data.get("scheduler", {}).get("type", "")
        or data.get("scheduler_type", ImageModelConfig.scheduler_type)
    )

    return ImageModelConfig(
        pipeline=str(data.get("pipeline", ImageModelConfig.pipeline)),
        model_id=str(data.get("model_id", ImageModelConfig.model_id)),
        loras=loras_tuple,
        scheduler_type=scheduler_type,
        steps=int(data.get("steps", ImageModelConfig.steps)),
        guidance_scale=float(data.get("guidance_scale", ImageModelConfig.guidance_scale)),
        width=int(data.get("width", ImageModelConfig.width)),
        height=int(data.get("height", ImageModelConfig.height)),
    )


def load_models_config(
    toml_path: Path | None = None,
) -> tuple[LLMModelConfig, ImageModelConfig]:
    """Lee models.toml y devuelve la configuracion de LLM e imagen.

    Si el archivo no existe o no se puede leer, devuelve los defaults.

    Args:
        toml_path: Ruta al archivo models.toml.  Si es ``None``, busca en la
                   raiz del proyecto (dos niveles arriba de este archivo).

    Returns:
        Tupla ``(LLMModelConfig, ImageModelConfig)``.
    """
    if toml_path is None:
        if getattr(sys, "frozen", False):
            # Ejecutable empaquetado: buscar junto al .app/.exe
            exe_dir = Path(sys.executable).resolve().parent
            if exe_dir.name == "MacOS" and exe_dir.parent.name == "Contents":
                toml_path = exe_dir.parent.parent.parent / "models.toml"
            else:
                toml_path = exe_dir / "models.toml"
        else:
            # Desarrollo: __file__ -> pong/config/models.py => raiz
            toml_path = Path(__file__).resolve().parent.parent.parent / "models.toml"

    llm_config = LLMModelConfig()
    image_config = ImageModelConfig()

    if not toml_path.exists():
        return llm_config, image_config

    try:
        raw = _load_toml(toml_path)
    except Exception as exc:
        logger.warning("Error leyendo %s: %s", toml_path, exc)
        return llm_config, image_config

    if "llm" in raw:
        llm_config = _parse_llm(raw["llm"])
    if "image" in raw:
        image_config = _parse_image(raw["image"])

    return llm_config, image_config
