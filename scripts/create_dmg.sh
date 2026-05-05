#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# create_dmg.sh -- Genera un .dmg instalador para macOS
# =============================================================================
# Uso:
#   ./scripts/create_dmg.sh              # genera dist/PongIA.dmg
#   ./scripts/create_dmg.sh PongIA_Beta_0.10  # nombre personalizado
#
# Requisitos:
#   - dist/PongIA.app debe existir (ejecutar antes build_with_pyinstaller.py)
#   - hdiutil (viene con macOS, no necesita instalacion)
#
# Resultado:
#   dist/<NOMBRE>.dmg  (comprimido con zlib-9)
# =============================================================================

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${ROOT_DIR}/dist"
APP_PATH="${DIST_DIR}/PongIA.app"
DMG_NAME="${1:-PongIA}"
DMG_PATH="${DIST_DIR}/${DMG_NAME}.dmg"
STAGING_DIR=$(mktemp -d)
VOLUME_NAME="PongIA"

# --- Verificar que el .app existe ---
if [[ ! -d "${APP_PATH}" ]]; then
    echo "ERROR: No se encuentra ${APP_PATH}"
    echo "Ejecuta primero: python3 scripts/build_with_pyinstaller.py"
    exit 1
fi

echo "=== Creando DMG para PongIA ==="
echo ""

# --- Limpiar DMG anterior si existe ---
rm -f "${DMG_PATH}"

# --- Preparar directorio de staging ---
echo "[1/3] Preparando contenido del DMG..."

# Copiar .app al staging
cp -R "${APP_PATH}" "${STAGING_DIR}/"

# Crear enlace simbolico a /Applications (para drag & drop)
ln -s /Applications "${STAGING_DIR}/Applications"

# Icono personalizado del volumen DMG
ICON_PATH="${ROOT_DIR}/assets/images/icon.icns"
if [[ -f "${ICON_PATH}" ]]; then
    cp "${ICON_PATH}" "${STAGING_DIR}/.VolumeIcon.icns"
fi

# --- Crear DMG comprimido directamente ---
echo "[2/3] Creando imagen de disco comprimida..."
hdiutil create \
    -srcfolder "${STAGING_DIR}" \
    -volname "${VOLUME_NAME}" \
    -fs HFS+ \
    -format UDZO \
    -imagekey zlib-level=9 \
    -o "${DMG_PATH}" \
    -quiet

# --- Limpiar ---
echo "[3/3] Limpiando..."
rm -rf "${STAGING_DIR}"

# --- Resultado ---
DMG_SIZE=$(du -sh "${DMG_PATH}" | awk '{print $1}')
echo ""
echo "=== DMG creado exitosamente ==="
echo "  Archivo: ${DMG_PATH}"
echo "  Tamano:  ${DMG_SIZE}"
echo ""
echo "El usuario solo tiene que:"
echo "  1. Abrir ${DMG_NAME}.dmg"
echo "  2. Arrastrar PongIA a Applications"
echo "  3. Ejecutar PongIA desde Launchpad"
