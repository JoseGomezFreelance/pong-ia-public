"""Descarga de modelos de IA desde la interfaz del juego.

Proporciona funciones para comprobar el estado de los modelos instalados
y descargarlos con reportes de progreso, pensado para usarse desde la
pantalla de descarga ZX Spectrum (``ZXDownloadScreen``).

La descarga corre en un hilo separado; el hilo principal de pygame lee
el estado compartido cada frame para actualizar las barras de progreso.
"""

from __future__ import annotations

import logging
import re
import ssl
import threading
import urllib.error
import urllib.request

import certifi
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

__all__ = [
    "ModelStatus",
    "check_models_status",
    "is_llm_tier_installed",
    "is_onnx_model_installed",
    "download_onnx_model",
    "find_unused_llm_models",
    "delete_llm_model",
    "download_llm_for_tier",
    "run_downloads",
]


# ============================================================
# Estado de un modelo descargable
# ============================================================

@dataclass
class ModelStatus:
    """Estado de un modelo de IA descargable."""

    name: str                    # Nombre para la UI
    model_type: str              # "llm" | "diffusion"
    installed: bool = False
    size_hint: str = ""          # "~2 GB"
    progress: float = 0.0       # 0.0-1.0; -1 = indeterminado
    status_text: str = "Pendiente"
    error: str = ""

    @property
    def is_downloading(self) -> bool:
        return self.status_text.startswith("Descargando")

    @property
    def is_done(self) -> bool:
        return self.installed or bool(self.error)


# ============================================================
# Comprobar estado de modelos
# ============================================================

_MIN_MODEL_SIZE = 100_000_000  # 100 MB -- menor = descarga incompleta


def check_models_status() -> list[ModelStatus]:
    """Comprueba que modelos estan instalados y devuelve su estado.

    Returns:
        Lista con el estado del LLM y de los modelos de difusion.
    """
    from pong.config.models import load_models_config

    llm_config, image_config = load_models_config()

    statuses: list[ModelStatus] = []

    # --- LLM ---
    llm_installed = _is_llm_installed(llm_config.filename)
    statuses.append(
        ModelStatus(
            name=f"Modelo LLM ({llm_config.resolved_display_name})",
            model_type="llm",
            installed=llm_installed,
            size_hint="~2 GB",
            status_text="Instalado" if llm_installed else "Pendiente",
        )
    )

    # --- Difusion ---
    diff_installed = _is_diffusion_installed()
    statuses.append(
        ModelStatus(
            name=f"Modelos de difusion ({image_config.model_id.split('/')[-1]})",
            model_type="diffusion",
            installed=diff_installed,
            size_hint="~3 GB",
            status_text="Instalado" if diff_installed else "Pendiente",
        )
    )

    return statuses


def _is_llm_installed(filename: str) -> bool:
    """Comprueba si el modelo GGUF existe y tiene un tamano razonable."""
    from pong.providers import resolve_model_path

    path = resolve_model_path(Path("models") / filename)
    if not path.exists():
        return False
    try:
        return path.stat().st_size >= _MIN_MODEL_SIZE
    except OSError:
        return False


def _is_diffusion_installed() -> bool:
    """Comprueba si los modelos de difusion estan en la cache."""
    try:
        from pong.image_generator import is_model_cached

        return is_model_cached()
    except (ImportError, Exception):
        return False


# ============================================================
# Estado del modelo ONNX
# ============================================================

_MIN_ONNX_MODEL_SIZE = 50_000_000  # 50 MB -- menor = descarga incompleta

# Archivos necesarios para el modelo ONNX (modelo + tokenizer)
_ONNX_FILES = (
    (
        "model_quantized.onnx",
        "https://huggingface.co/Xenova/distilgpt2/resolve/main/"
        "onnx/model_quantized.onnx?download=true",
        _MIN_ONNX_MODEL_SIZE,
    ),
    (
        "vocab.json",
        "https://huggingface.co/distilbert/distilgpt2/resolve/main/vocab.json",
        1000,  # ~1 MB pero minimo 1 KB
    ),
    (
        "merges.txt",
        "https://huggingface.co/distilbert/distilgpt2/resolve/main/merges.txt",
        1000,
    ),
)


def _resolve_onnx_dir() -> Path:
    """Devuelve el directorio ``models/onnx/`` escribible."""
    return _resolve_models_dir() / "onnx"


