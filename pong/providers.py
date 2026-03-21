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
from typing import Any, Protocol, runtime_checkable

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

    def set_perf(self, perf: Any) -> None: ...

    def set_log_fn(self, fn: Any) -> None: ...

    def activate(self) -> None: ...

    def request(self, prompt: str, negative_prompt: str = "") -> None: ...

    def consume(self) -> Any | None: ...

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


# ============================================================
# LocalLLMProvider — implementacion built-in con llama-cpp
# ============================================================

class LocalLLMProvider:
    """Proveedor LLM local usando llama-cpp-python con archivos GGUF.

    Esta clase encapsula la carga del modelo y la llamada a
    ``create_chat_completion``, separando la inferencia pura de la
    logica de narracion.
    """

    def __init__(self, config: Any | None = None) -> None:
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
        model_relative_path = Path("models") / self._config.filename
        model_path = resolve_model_path(model_relative_path)

        if not model_path.exists():
            return

        try:
            llama_cpp = importlib.import_module("llama_cpp")
            self._model = llama_cpp.Llama(
                model_path=str(model_path),
                n_ctx=self._config.context_window,
                n_threads=self._config.threads,
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


def load_llm_provider(config: Any | None = None) -> LLMProviderProtocol:
    """Carga el proveedor de LLM configurado.

    Orden de resolucion:
    1. Variable ``PONG_IA_LLM_PROVIDER`` → busca en entry_points ``pong_ia.llm``.
    2. Si no hay variable o no se encuentra el entry_point, usa ``LocalLLMProvider``.

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

    return LocalLLMProvider(config)


def load_imagegen_provider(config: Any | None = None) -> ImageGenProviderProtocol:
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
