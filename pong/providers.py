"""
pong/providers.py -- Protocols y providers para inferencia de IA.

Define los contratos (Protocols) para proveedores de LLM e imagen,
la implementacion built-in (LocalLLMProvider), y las funciones de
descubrimiento de plugins via entry_points de setuptools.

Un plugin externo puede registrar su propio provider en pyproject.toml:

    [project.entry-points."pong_ia.llm"]
    mi_provider = "mi_paquete:MiLLMProvider"

Y activarlo con la variable de entorno:

    PONG_IA_LLM_PROVIDER=mi_provider python main.py
"""

from __future__ import annotations

import importlib
import importlib.metadata
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Protocol, runtime_checkable

if TYPE_CHECKING:
    import pygame

    from pong.config.models import ImageModelConfig, LLMModelConfig
    from pong.perf import PerformanceMetrics

logger = logging.getLogger(__name__)


# ============================================================
# Protocols
# ============================================================

@runtime_checkable
class LLMProviderProtocol(Protocol):
    """Contrato para un backend de inferencia LLM."""

    @property
    def enabled(self) -> bool: ...

    @property
    def status_message(self) -> str: ...

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 64,
        temperature: float = 0.85,
        top_p: float = 0.92,
        repeat_penalty: float = 1.18,
        frequency_penalty: float = 0.0,
        stream: bool = False,
    ) -> Any: ...


@runtime_checkable
class ImageGenProviderProtocol(Protocol):
    """Contrato para un backend de generacion de imagenes."""

    @property
    def state(self) -> str: ...

    @property
    def is_ready(self) -> bool: ...

    def set_perf(self, perf: PerformanceMetrics) -> None: ...

    def set_log_fn(self, fn: Callable[[str, str], None]) -> None: ...

    def activate(self) -> None: ...

    def request(self, prompt: str, negative_prompt: str = "") -> None: ...

    def consume(self) -> pygame.Surface | None: ...

    def shutdown(self) -> None: ...


# ============================================================
# Resolucion de ruta del modelo LLM
# ============================================================

def resolve_model_path(model_relative_path: Path) -> Path:
    """
    Busca el archivo del modelo LLM en varias ubicaciones posibles.

    El modelo puede estar en distintos sitios segun como ejecutes el juego:
    - En desarrollo: en la carpeta models/ del proyecto.
    - Empaquetado como .app/.exe: junto al ejecutable.
    - Con variable de entorno: donde tu le digas.

    Args:
        model_relative_path: Ruta relativa al modelo (ej: ``models/qwen.gguf``).

    Returns:
        Path al archivo del modelo (.gguf).
    """
    candidates: list[Path] = []

    # 1. Variable de entorno (maxima prioridad)
    env_model_path = os.getenv("PONG_IA_MODEL_PATH")
    if env_model_path:
        candidates.append(Path(env_model_path).expanduser())

    # 2. Relativo a la raiz del proyecto (pong/ -> ../)
    source_dir = Path(__file__).resolve().parent.parent
    candidates.append(source_dir / model_relative_path)

    # 3. Relativo al directorio de trabajo actual
    candidates.append(Path.cwd() / model_relative_path)

    # 4. Para binarios empaquetados con PyInstaller
    if getattr(sys, "frozen", False):
        # Application Support (ubicacion canonica para datos del usuario)
        if sys.platform == "darwin":
            app_support = Path.home() / "Library" / "Application Support" / "PongIA"
        else:
            app_support = Path(os.environ.get("APPDATA", Path.home())) / "PongIA"
        candidates.append(app_support / model_relative_path)

        executable_dir = Path(sys.executable).resolve().parent
        candidates.append(executable_dir / model_relative_path)
        candidates.append(executable_dir.parent / model_relative_path)

        # 5. Dentro de un .app de macOS (estructura Contents/MacOS/)
        if (
            executable_dir.name == "MacOS"
            and executable_dir.parent.name == "Contents"
        ):
            app_bundle = executable_dir.parent.parent
            candidates.append(app_bundle / model_relative_path)
            candidates.append(app_bundle.parent / model_relative_path)

    # 6. Directorio temporal de PyInstaller (_MEIPASS)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / model_relative_path)

    # Eliminar duplicados manteniendo el orden de prioridad
    ordered: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            ordered.append(candidate)
            seen.add(key)

    for candidate in ordered:
        if candidate.exists():
            return candidate

    return ordered[0]


