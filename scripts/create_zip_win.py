#!/usr/bin/env python3
"""Crea un ZIP de distribucion de PongIA para itch.io y uso portable."""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = PROJECT_ROOT / "dist"
EXE_PATH = DIST_DIR / "PongIA.exe"


def get_version() -> str:
    """Extrae la version de pong/config/version.py sin importar el modulo."""
    version_file = PROJECT_ROOT / "pong" / "config" / "version.py"
    match = re.search(r'APP_VERSION\s*=\s*"(.+?)"', version_file.read_text())
    if not match:
        return "dev"
    # "Alfa 0.07" -> "Alfa_0.07" (seguro para nombres de archivo)
    return match.group(1).replace(" ", "_")


def main() -> int:
    parser = argparse.ArgumentParser(description="Crea ZIP de PongIA para itch.io")
    parser.add_argument(
        "name",
        nargs="?",
        default=None,
        help="Nombre del ZIP sin extension (ej: PongIA_0.07-hotfix1). "
             "Si se omite, usa PongIA_<version> automaticamente.",
    )
    args = parser.parse_args()

    if not EXE_PATH.exists():
        print(f"ERROR: No se encuentra {EXE_PATH}")
        print("Ejecuta primero: python scripts/build_with_pyinstaller.py")
        return 1

    zip_name = f"{args.name}.zip" if args.name else f"PongIA_{get_version()}.zip"
    zip_path = DIST_DIR / zip_name

    print(f"=== Creando ZIP: {zip_name} ===")
    print()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        # Ejecutable principal
        print("[1/3] Anadiendo PongIA.exe...")
        zf.write(EXE_PATH, "PongIA/PongIA.exe")

        # Configuracion de ejemplo
        toml_example = PROJECT_ROOT / "models.toml.example"
        if toml_example.exists():
            print("[2/3] Anadiendo models.toml.example...")
            zf.write(toml_example, "PongIA/models.toml.example")
        else:
            print("[2/3] models.toml.example no encontrado, omitiendo...")

        # Licencia
        license_file = PROJECT_ROOT / "LICENSE"
        if license_file.exists():
            print("[3/3] Anadiendo LICENSE...")
            zf.write(license_file, "PongIA/LICENSE")
        else:
            print("[3/3] LICENSE no encontrado, omitiendo...")

        # Directorios vacios (el juego los crea en runtime,
        # pero los incluimos para claridad)
        zf.writestr("PongIA/models/.keep", "")
        zf.writestr("PongIA/saves/.keep", "")

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print()
    print("=== ZIP creado exitosamente ===")
    print(f"  Archivo: {zip_path}")
    print(f"  Tamano:  {size_mb:.1f} MB")
    print()
    print("Para distribuir en itch.io:")
    print(f"  1. Subir {zip_name} como archivo Windows")
    print("  2. La app de itch.io lo extrae automaticamente")
    return 0


if __name__ == "__main__":
    sys.exit(main())