def is_onnx_model_installed() -> bool:
    """Comprueba si el modelo ONNX y archivos de tokenizer estan instalados."""
    onnx_dir = _resolve_onnx_dir()
    if not onnx_dir.exists():
        return False
    for fname, _, min_size in _ONNX_FILES:
        path = onnx_dir / fname
        if not path.exists():
            return False
        try:
            if path.stat().st_size < min_size:
                return False
        except OSError:
            return False
    return True


def download_onnx_model(
    status: ModelStatus,
    lock: threading.Lock,
) -> bool:
    """Descarga el modelo ONNX (DistilGPT-2) + archivos de tokenizer.

    Descarga secuencialmente: model_quantized.onnx, vocab.json, merges.txt.
    Actualiza ``status`` in-place (protegido por *lock*).

    Returns:
        ``True`` si la descarga fue exitosa.
    """
    dest_dir = _resolve_onnx_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)

    for fname, url, min_size in _ONNX_FILES:
        dest_path = dest_dir / fname

        # Si ya existe y tiene tamaño razonable, saltar
        if dest_path.exists():
            try:
                if dest_path.stat().st_size >= min_size:
                    continue
            except OSError:
                pass

        with lock:
            status.status_text = f"Descargando {fname}..."

        ok = _download_file(url, dest_path, status, lock)
        if not ok:
            return False

    with lock:
        status.progress = 1.0
        status.installed = True
        status.status_text = "Instalado"

    logger.info("Modelo ONNX descargado en: %s", dest_dir)
    return True


# ============================================================
# Descarga de modelos
# ============================================================

def _resolve_models_dir() -> Path:
    """Resuelve el directorio ``models/`` escribible (compatible PyInstaller)."""
    from pong.config.media import _resolve_writable_dir

    return _resolve_writable_dir("models")


def _download_file(
    url: str,
    dest_path: Path,
    status: ModelStatus,
    lock: threading.Lock,
) -> bool:
    """Logica comun de descarga HTTP con progreso.

    Descarga *url* a *dest_path* usando un archivo ``.part`` temporal.
    Actualiza *status* in-place (protegido por *lock*).

    Returns:
        ``True`` si la descarga fue exitosa.
    """
    part_path = dest_path.with_suffix(dest_path.suffix + ".part")
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    with lock:
        status.status_text = "Conectando..."
        status.progress = 0.0

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PongIA/1.0"})
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(req, timeout=30, context=ssl_ctx) as response:
            total = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 8192

            with open(part_path, "wb") as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    with lock:
                        if total > 0:
                            pct = downloaded / total
                            status.progress = pct
                            mb_done = downloaded / 1_048_576
                            mb_total = total / 1_048_576
                            status.status_text = (
                                f"Descargando {mb_done:.0f}/{mb_total:.0f} MB"
                            )
                        else:
                            status.progress = -1
                            mb_done = downloaded / 1_048_576
                            status.status_text = (
                                f"Descargando {mb_done:.0f} MB..."
                            )

        # Renombrar .part -> final
        if dest_path.exists():
            dest_path.unlink()
        part_path.rename(dest_path)

        with lock:
            status.progress = 1.0
            status.installed = True
            status.status_text = "Instalado"

        logger.info("Descargado: %s", dest_path)
        return True

    except (urllib.error.URLError, OSError, ValueError) as exc:
        with lock:
            status.error = str(exc)
            status.status_text = f"Error: {exc}"
            status.progress = 0.0

        if part_path.exists():
            try:
                part_path.unlink()
            except OSError:
                pass

        logger.error("Error descargando %s: %s", dest_path.name, exc)
        return False


def download_llm_model(
    status: ModelStatus,
    lock: threading.Lock,
) -> bool:
    """Descarga el modelo LLM configurado en models.toml (GGUF) con progreso.

    Actualiza ``status`` in-place (protegido por *lock*).

    Returns:
        ``True`` si la descarga fue exitosa.
    """
    from pong.config.models import load_models_config

    llm_config, _ = load_models_config()
    dest_dir = _resolve_models_dir()
    dest_path = dest_dir / llm_config.filename
    return _download_file(llm_config.download_url, dest_path, status, lock)


def is_llm_tier_installed(filename: str) -> bool:
    """Comprueba si un modelo GGUF de un tier especifico esta descargado."""
    return _is_llm_installed(filename)


