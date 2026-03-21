"""Descarga de modelos de IA desde la interfaz del juego.

Proporciona funciones para comprobar el estado de los modelos instalados
y descargarlos con reportes de progreso, pensado para usarse desde la
pantalla de descarga ZX Spectrum (``ZXDownloadScreen``).

La descarga corre en un hilo separado; el hilo principal de pygame lee
el estado compartido cada frame para actualizar las barras de progreso.
"""

from __future__ import annotations

import logging
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

__all__ = [
    "ModelStatus",
    "check_models_status",
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
# Descarga de modelos
# ============================================================

def _resolve_models_dir() -> Path:
    """Resuelve el directorio ``models/`` escribible (compatible PyInstaller)."""
    from pong.config.media import _resolve_writable_dir

    return _resolve_writable_dir("models")


def download_llm_model(
    status: ModelStatus,
    lock: threading.Lock,
) -> bool:
    """Descarga el modelo LLM (GGUF) con progreso.

    Actualiza ``status`` in-place (protegido por *lock*).

    Returns:
        ``True`` si la descarga fue exitosa.
    """
    from pong.config.models import load_models_config

    llm_config, _ = load_models_config()
    url = llm_config.download_url
    dest_dir = _resolve_models_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / llm_config.filename
    part_path = dest_path.with_suffix(dest_path.suffix + ".part")

    with lock:
        status.status_text = "Conectando..."
        status.progress = 0.0

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PongIA/1.0"})
        with urllib.request.urlopen(req, timeout=30) as response:
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

        logger.info("LLM descargado: %s", dest_path)
        return True

    except (urllib.error.URLError, OSError, ValueError) as exc:
        with lock:
            status.error = str(exc)
            status.status_text = f"Error: {exc}"
            status.progress = 0.0

        # Limpiar archivo parcial
        if part_path.exists():
            try:
                part_path.unlink()
            except OSError:
                pass

        logger.error("Error descargando LLM: %s", exc)
        return False


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

    if on_complete:
        on_complete()
