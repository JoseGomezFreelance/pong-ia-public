#!/usr/bin/env bash
set -euo pipefail

# Bootstrap local model runtime (no APIs, no Ollama)
# Usage:
#   ./scripts/bootstrap_local_model.sh
# Optional env vars:
#   MODEL_URL=...            # direct URL to GGUF file
#   MODEL_FILENAME=...       # output file name inside models/
#   MODEL_SHA256=...         # expected sha256 checksum (optional)

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODELS_DIR="${ROOT_DIR}/models"
mkdir -p "${MODELS_DIR}"

DEFAULT_URL="https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf?download=true"
MODEL_URL="${MODEL_URL:-$DEFAULT_URL}"
MODEL_FILENAME="${MODEL_FILENAME:-qwen2.5-3b-instruct-q4_k_m.gguf}"
MODEL_SHA256="${MODEL_SHA256:-}"
MODEL_PATH="${MODELS_DIR}/${MODEL_FILENAME}"

echo "[1/3] Instalando dependencias Python locales..."
python3 -m pip install -r "${ROOT_DIR}/requirements.txt"
python3 -m pip install llama-cpp-python huggingface-hub

echo "[2/3] Descargando modelo GGUF en ${MODEL_PATH}"
if command -v curl >/dev/null 2>&1; then
  curl -L --fail --retry 3 "${MODEL_URL}" -o "${MODEL_PATH}"
elif command -v wget >/dev/null 2>&1; then
  wget -O "${MODEL_PATH}" "${MODEL_URL}"
else
  echo "ERROR: se requiere curl o wget para descargar el modelo."
  exit 1
fi

echo "[3/3] Verificando descarga"
if [[ -n "${MODEL_SHA256}" ]]; then
  if command -v sha256sum >/dev/null 2>&1; then
    ACTUAL_SHA256="$(sha256sum "${MODEL_PATH}" | awk '{print $1}')"
  elif command -v shasum >/dev/null 2>&1; then
    ACTUAL_SHA256="$(shasum -a 256 "${MODEL_PATH}" | awk '{print $1}')"
  else
    echo "WARN: no se puede verificar checksum (sha256sum/shasum no encontrado)."
    ACTUAL_SHA256=""
  fi
  if [[ -n "${ACTUAL_SHA256}" ]]; then
    if [[ "${ACTUAL_SHA256}" != "${MODEL_SHA256}" ]]; then
      echo "ERROR: checksum inválido"
      echo "Esperado: ${MODEL_SHA256}"
      echo "Actual:   ${ACTUAL_SHA256}"
      exit 1
    fi
    echo "Checksum OK"
  fi
else
  echo "Checksum no configurado (MODEL_SHA256 vacío)."
fi

echo "Bootstrap completado. Modelo listo en: ${MODEL_PATH}"