def download_llm_for_tier(
    repo_id: str,
    gguf_pattern: str,
    filename: str,
    download_url: str,
    split: bool,
    status: ModelStatus,
    lock: threading.Lock,
) -> bool:
    """Descarga un modelo LLM de un tier especifico.

    Para modelos single-file (split=False) usa descarga HTTP directa.
    Para modelos split (split=True) usa huggingface_hub.

    Returns:
        ``True`` si la descarga fue exitosa.
    """
    if not split and download_url:
        # Single file: descarga HTTP directa
        dest_dir = _resolve_models_dir()
        dest_path = dest_dir / filename
        return _download_file(download_url, dest_path, status, lock)

    # Split files: usar huggingface_hub
    return _download_hf_split(repo_id, gguf_pattern, status, lock)


def _download_hf_split(
    repo_id: str,
    pattern: str,
    status: ModelStatus,
    lock: threading.Lock,
) -> bool:
    """Descarga archivos split GGUF con barra de progreso real.

    Usa la API de HuggingFace para listar archivos y tamaños, y luego
    descarga cada parte por HTTP directo con progreso acumulado.
    """
    import fnmatch

    with lock:
        status.status_text = "Consultando archivos..."
        status.progress = 0.0

    try:
        from huggingface_hub import HfApi
    except ImportError:
        with lock:
            status.error = "huggingface_hub no disponible"
            status.status_text = "Error: huggingface_hub no disponible"
            status.progress = 0.0
        return False

    try:
        api = HfApi()
        repo_files = list(api.list_repo_tree(repo_id, recursive=False))
        matching = [
            (f.rfilename, f.size)
            for f in repo_files
            if hasattr(f, "rfilename")
            and hasattr(f, "size")
            and f.size
            and fnmatch.fnmatch(f.rfilename, pattern)
        ]

        if not matching:
            with lock:
                status.error = f"No se encontraron archivos: {pattern}"
                status.status_text = f"Error: sin archivos {pattern}"
                status.progress = 0.0
            return False

        matching.sort()
        total_bytes = sum(s for _, s in matching)
        downloaded_total = 0
        dest_dir = _resolve_models_dir()
        dest_dir.mkdir(parents=True, exist_ok=True)

        ssl_ctx = ssl.create_default_context(cafile=certifi.where())

        for i, (filename, _file_size) in enumerate(matching):
            url = (
                f"https://huggingface.co/{repo_id}/resolve/main/{filename}"
            )
            dest_path = dest_dir / filename
            part_path = dest_path.with_suffix(dest_path.suffix + ".part")

            with lock:
                mb_done = downloaded_total / 1_048_576
                mb_total = total_bytes / 1_048_576
                status.status_text = (
                    f"Descargando {mb_done:.0f}/{mb_total:.0f} MB "
                    f"({i + 1}/{len(matching)})"
                )

            req = urllib.request.Request(
                url, headers={"User-Agent": "PongIA/1.0"}
            )
            with urllib.request.urlopen(
                req, timeout=60, context=ssl_ctx
            ) as response:
                chunk_size = 8192
                with open(part_path, "wb") as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded_total += len(chunk)

                        with lock:
                            pct = (
                                downloaded_total / total_bytes
                                if total_bytes > 0
                                else 0
                            )
                            status.progress = pct
                            mb_done = downloaded_total / 1_048_576
                            mb_total = total_bytes / 1_048_576
                            status.status_text = (
                                f"Descargando {mb_done:.0f}/{mb_total:.0f} MB"
                            )

            # Renombrar .part -> final
            if dest_path.exists():
                dest_path.unlink()
            part_path.rename(dest_path)

        with lock:
            status.progress = 1.0
            status.installed = True
            status.status_text = "Instalado"

        logger.info("Modelo split descargado: %s (%d partes)", repo_id, len(matching))
        return True

    except (urllib.error.URLError, OSError, ValueError) as exc:
        with lock:
            status.error = str(exc)
            status.status_text = f"Error: {exc}"
            status.progress = 0.0

        # Limpiar .part residuales
        try:
            dest_dir = _resolve_models_dir()
            for part in dest_dir.glob("*.gguf.part"):
                part.unlink()
        except OSError:
            pass

        logger.error("Error descargando %s: %s", repo_id, exc)
        return False

    except Exception as exc:
        with lock:
            status.error = str(exc)
            status.status_text = f"Error: {exc}"
            status.progress = 0.0
        logger.error("Error descargando %s: %s", repo_id, exc)
        return False


def _split_base(filename: str) -> str:
    """Extrae el nombre base de un archivo GGUF (sin sufijo de split).

    ``qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf`` → ``qwen2.5-7b-instruct-q4_k_m``
    ``qwen2.5-3b-instruct-q4_k_m.gguf`` → ``qwen2.5-3b-instruct-q4_k_m``
    """
    name = filename.removesuffix(".gguf")
    return re.sub(r"-\d{5}-of-\d{5}$", "", name)