def _detect_gpu_layers() -> int:
    """Detecta cuantas capas offloadear a GPU para llama-cpp.

    Returns:
        0 para CPU, -1 para MPS (Apple Silicon) o CUDA (todas las capas).

    En Apple Silicon la memoria es unificada (GPU = RAM total), por lo que
    se offloadean todas las capas a Metal igual que en CUDA.
    """
    try:
        import torch
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return -1
        if torch.cuda.is_available():
            return -1
    except Exception:
        pass
    return 0


# ============================================================
# LocalLLMProvider — implementacion built-in con llama-cpp
# ============================================================

class LocalLLMProvider:
    """Proveedor LLM local usando llama-cpp-python con archivos GGUF.

    Esta clase encapsula la carga del modelo y la llamada a
    ``create_chat_completion``, separando la inferencia pura de la
    logica de narracion.
    """

    def __init__(self, config: LLMModelConfig | None = None) -> None:
        from pong.config.models import LLMModelConfig

        if config is None:
            config = LLMModelConfig()

        self._config = config
        self._enabled: bool = False
        self._status_message: str = (
            "Narrador IA no disponible. Coloca el modelo en models/ o ejecuta "
            "scripts/bootstrap_local_model.sh"
        )
        self._model: Any = None
        self._load_model()

    def _load_model(self) -> None:
        """Intenta cargar el modelo LLM desde disco."""
        # Safety net: no intentar cargar llama_cpp si la CPU no tiene AVX2
        # (evita SIGILL en CPUs pre-Haswell)
        try:
            from pong.system_info import detect_system_info
            info = detect_system_info()
            if not info.has_avx2:
                self._enabled = False
                self._status_message = (
                    "Narrador IA no disponible: CPU sin soporte AVX2"
                )
                return
        except Exception:
            pass  # Si falla la deteccion, intentar cargar igualmente

        model_relative_path = Path("models") / self._config.filename
        model_path = resolve_model_path(model_relative_path)

        if not model_path.exists():
            return

        try:
            llama_cpp = importlib.import_module("llama_cpp")
            n_gpu_layers = _detect_gpu_layers()
            self._model = llama_cpp.Llama(
                model_path=str(model_path),
                n_ctx=self._config.context_window,
                n_threads=self._config.threads,
                n_gpu_layers=n_gpu_layers,
                verbose=False,
            )
            self._enabled = True
            display = self._config.resolved_display_name
            self._status_message = f"Narrador IA activo: {display}"
        except ModuleNotFoundError:
            self._enabled = False
            self._status_message = (
                "Error al cargar IA local: falta el modulo 'llama_cpp'. "
                "Instala dependencias en el mismo interprete de VSCode con: "
                "python -m pip install -r requirements.txt"
            )
        except Exception as exc:
            self._enabled = False
            self._status_message = f"Error al cargar IA local: {exc}"

    def reload(self) -> None:
        """Recarga el modelo LLM (tras descarga o cambio de modelo).

        Lee la configuracion actualizada de models.toml para detectar
        cambios de modelo.
        """
        from pong.config.models import load_models_config

        new_config, _ = load_models_config()
        config_changed = new_config.filename != self._config.filename
        if config_changed:
            self._config = new_config
            self._model = None
            self._enabled = False

        if not self._enabled:
            self._load_model()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def status_message(self) -> str:
        return self._status_message

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
        """Delega a llama_cpp.Llama.create_chat_completion()."""
        return self._model.create_chat_completion(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            repeat_penalty=repeat_penalty,
            frequency_penalty=frequency_penalty,
            stream=stream,
        )


