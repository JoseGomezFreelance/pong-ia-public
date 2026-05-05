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

## Sistema multi-tier de modelos LLM (v0.08+)

A partir de la versión 0.08, PongIA ofrece un selector de modelo LLM con
**5 niveles de calidad** basados en la familia Qwen 2.5 Instruct (Q4_K_M).
El usuario elige el nivel que mejor se ajuste a su hardware desde una
pantalla integrada en el juego.

### Los 5 niveles

| Nivel | Modelo | Tamaño | RAM recomendada | RAM justa |
|-------|--------|--------|-----------------|-----------|
| 1 | Qwen 2.5 3B | ~2 GB | 8 GB | 4 GB |
| 2 | Qwen 2.5 7B | ~4.4 GB (2 partes) | 12 GB | 8 GB |
| 3 | Qwen 2.5 14B | ~8.6 GB (3 partes) | 16 GB | 12 GB |
| 4 | Qwen 2.5 32B | ~18.5 GB (5 partes) | 32 GB | 24 GB |
| 5 | Qwen 2.5 72B | ~41 GB (12 partes) | 64 GB | 48 GB |

Todos los modelos usan cuantización **Q4_K_M** y licencia **Apache-2.0**.

### Archivos split GGUF

Los modelos de 7B en adelante se distribuyen en HuggingFace como archivos
GGUF divididos (split). Por ejemplo, el 14B consta de 3 partes:

```
qwen2.5-14b-instruct-q4_k_m-00001-of-00003.gguf  (~3.99 GB)
qwen2.5-14b-instruct-q4_k_m-00002-of-00003.gguf  (~3.99 GB)
qwen2.5-14b-instruct-q4_k_m-00003-of-00003.gguf  (~1.01 GB)
```

`llama-cpp-python` (≥0.3.16) carga modelos split apuntando al primer
archivo (`-00001-of-NNNNN.gguf`); localiza el resto automáticamente.

### Detección de hardware y recomendaciones

Al entrar en el selector, el sistema detecta automáticamente:
- **RAM total** (y VRAM en sistemas con GPU dedicada).
- **Tipo de GPU**: CUDA (NVIDIA), MPS (Apple Silicon) o solo CPU.
- **Espacio en disco** disponible.

Cada nivel se clasifica con un código de color:
- 🟢 **Verde** (recomendado): la RAM supera el umbral holgado.
- 🟡 **Amarillo** (justo): funciona pero con margen limitado.
- 🔴 **Rojo** (no recomendado): RAM o disco insuficientes.

En Apple Silicon la memoria es unificada (GPU = RAM total), por lo que se
usa toda la RAM como referencia. En sistemas CUDA se usa la VRAM de la GPU.

### Aceleración GPU (n_gpu_layers)

| Plataforma | `n_gpu_layers` | Notas |
|------------|----------------|-------|
| Apple Silicon (MPS) | `-1` (todas) | Memoria unificada; Metal acelera todas las capas |
| NVIDIA (CUDA) | `-1` (todas) | Offload completo a VRAM |
| Solo CPU | `0` | Sin aceleración GPU |

> **Nota histórica**: durante el desarrollo se usó `n_gpu_layers=1` para
> MPS, lo que provocaba que solo 1 capa fuese a Metal y el resto corriese
> en CPU — ralentizando modelos ≥7B hasta hacerlos inviables en el
> benchmark. Con `-1` un Apple Silicon con 16 GB mueve el 14B (~8.6 GB)
> con latencias de ~1-3 s por llamada.

### Benchmark integrado

Tras descargar un modelo, se ejecuta automáticamente un benchmark de 45
segundos con una partida demo IA-vs-IA:
- Dos paletas controladas por IA juegan mientras el LLM genera narraciones
  cada 8 segundos en segundo plano.
- Se miden FPS y latencia LLM en tiempo real.
- **Criterios de aprobación**: FPS medio ≥ 30, latencia LLM ≤ 15 s, al
  menos 2 llamadas completadas.
- Si el benchmark falla, el sistema ofrece automáticamente el nivel
  inmediatamente inferior (cascade de fallback).

### Descarga con progreso

- **Nivel 1 (3B)**: archivo único, descarga HTTP directa con barra de
  progreso en MB.
- **Niveles 2-5 (split)**: se consulta la API de HuggingFace para obtener
  la lista de partes y sus tamaños, y se descarga cada parte por HTTP
  directo con progreso acumulado real (MB descargados / MB totales).

### Limpieza de modelos

Al seleccionar un modelo nuevo, si existen modelos anteriores descargados,
el sistema muestra un diálogo ofreciendo eliminarlos para liberar espacio.
Los archivos split se agrupan y eliminan como unidad.
