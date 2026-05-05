#!/usr/bin/env python3
"""Genera icon.ico y icon.icns a partir de assets/images/icon.* (png, jpg, jpeg, webp, bmp)."""

import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("ERROR: Pillow no esta instalado. Ejecuta: pip install Pillow")

ROOT = Path(__file__).resolve().parent.parent
IMAGES_DIR = ROOT / "assets" / "images"
ICON_ICO = IMAGES_DIR / "icon.ico"
ICON_ICNS = IMAGES_DIR / "icon.icns"

# Extensiones soportadas como fuente (orden de preferencia)
SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


def find_source_icon() -> Path | None:
    """Busca icon.* en assets/images/ con cualquier extension soportada."""
    for ext in SUPPORTED_EXTENSIONS:
        candidate = IMAGES_DIR / f"icon{ext}"
        if candidate.exists():
            return candidate
    return None

# Tamanos requeridos para .ico (Windows)
ICO_SIZES = [16, 32, 48, 256]

# Tamanos requeridos para .icns (macOS) — iconutil espera estos
ICNS_SIZES = {
    "icon_16x16.png": 16,
    "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32,
    "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
    "icon_512x512@2x.png": 1024,
}


def generate_ico(source: Image.Image) -> None:
    """Genera icon.ico con multiples tamanos embebidos."""
    imgs = [source.resize((s, s), Image.LANCZOS) for s in ICO_SIZES]
    imgs[0].save(str(ICON_ICO), format="ICO", sizes=[(s, s) for s in ICO_SIZES],
                 append_images=imgs[1:])
    print(f"  -> {ICON_ICO.relative_to(ROOT)}")


def generate_icns(source: Image.Image) -> None:
    """Genera icon.icns usando iconutil (solo macOS)."""
    if platform.system() != "Darwin":
        print("  ** .icns solo se puede generar en macOS (necesita iconutil)")
        print("  ** Ejecuta este script en Mac para generar el .icns")
        return

    if not shutil.which("iconutil"):
        print("  ** iconutil no encontrado. Instala Xcode Command Line Tools:")
        print("     xcode-select --install")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        iconset = Path(tmpdir) / "icon.iconset"
        iconset.mkdir()

        for name, size in ICNS_SIZES.items():
            img = source.resize((size, size), Image.LANCZOS)
            img.save(str(iconset / name), format="PNG")

        result = subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(ICON_ICNS)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"  ** Error de iconutil: {result.stderr.strip()}")
            return

    print(f"  -> {ICON_ICNS.relative_to(ROOT)}")


def main() -> None:
    icon_path = find_source_icon()
    if icon_path is None:
        exts = ", ".join(SUPPORTED_EXTENSIONS)
        sys.exit(f"ERROR: No se encuentra icon.* en {IMAGES_DIR.relative_to(ROOT)}/\n"
                 f"Coloca tu imagen (1024x1024, cuadrada) como icon.png, icon.jpg, etc.\n"
                 f"Extensiones soportadas: {exts}")

    source = Image.open(icon_path).convert("RGBA")
    w, h = source.size
    print(f"Fuente: {icon_path.relative_to(ROOT)} ({w}x{h})")

    if w != h:
        print(f"AVISO: La imagen no es cuadrada ({w}x{h}). El resultado puede distorsionarse.")
    if w < 256:
        print(f"AVISO: Resolucion baja ({w}px). Se recomienda al menos 1024x1024.")

    print("\nGenerando .ico (Windows)...")
    generate_ico(source)

    print("\nGenerando .icns (macOS)...")
    generate_icns(source)

    print("\nListo!")


if __name__ == "__main__":
    main()