# ============================================================
# Descubrimiento de plugins via entry_points
# ============================================================

def _load_entry_point(group: str, name: str) -> Any:
    """Busca y carga un entry_point por grupo y nombre.

    Returns:
        La clase del provider (sin instanciar), o None si no se encuentra.
    """
    try:
        eps = importlib.metadata.entry_points()
        # Python 3.12+ devuelve SelectableGroups, 3.10-3.11 devuelve dict
        if isinstance(eps, dict):
            group_eps: Any = eps.get(group, [])
        else:
            group_eps = eps.select(group=group, name=name)  # type: ignore[union-attr,unused-ignore]

        for ep in group_eps:
            if ep.name == name:
                return ep.load()
    except Exception as exc:
        logger.debug("entry_points lookup failed for %s:%s: %s", group, name, exc)

    return None


def _try_onnx_provider() -> LLMProviderProtocol:
    """Intenta cargar OnnxLLMProvider como fallback para CPUs sin AVX2.

    Returns:
        OnnxLLMProvider si onnxruntime esta disponible, o un
        LocalLLMProvider disabled si no lo esta.
    """
    try:
        from pong.onnx_provider import OnnxLLMProvider
        return OnnxLLMProvider()
    except Exception as exc:
        logger.debug("No se pudo cargar OnnxLLMProvider: %s", exc)
        return LocalLLMProvider()


def load_llm_provider(config: LLMModelConfig | None = None) -> LLMProviderProtocol:
    """Carga el proveedor de LLM configurado.

    Orden de resolucion:
    1. Variable ``PONG_IA_LLM_PROVIDER`` → busca en entry_points ``pong_ia.llm``.
    2. Si la CPU no tiene AVX2, intenta ``OnnxLLMProvider``.
    3. Fallback: ``LocalLLMProvider``.

    Args:
        config: ``LLMModelConfig`` opcional.  Si es ``None`` se usan defaults.

    Returns:
        Instancia que cumple ``LLMProviderProtocol``.
    """
    name = os.environ.get("PONG_IA_LLM_PROVIDER", "")

    if name and name != "local":
        provider_cls = _load_entry_point("pong_ia.llm", name)
        if provider_cls is not None:
            return provider_cls(config)  # type: ignore[no-any-return]
        logger.warning(
            "Proveedor LLM '%s' no encontrado en entry_points. "
            "Usando LocalLLMProvider.",
            name,
        )

    # Si la CPU no tiene AVX2, intentar ONNX provider
    try:
        from pong.system_info import detect_system_info
        info = detect_system_info()
        if not info.has_avx2:
            return _try_onnx_provider()
    except Exception:
        pass

    return LocalLLMProvider(config)


def load_imagegen_provider(config: ImageModelConfig | None = None) -> ImageGenProviderProtocol:
    """Carga el proveedor de generacion de imagenes configurado.

    Orden de resolucion:
    1. Variable ``PONG_IA_IMAGEGEN_PROVIDER`` → entry_points ``pong_ia.imagegen``.
    2. Fallback: ``ImageGenerator`` built-in.

    Args:
        config: ``ImageModelConfig`` opcional.

    Returns:
        Instancia que cumple ``ImageGenProviderProtocol``.
    """
    name = os.environ.get("PONG_IA_IMAGEGEN_PROVIDER", "")

    if name and name != "local":
        provider_cls = _load_entry_point("pong_ia.imagegen", name)
        if provider_cls is not None:
            return provider_cls(config)  # type: ignore[no-any-return]
        logger.warning(
            "Proveedor imagegen '%s' no encontrado en entry_points. "
            "Usando ImageGenerator built-in.",
            name,
        )

    from pong.image_generator import ImageGenerator
    return ImageGenerator(config)