def find_unused_llm_models(active_filename: str) -> list[tuple[str, float]]:
    """Encuentra modelos GGUF descargados que no son el activo.

    Agrupa archivos split (``-00001-of-NNNNN.gguf``, etc.) como un solo
    modelo y reporta el tamaño total del grupo.

    Args:
        active_filename: Nombre del archivo GGUF actualmente en uso
            (primer archivo en caso de split).

    Returns:
        Lista de ``(display_name, size_gb)`` de modelos no activos.
        ``display_name`` es el primer archivo del grupo (o el unico).
    """
    models_dir = _resolve_models_dir()
    if not models_dir.exists():
        return []

    active_base = _split_base(active_filename)

    # Agrupar por base: {base: [(filename, size_bytes), ...]}
    groups: dict[str, list[tuple[str, int]]] = {}
    for path in models_dir.glob("*.gguf"):
        base = _split_base(path.name)
        try:
            size = path.stat().st_size
        except OSError:
            continue
        groups.setdefault(base, []).append((path.name, size))

    unused: list[tuple[str, float]] = []
    for base, files in groups.items():
        if base == active_base:
            continue
        total_bytes = sum(s for _, s in files)
        total_gb = total_bytes / (1024 ** 3)
        if total_gb < 0.1:
            continue
        # Usar el primer archivo como display name
        first_file = sorted(files)[0][0]
        unused.append((first_file, round(total_gb, 1)))

    return unused


def delete_llm_model(filename: str) -> bool:
    """Elimina un modelo GGUF del directorio models/.

    Si el archivo es parte de un modelo split, elimina todos los archivos
    del grupo (misma base).

    Returns:
        ``True`` si se elimino al menos un archivo.
    """
    models_dir = _resolve_models_dir()
    base = _split_base(filename)
    deleted = False

    # Buscar todos los archivos con la misma base
    if not models_dir.exists():
        return False
    for path in models_dir.glob("*.gguf"):
        if _split_base(path.name) != base:
            continue
        try:
            path.unlink()
            logger.info("Modelo eliminado: %s", path)
            deleted = True
        except OSError as exc:
            logger.error("Error eliminando %s: %s", path, exc)

    return deleted


def download_diffusion_models(
    status: ModelStatus,
    lock: threading.Lock,
) -> bool:
    """Descarga los modelos de difusion usando huggingface_hub.

    El progreso es indeterminado (snapshot_download no reporta bytes).

    Returns:
        ``True`` si la descarga fue exitosa.
    """
    with lock:
        status.status_text = "Descargando modelos de difusion..."
        status.progress = -1  # indeterminado

    def _progress_callback(msg: str) -> None:
        with lock:
            status.status_text = msg

    try:
        from pong.image_generator import ensure_models_downloaded

        ok = ensure_models_downloaded(progress_callback=_progress_callback)
        with lock:
            if ok:
                status.installed = True
                status.progress = 1.0
                status.status_text = "Instalado"
            else:
                status.error = "huggingface_hub no disponible"
                status.status_text = "Error: huggingface_hub no disponible"
                status.progress = 0.0
        return ok

    except Exception as exc:
        with lock:
            status.error = str(exc)
            status.status_text = f"Error: {exc}"
            status.progress = 0.0
        logger.error("Error descargando modelos de difusion: %s", exc)
        return False


# ============================================================
# Orquestador de descargas (corre en hilo separado)
# ============================================================

def run_downloads(
    statuses: list[ModelStatus],
    lock: threading.Lock,
    on_complete: Callable[[], None] | None = None,
) -> None:
    """Descarga secuencialmente todos los modelos pendientes.

    Pensado para ejecutarse en un ``threading.Thread``.
    Actualiza cada ``ModelStatus`` in-place (protegido por *lock*).

    Args:
        statuses: Lista de ModelStatus a descargar.
        lock: Lock compartido con el hilo principal (pygame).
        on_complete: Callback opcional al terminar todo.
    """
    for status in statuses:
        with lock:
            if status.installed:
                continue  # ya instalado, saltar

        if status.model_type == "llm":
            download_llm_model(status, lock)
        elif status.model_type == "diffusion":
            download_diffusion_models(status, lock)
        elif status.model_type == "onnx":
            download_onnx_model(status, lock)

    if on_complete:
        on_complete()
