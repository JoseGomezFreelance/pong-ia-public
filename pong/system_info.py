"""Deteccion de hardware del sistema para recomendar modelos LLM.

Proporciona ``detect_system_info()`` que devuelve RAM, GPU, disco y CPU
de forma cross-platform (macOS / Windows / Linux).  Si ``psutil`` no
esta instalado, devuelve valores por defecto razonables.
"""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = ["SystemInfo", "detect_system_info"]


@dataclass(frozen=True)
class SystemInfo:
    """Informacion del hardware del sistema."""

    total_ram_gb: float
    available_ram_gb: float
    unified_memory: bool          # True en Apple Silicon
    gpu_name: str                 # "Apple M1", "NVIDIA RTX 3060", ...
    gpu_type: str                 # "mps" | "cuda" | "cpu"
    gpu_vram_gb: float            # 0.0 si unificada o desconocida
    disk_free_gb: float
    cpu_name: str
    cpu_cores: int
    has_avx: bool = True          # Default True (arm64 no usa AVX)
    has_avx2: bool = True         # Default True (arm64 no usa AVX2)


# ============================================================
# Helpers internos
# ============================================================

def _detect_ram() -> tuple[float, float]:
    """Devuelve (total_gb, available_gb)."""
    try:
        import psutil
        mem = psutil.virtual_memory()
        return mem.total / (1024 ** 3), mem.available / (1024 ** 3)
    except Exception:
        logger.warning("psutil no disponible; asumiendo 8 GB de RAM")
        return 8.0, 4.0


def _is_apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"


def _detect_gpu() -> tuple[str, str, float]:
    """Devuelve (gpu_name, gpu_type, gpu_vram_gb)."""
    try:
        import torch

        # Apple Silicon (MPS)
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            # En Apple Silicon la VRAM es la RAM unificada; se reporta aparte
            chip_name = _apple_chip_name()
            return chip_name, "mps", 0.0

        # NVIDIA (CUDA)
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            props = torch.cuda.get_device_properties(0)
            vram_gb = props.total_memory / (1024 ** 3)
            return name, "cuda", round(vram_gb, 1)
    except Exception:
        logger.debug("torch no disponible para detectar GPU; intentando nvidia-smi")

    # Fallback: nvidia-smi (funciona sin torch instalado)
    gpu = _detect_gpu_nvidia_smi()
    if gpu is not None:
        return gpu

    return "Desconocida", "cpu", 0.0


