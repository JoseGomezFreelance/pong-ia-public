#!/usr/bin/env python3
"""Build PongIA executables with PyInstaller."""

from __future__ import annotations

import argparse
import importlib.util
import platform
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENTRYPOINT = PROJECT_ROOT / "main.py"
APP_NAME = "PongIA"

SYSTEM_TO_TARGET = {
    "darwin": "mac",
    "windows": "win",
    "linux": "linux",
}

# Todos los modulos del paquete pong que PyInstaller debe incluir.
PONG_HIDDEN_IMPORTS = [
    "pong",
    "pong.__init__",
    "pong.config",
    "pong.config.__init__",
    "pong.config.layout",
    "pong.config.colors",
    "pong.config.gameplay",
    "pong.config.media",
    "pong.config.models",
    "pong.config.narrator",
    "pong.config.version",
    "pong.config.zx_spectrum",
    "pong.config.ui_end_screen",
    "pong.config.ui_achievements",
    "pong.entities",
    "pong.sound",
    "pong.music",
    "pong.game",
    "pong.game_ai",
    "pong.game_persistence",
    "pong.game_imagegen",
    "pong.scoring",
    "pong.narrator",
    "pong.narrator_questions",
    "pong.narrator_summary",
    "pong.narration_bridge",
    "pong.renderer",
    "pong.renderer_achievements",
    "pong.renderer_end_screen",
    "pong.image_generator",
    "pong.providers",
    "pong.save_manager",
    "pong.emotional_state",
    "pong.achievements",
    "pong.achievement_icons",
    "pong.splash",
    "pong.theme",
    "pong.question_system",
    "pong.perf",
    "pong.harness",
    "pong.exceptions",
    "pong.protocols",
]

# Dependencias de terceros que se importan dinamicamente.
# Cada entrada es (modulo_a_verificar, [imports_a_incluir]).
THIRD_PARTY_HIDDEN_IMPORTS: list[tuple[str, list[str]]] = [
    ("llama_cpp", ["llama_cpp"]),
    ("mido", ["mido", "mido.backends", "mido.backends.backend_python"]),
    ("tomli", ["tomli"]),
    ("torch", [
        "torch",
        "torch.utils",
        "torch.utils.data",
    ]),
    ("diffusers", [
        "diffusers",
        "diffusers.pipelines.stable_diffusion",
        "diffusers.pipelines.stable_diffusion_xl",
        "diffusers.schedulers",
    ]),
    ("transformers", [
        "transformers",
        "transformers.models.clip",
        "transformers.models.auto",
    ]),
    ("accelerate", ["accelerate"]),
    ("safetensors", ["safetensors"]),
    ("peft", ["peft"]),
    ("huggingface_hub", ["huggingface_hub"]),
]

# Modulos que no necesitamos en el ejecutable (reducen tamanio).
EXCLUDE_MODULES = [
    "tkinter",
    "xmlrpc",
    "doctest",
    "distutils",
]

# Exclusiones extra para macOS (no hay CUDA).
MAC_EXCLUDE_MODULES = [
    "torch.cuda",
    "torch.distributed",
    "torch.testing",
    "torch.utils.tensorboard",
    "torch.utils.bottleneck",
    "torch.utils.benchmark",
]


def detect_current_target() -> str:
    system = platform.system().lower()
    target = SYSTEM_TO_TARGET.get(system)
    if not target:
        raise RuntimeError(f"Unsupported platform for build: {system}")
    return target


def is_module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def build_command(target: str, onefile: bool) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--strip",
        "--name",
        APP_NAME,
    ]
    if onefile:
        command.append("--onefile")

    # Separador de --add-data segun plataforma
    sep = ";" if target == "win" else ":"

    # Bundlear assets (musica MIDI, imagenes)
    assets_dir = PROJECT_ROOT / "assets"
    if assets_dir.exists():
        command.extend(["--add-data", f"{assets_dir}{sep}assets"])

    # Identificador de bundle para macOS
    if target == "mac":
        command.extend(["--osx-bundle-identifier", "com.pongia.app"])

    # Hidden imports: todos los modulos pong
    for module in PONG_HIDDEN_IMPORTS:
        command.extend(["--hidden-import", module])

    # Hidden imports: dependencias de terceros (solo si estan instaladas)
    for check_module, imports in THIRD_PARTY_HIDDEN_IMPORTS:
        if is_module_available(check_module):
            for imp in imports:
                command.extend(["--hidden-import", imp])

    # Collect-submodules para paquetes con muchos submodulos dinamicos
    for pkg in ("diffusers.schedulers", "torch.backends"):
        check = pkg.split(".")[0]
        if is_module_available(check):
            command.extend(["--collect-submodules", pkg])

    # Exclusiones globales para reducir tamanio
    for module in EXCLUDE_MODULES:
        command.extend(["--exclude-module", module])

    # Exclusiones extra en macOS (sin CUDA)
    if target == "mac":
        for module in MAC_EXCLUDE_MODULES:
            command.extend(["--exclude-module", module])

    command.append(str(ENTRYPOINT))
    return command


def expected_artifact(target: str, onefile: bool) -> Path:
    dist_dir = PROJECT_ROOT / "dist"
    if target == "mac":
        return dist_dir / f"{APP_NAME}.app"
    if target == "win":
        if onefile:
            return dist_dir / f"{APP_NAME}.exe"
        return dist_dir / APP_NAME / f"{APP_NAME}.exe"
    if onefile:
        return dist_dir / APP_NAME
    return dist_dir / APP_NAME / APP_NAME


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build PongIA executable for the current platform using PyInstaller."
    )
    parser.add_argument(
        "--target",
        default="auto",
        choices=["auto", "mac", "win", "linux"],
        help="Build target. Use auto to infer from current platform.",
    )
    parser.add_argument(
        "--onefile",
        action="store_true",
        help="Force onefile bundle. Windows defaults to onefile.",
    )
    args = parser.parse_args()

    current_target = detect_current_target()
    selected_target = current_target if args.target == "auto" else args.target

    if selected_target != current_target:
        raise SystemExit(
            f"Cross-compilation is not supported with this setup. "
            f"Run on a '{selected_target}' machine instead."
        )

    onefile = args.onefile or selected_target == "win"
    command = build_command(selected_target, onefile=onefile)

    print(f"Running: {' '.join(command)}")
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)

    artifact = expected_artifact(selected_target, onefile=onefile)
    if artifact.exists():
        print(f"Build completed: {artifact}")
    else:
        print("Build finished, but expected artifact path was not found.")
        print("Check dist/ directory for actual output.")


if __name__ == "__main__":
    main()
