#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# create_dmg.sh -- Genera un .dmg instalador para macOS
# =============================================================================
# Uso:
#   ./scripts/create_dmg.sh
#
# Requisitos:
#   - dist/PongIA.app debe existir (ejecutar antes build_with_pyinstaller.py)
#   - hdiutil (viene con macOS, no necesita instalacion)
#
# Resultado:
#   dist/PongIA.dmg  (~1.2 GB comprimido)
# =============================================================================

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${ROOT_DIR}/dist"
APP_PATH="${DIST_DIR}/PongIA.app"
DMG_NAME="PongIA"
DMG_PATH="${DIST_DIR}/${DMG_NAME}.dmg"
DMG_TEMP="${DIST_DIR}/${DMG_NAME}_temp.dmg"
VOLUME_NAME="PongIA"
STAGING_DIR="${DIST_DIR}/dmg_staging"

# --- Verificar que el .app existe ---
if [[ ! -d "${APP_PATH}" ]]; then
    echo "ERROR: No se encuentra ${APP_PATH}"
    echo "Ejecuta primero: python3 scripts/build_with_pyinstaller.py"
    exit 1
fi

echo "=== Creando DMG para PongIA ==="
echo ""

# --- Limpiar archivos anteriores ---
rm -f "${DMG_PATH}" "${DMG_TEMP}"
rm -rf "${STAGING_DIR}"

# --- Preparar directorio de staging ---
echo "[1/4] Preparando contenido del DMG..."
mkdir -p "${STAGING_DIR}"

# Copiar .app al staging
cp -R "${APP_PATH}" "${STAGING_DIR}/"

# Crear enlace simbolico a /Applications (para drag & drop)
ln -s /Applications "${STAGING_DIR}/Applications"

# --- Calcular tamano necesario ---
echo "[2/4] Calculando tamano..."
APP_SIZE_KB=$(du -sk "${STAGING_DIR}" | awk '{print $1}')
# Anadir 20% de margen (HFS+ necesita espacio extra para metadatos)
DMG_SIZE_KB=$(( APP_SIZE_KB + APP_SIZE_KB / 5 ))

# --- Crear DMG temporal (lectura/escritura) ---
echo "[3/4] Creando imagen de disco..."
hdiutil create \
    -srcfolder "${STAGING_DIR}" \
    -volname "${VOLUME_NAME}" \
    -fs HFS+ \
    -fsargs "-c c=64,a=16,e=16" \
    -format UDRW \
    -size "${DMG_SIZE_KB}k" \
    "${DMG_TEMP}" \
    -quiet

# --- Convertir a DMG comprimido (solo lectura) ---
echo "[4/4] Comprimiendo DMG final..."
hdiutil convert \
    "${DMG_TEMP}" \
    -format UDZO \
    -imagekey zlib-level=9 \
    -o "${DMG_PATH}" \
    -quiet

# --- Limpiar ---
rm -f "${DMG_TEMP}"
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
