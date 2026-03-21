# Modelos LLM locales recomendados (sin APIs ni Ollama)

## Requisito del proyecto
Queremos una integración **100% local y autónoma** para futuras fases de `pong-ia`:
- Sin APIs externas.
- Sin depender de Ollama.
- Instalación reproducible para un equipo gaming medio (ej. RTX 3060 12 GB).
- Licencia clara para uso en portafolio y distribución del repositorio.

## Recomendación principal

### 1) `Qwen2.5-3B-Instruct` (GGUF)
- **Licencia**: Apache-2.0 (permisiva, apta para proyectos personales/comerciales).
- **Calidad/coste**: mejor calidad narrativa que 1.5B manteniendo buena velocidad local.
- **Idioma**: funciona bien en español.
- **Huella típica**:
  - `Q4_K_M`: ~1.8–2.3 GB.
  - `Q8_0`: ~3.6–4.6 GB.
- **Hardware objetivo**: una RTX 3060 puede moverlo sin problemas en cuantización GGUF.

## Alternativas válidas (Apache-2.0)

### 2) `Qwen2.5-1.5B-Instruct` (GGUF)
- Más ligero (~1.0–1.2 GB en Q4_K_M) y bastante rápido.
- Menor riqueza expresiva que 3B, útil como modo rápido.

### 3) `Qwen2.5-0.5B-Instruct` (GGUF)
- Más ligero aún (~0.4–0.7 GB según cuantización).
- Menor calidad narrativa/razonamiento, útil como modo "ultra-ligero".

### 4) `TinyLlama-1.1B-Chat` (GGUF)
- Muy liviano y rápido.
- Calidad inferior a Qwen2.5 en seguimiento de instrucciones largas.

## Decisión propuesta para el repo
Usar por defecto:
- **Modelo**: `Qwen2.5-3B-Instruct`.
- **Formato**: GGUF.
- **Runtime**: `llama-cpp-python` (backend local, sin servidor externo).

## Nota importante sobre "incluirlo en el repositorio"
Subir pesos LLM al repo Git suele ser mala práctica por:
- Tamaño (1–2+ GB por archivo).
- Clonado lento y coste de almacenamiento.
- Límites habituales de hosting Git.

En su lugar, este repo incorpora scripts para:
1. Descargar automáticamente el modelo en `models/`.
2. Verificar checksum (cuando se configure).
3. Ejecutar localmente sin APIs ni Ollama.

Con esto el proyecto queda **autónomo para el usuario final** tras un único comando de bootstrap.