def _detect_gpu_nvidia_smi() -> tuple[str, str, float] | None:
    """Detecta GPU NVIDIA via nvidia-smi (no requiere torch)."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None
        line = result.stdout.strip().split("\n")[0]
        parts = line.split(",")
        if len(parts) < 2:
            return None
        name = parts[0].strip()
        try:
            vram_mb = float(parts[1].strip())
            vram_gb = round(vram_mb / 1024, 1)
        except ValueError:
            vram_gb = 0.0
        return name, "cuda", vram_gb
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return None


def _apple_chip_name() -> str:
    """Intenta obtener el nombre del chip Apple (M1, M2, etc.)."""
    try:
        import subprocess
        result = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return f"Apple {platform.machine()}"


def _detect_cpu() -> tuple[str, int]:
    """Devuelve (cpu_name, cores_fisicos)."""
    name = platform.processor() or platform.machine()

    # En macOS platform.processor() devuelve "arm" o "i386"
    if sys.platform == "darwin" and name in ("arm", "i386", ""):
        name = _apple_chip_name()

    cores = 4  # default
    try:
        import psutil
        physical = psutil.cpu_count(logical=False)
        if physical:
            cores = physical
    except Exception:
        import os
        cores = os.cpu_count() or 4

    return name, cores


def _detect_cpu_simd() -> tuple[bool, bool]:
    """Detecta soporte AVX y AVX2 en la CPU.

    Retorna ``(has_avx, has_avx2)``.
    En arquitecturas no-x86 (arm64, aarch64) retorna ``(True, True)``
    porque no necesitan AVX — llama-cpp usa NEON/Metal en su lugar.
    Si la deteccion falla, retorna ``(True, True)`` para no bloquear.
    """
    machine = platform.machine().lower()
    if machine not in ("x86_64", "amd64", "x86", "i686", "i386"):
        return True, True

    try:
        flags = _read_cpu_flags()
    except Exception:
        logger.debug("No se pudieron leer flags de CPU; asumiendo AVX2")
        return True, True

    if not flags:
        return True, True

    tokens = set(flags.lower().split())
    # macOS sysctl usa mayusculas separadas por espacio ("AVX1.0 AVX2")
    # Linux /proc/cpuinfo usa minusculas ("avx avx2")
    has_avx = "avx" in tokens or "avx1.0" in tokens
    has_avx2 = "avx2" in tokens
    return has_avx, has_avx2


def _read_cpu_flags() -> str:
    """Lee los flags/features de la CPU segun la plataforma."""
    if sys.platform == "darwin":
        return _read_cpu_flags_macos()
    if sys.platform == "linux":
        return _read_cpu_flags_linux()
    if sys.platform == "win32":
        return _read_cpu_flags_windows()
    return ""


def _read_cpu_flags_macos() -> str:
    """Lee features de CPU en macOS via sysctl."""
    parts: list[str] = []
    for key in ("machdep.cpu.features", "machdep.cpu.leaf7_features"):
        try:
            result = subprocess.run(
                ["sysctl", "-n", key],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                parts.append(result.stdout.strip())
        except Exception:
            pass
    return " ".join(parts)


def _read_cpu_flags_linux() -> str:
    """Lee flags de CPU en Linux via /proc/cpuinfo."""
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("flags"):
                    # flags\t: sse sse2 avx avx2 ...
                    _, _, flags = line.partition(":")
                    return flags.strip()
    except Exception:
        pass
    return ""


def _read_cpu_flags_windows() -> str:
    """Lee features de CPU en Windows via CPUID."""
    return _read_cpu_flags_windows_cpuid()


def _read_cpu_flags_windows_cpuid() -> str:
    """Detecta AVX/AVX2 en Windows usando la instruccion CPUID via ctypes."""
    try:
        import ctypes
        import struct
        import tempfile

        # Shellcode x86_64 para CPUID leaf 1 (ECX) y leaf 7 (EBX)
        # Retorna: ECX de leaf 1 en [0:4], EBX de leaf 7 en [4:8]
        code = (
            b"\x53"                    # push rbx
            b"\x48\x89\xcf"            # mov rdi, rcx  (primer arg Windows x64)
            b"\xb8\x01\x00\x00\x00"    # mov eax, 1
            b"\x0f\xa2"                # cpuid
            b"\x89\x0f"                # mov [rdi], ecx
            b"\xb8\x07\x00\x00\x00"    # mov eax, 7
            b"\x31\xc9"                # xor ecx, ecx
            b"\x0f\xa2"                # cpuid
            b"\x89\x5f\x04"            # mov [rdi+4], ebx
            b"\x5b"                    # pop rbx
            b"\xc3"                    # ret
        )

        # Alojar memoria ejecutable
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        MEM_COMMIT = 0x1000
        MEM_RESERVE = 0x2000
        PAGE_EXECUTE_READWRITE = 0x40
        MEM_RELEASE = 0x8000

        addr = kernel32.VirtualAlloc(
            None, len(code), MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE,
        )
        if not addr:
            return ""

        ctypes.memmove(addr, code, len(code))

        buf = ctypes.create_string_buffer(8)
        func_type = ctypes.CFUNCTYPE(None, ctypes.c_void_p)
        func = func_type(addr)
        func(ctypes.addressof(buf))

        kernel32.VirtualFree(addr, 0, MEM_RELEASE)

        ecx_leaf1, ebx_leaf7 = struct.unpack("<II", buf.raw)

        flags: list[str] = []
        # AVX: bit 28 de ECX (leaf 1)
        if ecx_leaf1 & (1 << 28):
            flags.append("avx")
        # AVX2: bit 5 de EBX (leaf 7, subleaf 0)
        if ebx_leaf7 & (1 << 5):
            flags.append("avx2")
        return " ".join(flags)

    except Exception:
        logger.debug("CPUID fallback fallo en Windows")
        return ""


def _detect_disk_free(path: Path | None = None) -> float:
    """Devuelve GB libres en la particion del directorio de modelos."""
    if path is None:
        try:
            from pong.config.media import _resolve_writable_dir
            path = _resolve_writable_dir("models")
        except Exception:
            path = Path.cwd()

    # Si el directorio no existe todavia, subir al padre que si exista
    # (en instalaciones nuevas, models/ puede no haberse creado aun)
    target = path
    while not target.exists():
        parent = target.parent
        if parent == target:
            break
        target = parent

    try:
        usage = shutil.disk_usage(target)
        return round(usage.free / (1024 ** 3), 1)
    except Exception:
        return 0.0


# ============================================================
# API publica
# ============================================================

def detect_system_info() -> SystemInfo:
    """Detecta el hardware del sistema.

    Funciona sin psutil ni torch (con valores degradados).
    """
    total_ram, available_ram = _detect_ram()
    gpu_name, gpu_type, gpu_vram = _detect_gpu()
    cpu_name, cpu_cores = _detect_cpu()
    disk_free = _detect_disk_free()
    unified = _is_apple_silicon()
    has_avx, has_avx2 = _detect_cpu_simd()

    return SystemInfo(
        total_ram_gb=round(total_ram, 1),
        available_ram_gb=round(available_ram, 1),
        unified_memory=unified,
        gpu_name=gpu_name,
        gpu_type=gpu_type,
        gpu_vram_gb=gpu_vram,
        disk_free_gb=disk_free,
        cpu_name=cpu_name,
        cpu_cores=cpu_cores,
        has_avx=has_avx,
        has_avx2=has_avx2,
    )
