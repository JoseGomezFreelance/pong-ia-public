# Investigación: Compatibilidad LLM en CPUs sin AVX2

**Fecha:** 2026-03-28
**Contexto:** PongIA ya implementa un Tier 0 oculto (Qwen 2.5 1.5B, commit `ee7d949`) como fallback para hardware limitado. Esta investigación evalúa qué ocurre con CPUs aún más antiguas que carecen de instrucciones AVX2 (pre-Haswell, ~2013), y si es viable ofrecer narración IA en ellas.

---

## Índice

1. [Requisitos SIMD de llama-cpp-python](#1-requisitos-simd-de-llama-cpp-python)
2. [Soporte de llama.cpp para CPUs pre-AVX2](#2-soporte-de-llamacpp-para-cpus-pre-avx2)
3. [Runtimes alternativos para CPUs sin AVX2](#3-runtimes-alternativos-para-cpus-sin-avx2)
4. [Modelos tiny viables para Tier -1](#4-modelos-tiny-viables-para-tier--1)
5. [Opciones de implementación para PongIA](#5-opciones-de-implementación-para-pongia)
6. [Estado actual de `system_info.py`](#6-estado-actual-de-system_infopy)
7. [Conclusión y recomendación](#7-conclusión-y-recomendación)
8. [Adenda A: Auditoría de Seguridad de ONNX Runtime](#adenda-a-auditoría-de-seguridad-de-onnx-runtime-onnxruntime)

---

## 1. Requisitos SIMD de llama-cpp-python

### ¿Requiere AVX2?

**AVX2 no es un requisito formal, pero sí el default de compilación.** CMake habilita `GGML_AVX2=ON` y `GGML_FMA=ON` por defecto, incluso si la CPU del sistema no los soporta.

**Consecuencia práctica:** Si instalas `pip install llama-cpp-python` en una CPU sin AVX2, el resultado es un **crash con `SIGILL` (Illegal Instruction)** al importar el módulo. Los wheels de PyPI se compilan con instrucciones nativas de la máquina que lo compila (que normalmente tiene AVX2).

**No existen wheels pre-construidos oficiales para SSE4-only** en PyPI.

### Flags CMAKE para controlar SIMD

| Flag | Default | Descripción |
|------|---------|-------------|
| `GGML_NATIVE` | ON | Optimiza para la CPU del sistema actual |
| `GGML_AVX` | ON | Instrucciones AVX |
| `GGML_AVX2` | ON | Instrucciones AVX2 |
| `GGML_AVX512` | OFF | Instrucciones AVX-512 |
| `GGML_FMA` | ON | Fused Multiply-Add |
| `GGML_F16C` | ON | Conversión float16 |

> **Nota:** Versiones antiguas de llama.cpp usaban prefijo `LLAMA_` (ej: `LLAMA_AVX2`). Las actuales usan `GGML_`.

**Comando para build SSE4-only:**
```bash
CMAKE_ARGS="-DGGML_NATIVE=OFF -DGGML_AVX=OFF -DGGML_AVX2=OFF -DGGML_FMA=OFF -DGGML_F16C=OFF" \
  FORCE_CMAKE=1 \
  pip install llama-cpp-python --force-reinstall --no-cache-dir
```

### Fuentes
- [Issue #1583 — CMake assumes AVX2](https://github.com/ggml-org/llama.cpp/issues/1583)
- [Issue #284 — cmake ignores DLLAMA_AVX2=OFF](https://github.com/abetlen/llama-cpp-python/issues/284)
- [Discussion #833 — Illegal hardware instruction](https://github.com/abetlen/llama-cpp-python/discussions/833)

---

## 2. Soporte de llama.cpp para CPUs pre-AVX2

### Dynamic CPU Dispatch

llama.cpp tiene un sistema de **dispatch dinámico de CPU** (compilando con `GGML_BACKEND_DL=ON` y `GGML_CPU_ALL_VARIANTS=ON`). Genera múltiples variantes de backend (SSE4.2, AVX, AVX2, AVX512) y selecciona la mejor en runtime. Sin embargo, **esto no se activa automáticamente en llama-cpp-python vía pip.**

### Problema conocido: instrucciones AVX "filtradas"

En el [Issue #6723](https://github.com/ggml-org/llama.cpp/issues/6723), un usuario reportó que incluso compilando con `-DLLAMA_AVX=OFF -DLLAMA_AVX2=OFF -DLLAMA_FMA=OFF -DLLAMA_F16C=OFF`, el binario resultante aún contenía instrucciones AVX (`vmovdqu8`). El issue fue **cerrado por inactividad, no por solución.**

### Penalidad de rendimiento SSE4 vs AVX2

- AVX2 usa registros de 256 bits vs 128 bits de SSE4.2.
- En la práctica, la diferencia es de **~2x a 4x** en operaciones de multiplicación de matrices (cuello de botella en inferencia LLM).
- Para un modelo pequeño (1.5B parámetros), la penalidad es tolerable. Para modelos mayores es significativa.

### Wheels de la comunidad (jllllll)

El repositorio de **jllllll** ofrece wheels con variantes específicas:

```bash
# Build "basic" (sin AVX/FMA/F16C) — CPU only, máxima compatibilidad
pip install llama-cpp-python --prefer-binary \
  --extra-index-url=https://jllllll.github.io/llama-cpp-python-cuBLAS-wheels/basic/cpu

# Build AVX-only (sin AVX2) — CPU only
pip install llama-cpp-python --prefer-binary \
  --extra-index-url=https://jllllll.github.io/llama-cpp-python-cuBLAS-wheels/AVX/cpu
```

**Riesgo:** Repositorio de terceros sin garantía de mantenimiento a largo plazo.

### Fuentes
- [Discussion #7723 — AVX2 minimum requirement?](https://github.com/ggml-org/llama.cpp/discussions/7723)
- [Issue #6723 — AVX instructions without AVX support](https://github.com/ggml-org/llama.cpp/issues/6723)
- [DeepWiki — CPU Backend and Optimization](https://deepwiki.com/ggml-org/llama.cpp/4.2-cpu-backend-and-optimization)
- [jllllll/llama-cpp-python-cuBLAS-wheels](https://github.com/jllllll/llama-cpp-python-cuBLAS-wheels)

---

## 3. Runtimes alternativos para CPUs sin AVX2

### Tabla comparativa

| Runtime | Min SIMD | Peso pip | Modelos compatibles | Viabilidad |
|---------|----------|----------|---------------------|------------|
| **ONNX Runtime** | SSE2 (dispatch dinámico) | ~15 MB | GPT-2, DistilGPT-2, TinyStories | **Alta** |
| PyTorch/Transformers | AVX2 (FBGEMM) | ~300 MB | Todos HF | **Baja** |
| KoboldCpp (failsafe) | Ninguno | ~50 MB exe | GGUF cualquiera | Media |
| ctransformers | AVX2 (ggml) | — | GGUF | Baja (abandonado) |
| tinygrad | Sin documentar | — | Sin ecosistema LLM | No práctica |

### ONNX Runtime — La opción más prometedora

- Usa **dispatch dinámico de instrucciones** en runtime: selecciona automáticamente SSE2 → AVX → AVX2 → AVX512 según la CPU detectada.
- La línea base es **SSE2**, ya que existen implementaciones de operadores clave usando SSE2 y NEON.
- Paquete ligero: ~15 MB el wheel de CPU (`pip install onnxruntime`).
- API Python limpia, sin compilar nada.
- Soporte oficial para GPT-2 con notebooks de ejemplo de Microsoft.
- **No requiere internet para funcionar.**

```python
from optimum.onnxruntime import ORTModelForCausalLM
from transformers import AutoTokenizer, pipeline

model = ORTModelForCausalLM.from_pretrained("optimum/gpt2")
tokenizer = AutoTokenizer.from_pretrained("optimum/gpt2")
gen = pipeline("text-generation", model=model, tokenizer=tokenizer)
result = gen("Once upon a time")
```

> **Nota:** `optimum` depende de `transformers` que depende de PyTorch. Para evitar PyTorch, se puede usar la API directa de `onnxruntime.InferenceSession`.

**Fuentes:**
- [ONNX Runtime Issue #7010 — SSE/AVX support](https://github.com/microsoft/onnxruntime/issues/7010)
- [ONNX Runtime GPT-2 CPU notebook](https://github.com/microsoft/onnxruntime/blob/main/onnxruntime/python/tools/transformers/notebooks/Inference_GPT2_with_OnnxRuntime_on_CPU.ipynb)

### PyTorch — Problemático

Los binarios precompilados de pip causan **"Illegal Instruction"** en CPUs sin AVX2 por la librería FBGEMM. Compilar desde source sin AVX2 es posible pero tedioso (1+ hora). No recomendado.

**Fuentes:**
- [PyTorch Issue #94021 — Set AVX2 as minimum](https://github.com/pytorch/pytorch/issues/94021)
- [PyTorch Issue #32724 — Illegal Instruction without AVX2](https://github.com/pytorch/pytorch/issues/32724)

### KoboldCpp — Alternativa con proceso externo

Ofrece tres modos para hardware viejo:
1. **NoAVX2** (`--noavx2`): usa instrucciones AVX1
2. **oldcpu** (`koboldcpp_oldcpu.exe`): CPUs sin AVX2
3. **Failsafe** (`--failsafe`): desactiva TODAS las intrinsics. Funciona en cualquier CPU x86.

**Problema:** Es un ejecutable standalone, no una librería Python. La integración requeriría lanzar un proceso externo y comunicarse vía HTTP API.

**Fuentes:**
- [KoboldCpp Discussion #1068](https://github.com/LostRuins/koboldcpp/discussions/1068)
- [KoboldCpp Issue #501 — NoAVX2 and Failsafe modes](https://github.com/LostRuins/koboldcpp/issues/501)

---

## 4. Modelos tiny viables para Tier -1

### Candidatos

| Modelo | Parámetros | Peso ONNX | Calidad texto | Ideal para |
|--------|-----------|-----------|---------------|------------|
| **TinyStories-33M** | 33M | ~130 MB FP32 | Historias coherentes, gramática correcta | **Mejor candidato** |
| TinyStories-8M | 8M | ~32 MB | Historias simples, vocab limitado | Ultra-low spec |
| DistilGPT-2 | 82M | ~170 MB INT8 | Texto general bueno | Más versatilidad |
| GPT-2 Small | 124M | ~187 MB INT8 | Texto general muy bueno | Si hay más RAM |

### TinyStories — Especialmente interesante

Los modelos TinyStories se entrenaron específicamente para generar **historias cortas y coherentes** con vocabulario limitado:
- **TinyStories-33M:** Solo 130 MB, produce texto fluido y gramaticalmente correcto.
- **TinyStories-8M:** Solo 32 MB, calidad de vocabulario de niño de 3-4 años.
- Incluso modelos de 3M parámetros producen texto coherente.
- Son convertibles a formato ONNX.

**Limitaciones:** Solo generan texto en inglés con vocabulario de historias infantiles. Para la narración de partidas de Pong puede funcionar, pero el estilo narrativo será limitado.

### Cuantización

GPT-2 FP32 pesa ~511 MB; cuantizado a INT8 baja a ~187 MB. Sin embargo, en CPUs viejos sin VNNI, la cuantización INT8 puede no dar mejora de velocidad (e incluso ser más lenta por overhead de des/cuantización).

**Fuentes:**
- [TinyStories paper (arXiv)](https://arxiv.org/abs/2305.07759)
- [TinyStories-33M en Hugging Face](https://huggingface.co/roneneldan/TinyStories-33M)
- [DistilGPT-2 en Hugging Face](https://huggingface.co/distilbert/distilgpt2)
- [GPT-2 ONNX quantized](https://huggingface.co/brianwoo/GPT2-Onnx-Quantized)

---

## 5. Opciones de implementación para PongIA

### Opción A — ONNX Runtime + TinyStories (recomendada si se quiere Tier -1)

- Añadir `onnxruntime` como dependencia opcional (~15 MB).
- Incluir o descargar TinyStories-33M en formato ONNX (~130 MB).
- Si no hay AVX2 → usar este stack en vez de llama-cpp-python.
- **Pro:** Máxima compatibilidad, paquete ligero, buena calidad narrativa.
- **Con:** Dependencia nueva, modelo solo genera inglés/historias simples.

### Opción B — llama-cpp-python con wheels SSE4 (comunidad)

- Instalar desde los wheels de jllllll (variante "basic" o "AVX").
- **Pro:** Misma arquitectura que los tiers normales, mismo modelo Qwen.
- **Con:** Dependencia de un repo de terceros, no garantizado, issue #6723 sin resolver.

### Opción C — Mensaje "CPU no compatible" (mínimo esfuerzo)

- Detectar falta de AVX2 → mostrar aviso → desactivar narración IA.
- **Pro:** Cero complejidad adicional, sin riesgo de bugs.
- **Con:** Peor experiencia de usuario.

### Opción D — KoboldCpp como proceso externo

- Incluir koboldcpp en modo failsafe, comunicación vía HTTP localhost.
- **Pro:** Funciona en cualquier CPU x86.
- **Con:** Complejo de empaquetar, proceso externo, overhead.

---

## 6. Estado actual de `system_info.py`

### Lo que ya se detecta

El dataclass `SystemInfo` actualmente incluye:
- `total_ram_gb`, `available_ram_gb` — RAM total y disponible
- `unified_memory` — Flag Apple Silicon
- `gpu_name`, `gpu_type`, `gpu_vram_gb` — GPU (MPS/CUDA/CPU)
- `disk_free_gb` — Espacio libre en directorio de modelos
- `cpu_name`, `cpu_cores` — Nombre y cores de CPU

### Lo que falta

**No se detectan flags de instrucciones SIMD.** No hay campos para AVX, AVX2, SSE4, ni ninguna extensión de instrucciones.

### Cambios necesarios (independientes de la opción elegida)

1. Añadir campos al dataclass:
   - `has_sse42: bool`
   - `has_avx: bool`
   - `has_avx2: bool`

2. Implementar `_detect_cpu_capabilities()`:
   - **Linux:** Leer `/proc/cpuinfo` (campo `flags`)
   - **macOS:** `sysctl -a machdep.cpu.features` y `machdep.cpu.leaf7_features`
   - **Windows:** `cpuid` vía ctypes o registro del sistema

3. Integrar en el flujo de evaluación de tiers (`llm_tiers.py`):
   - Si `has_avx2 == False` → mostrar aviso antes de intentar cargar llama-cpp-python.

---

## 7. Conclusión y recomendación

**Base obligatoria (todas las opciones):** Implementar detección de AVX2 en `system_info.py` y mostrar un aviso claro si la CPU no lo soporta. Esto es necesario independientemente de si ofrecemos un Tier -1 o no.

**Sobre el Tier -1:** La decisión depende de la audiencia:

| Escenario | Recomendación |
|-----------|---------------|
| Público general (gaming) | **Opción C** — aviso + desactivar narración. CPUs pre-2013 son <5% del mercado. |
| PCs escolares/mercados emergentes | **Opción A** — ONNX Runtime + TinyStories. Inversión razonable (~145 MB extra). |
| Máxima cobertura sin complejidad | **Opción C ahora**, evaluar Opción A más adelante si hay demanda. |

**Stack recomendado si se elige Opción A:** `onnxruntime` (15 MB) + TinyStories-33M en ONNX (~130 MB). Ver [Adenda A](#adenda-a-auditoría-de-seguridad-de-onnx-runtime-onnxruntime) para el análisis de seguridad completo de onnxruntime.

---

---

## Adenda A: Auditoría de Seguridad de ONNX Runtime (`onnxruntime`)

**Fecha:** 2026-03-28
**Contexto:** Evaluación de `onnxruntime` como runtime alternativo para CPUs sin AVX2 en PongIA (Tier -1 fallback).

---

### A.1. Legitimidad del Proyecto

| Aspecto | Detalle |
|---------|---------|
| **Mantenedor** | Microsoft (cuenta verificada en PyPI, repo en `github.com/microsoft/onnxruntime`) |
| **Contacto** | `onnxruntime@microsoft.com` |
| **Licencia** | MIT |
| **GitHub Stars** | ~19,500+ |
| **Contribuidores** | 170+ |
| **Última versión** | v1.24.4 (17 marzo 2026) |
| **Cadencia de releases** | Múltiples por año, con parches de seguridad intermedios |
| **Uso interno Microsoft** | Office, Azure, Bing, Xbox |
| **ONNX Foundation** | El formato ONNX es proyecto graduado de la LF AI Foundation (Linux Foundation). El runtime es un proyecto separado de Microsoft |

**Veredicto:** Proyecto legítimo con respaldo corporativo fuerte y uso extensivo en producción.

---

### A.2. Seguridad de la Cadena de Suministro (Supply Chain)

#### Publicación en PyPI
- Publicado por la cuenta **"microsoft"** verificada en PyPI.
- **No usa Trusted Publishing** (OIDC). Esto es una debilidad: el mecanismo recomendado por PyPI desde 2023 elimina la necesidad de tokens de API almacenados. Ni PyTorch, ni TensorFlow, ni llama-cpp-python lo usan tampoco.
- Los wheels no están firmados criptográficamente de forma independiente.
- No se encontró evidencia de builds reproducibles.

#### Incidentes conocidos
- **No se han documentado ataques de supply chain contra el paquete `onnxruntime` en PyPI.**
- **No se han encontrado paquetes typosquat específicos** imitando a onnxruntime.
- En 2024 hubo una campaña masiva de typosquatting en PyPI (500+ paquetes), pero onnxruntime no fue objetivo documentado.
- **"ONNX Store" (phishing-as-a-service):** Criminales usurparon la marca "ONNX" para phishing en 2024. **No tiene relación técnica con el software.** Microsoft incautó 256 sitios fraudulentos en noviembre 2024.

#### Dependencias Python
Las dependencias son mínimas para un paquete de ML:
- Requiere Python >= 3.11 (v1.24.4)
- Los wheels contienen bibliotecas C++ compiladas (abseil, protobuf, re2)
- Protobuf se enlaza estáticamente en Windows
- No depende de PyTorch ni TensorFlow

**Veredicto:** Riesgo de supply chain bajo-medio. La falta de Trusted Publishing es una debilidad compartida con toda la industria de ML en Python.

---

### A.3. CVEs y Vulnerabilidades Conocidas

#### A.3.1 CVEs directos de ONNX Runtime

Microsoft **no publica advisories GHSA** en el repositorio. Las correcciones se incluyen silenciosamente en releases sin asignar CVEs públicos. Esto dificulta el rastreo pero las correcciones llegan en semanas.

**CVE-2022-1941 — DoS vía Protobuf (dependencia)**
- CVSS: 7.5 (Alta)
- Mensajes protobuf maliciosamente construidos causan out-of-memory
- Corregido en protobuf >= 3.18.3 / 3.19.5 / 3.20.2 / 3.21.6

**Correcciones de seguridad en v1.24.3 (marzo 2025, sin CVE público):**

| Operación | Tipo de vulnerabilidad | PR |
|-----------|----------------------|-----|
| GatherCopyData | Truncación de entero → heap OOB read/write | #27444 |
| RoiAlign | Heap OOB read por batch_indices sin validar | #27543 |
| Lora Adapters | Heap OOB por adaptadores LoRA maliciosos | #27518 |
| Resize | Acceso out-of-bounds | #27419 |
| ArrayFeatureExtractor | Lectura out-of-bounds | #27275 |
| GatherND | División por cero (mismatch dimensiones batch) | — |

**Tipos predominantes:** Heap buffer overflow, out-of-bounds read/write. **No se han reportado RCE directos** en onnxruntime.

#### A.3.2 CVEs del formato ONNX (paquete `onnx`, dependencia)

Estos afectan al paquete `onnx`, no directamente al runtime, pero son relevantes porque onnxruntime carga archivos `.onnx`:

| CVE | CVSS | Tipo | Versiones afectadas | Fix |
|-----|------|------|---------------------|-----|
| CVE-2022-25882 | 7.5 | Path Traversal vía external_data | onnx <= 1.13.0 | >= 1.13.1 |
| CVE-2024-27318 | 7.5 | Path Traversal (bypass del anterior) | onnx <= 1.15.0 | >= 1.16.0 |
| CVE-2024-27319 | Media | OOB Read en assertions | onnx 1.1.0–1.15.0 | >= 1.16.0 |
| CVE-2024-5187 | 8.1 | File Overwrite vía tar malicioso | onnx < 1.16.2 | >= 1.16.2 |
| CVE-2024-7776 | 9.1 | Path Traversal en download_model | onnx <= 1.16.1 | >= 1.16.2 |
| CVE-2025-51480 | 8.8 | Path Traversal en save_external_data | onnx <= 1.17.0 | Parche en master |
| CVE-2026-28500 | Media-Alta | Bypass seguridad en onnx.hub.load() | onnx <= 1.20.1 | Sin parche |

#### A.3.3 Velocidad de parcheado
Las correcciones llegan generalmente en la siguiente release (semanas). Sin embargo, la falta de CVEs públicos para bugs del runtime dificulta el seguimiento automatizado con herramientas como Dependabot o Safety CLI.

**Veredicto:** Historial de vulnerabilidades moderado. Los bugs son típicos de código C++ de procesamiento de datos (heap overflows, path traversal). No hay evidencia de RCE directo. El patrón de CVEs sin publicar es preocupante desde el punto de vista de transparencia.

---

### A.4. Prácticas de Seguridad del Proyecto

| Práctica | Estado |
|----------|--------|
| **SECURITY.md** | Sí — redirige al MSRC (Microsoft Security Response Center) |
| **Bug Bounty** | Sí — programa de Microsoft |
| **Respuesta comprometida** | 24 horas |
| **Coordinated Vulnerability Disclosure** | Sí |
| **OSS-Fuzz (Google)** | **No confirmado** — los heap OOB encontrados sugieren gaps en fuzzing |
| **OneFuzz (Microsoft)** | Posible pero sin confirmación pública |
| **CI/CD** | GitHub Actions, tests multi-plataforma extensivos |
| **Code review** | Obligatorio (repo Microsoft estándar) |

**Veredicto:** Prácticas de seguridad corporativas sólidas, pero la falta de integración confirmada con OSS-Fuzz es una debilidad.

---

### A.5. Privacidad y Telemetría

#### Hallazgo clave: Telemetría en Windows

Según la [documentación oficial de privacidad](https://github.com/microsoft/onnxruntime/blob/main/docs/Privacy.md):

| Plataforma | Telemetría | Estado por defecto |
|------------|-----------|-------------------|
| **Windows** | Sí (TraceLogging API) | **Activada** |
| **Linux** | No implementada | N/A |
| **macOS** | No implementada | N/A |

**Importante para PongIA:** Un maintainer clarificó en [issue #3898](https://github.com/microsoft/onnxruntime/issues/3898) que **la telemetría está en el paquete NuGet (C#), no en el de pip (Python)**. Sin embargo, la documentación oficial no hace esta distinción explícita.

#### Problema: Imposibilidad de desactivar completamente (Windows)
[Issue #25573](https://github.com/microsoft/onnxruntime/issues/25573): `DisableTelemetryEvents()` requiere crear un `OrtEnv` primero, pero la creación del environment ya envía telemetría vía `LogProcessInfo()`. Sin respuesta oficial de Microsoft.

#### Cómo desactivar telemetría
1. **Compilar desde source** con `onnxruntime_USE_TELEMETRY=OFF` (eliminación total)
2. API Python: `session.disable_telemetry_events()` (reduce pero no elimina en Windows)
3. Configuración de telemetría de Windows a nivel OS

#### Conexiones de red
- **No requiere internet** para instalación (pip descarga el wheel y listo) ni para inferencia.
- No se encontró evidencia de conexiones de red durante el runtime fuera de la telemetría de Windows.
- No hay analytics ni tracking web embebido.

**Veredicto para PongIA:**
- **En macOS:** Sin impacto. No hay telemetría implementada.
- **En Windows (builds pip):** Riesgo bajo según el maintainer, pero la documentación es ambigua. Recomendable llamar a `disable_telemetry_events()` como precaución.

---

### A.6. Seguridad del Formato de Modelo ONNX

#### Diseño del formato
ONNX es un formato **declarativo** basado en Protocol Buffers. A diferencia de pickle (PyTorch), **no permite ejecución de código arbitrario** por diseño. Define grafos de operaciones matemáticas, no código ejecutable.

#### Vectores de ataque conocidos (modelos maliciosos)

| Vector | Riesgo | Mitigación |
|--------|--------|------------|
| **Path traversal vía external_data** | Alto — lectura/escritura de archivos arbitrarios | Usar onnx >= 1.16.2 |
| **Custom operators (C++/CUDA)** | Alto — ejecución de código nativo al cargar | No cargar modelos con custom ops de fuentes no confiables |
| **Metadata_props con payload** | Medio — requiere que el código procese activamente los metadatos | No ejecutar contenido de metadatos como código |
| **Backdoors arquitecturales** | Bajo — rutas paralelas ocultas en el grafo del modelo | Validar modelos con herramientas de inspección |
| **onnx.hub.load(silent=True)** | Medio — descarga sin verificación | No usar silent=True; no aplica a PongIA |

#### Relevancia para PongIA
**Baja.** PongIA solo cargará modelos que nosotros mismos generamos/descargamos de Hugging Face (fuentes confiables). No hay carga de modelos de usuarios o fuentes no confiables.

---

### A.7. Comparación de Seguridad con Alternativas

| Aspecto | onnxruntime | PyTorch | llama-cpp-python |
|---------|-------------|---------|------------------|
| **Formato de modelo** | ONNX (declarativo) | Pickle (**ejecutable**) | GGUF (binario) |
| **RCE vía modelo** | Difícil (solo vía custom ops) | **Trivial** (pickle deserialización) | CVE-2024-34359 CVSS 9.7 (Jinja2) |
| **CVEs críticos recientes** | Heap OOB (sin CVE público) | Múltiples | CVSS 9.7 RCE |
| **Telemetría** | Solo Windows/NuGet | No | No |
| **Peso pip** | ~15 MB | ~300 MB | ~5 MB (+ compilación) |
| **Trusted Publisher PyPI** | No | No | No |
| **Bug Bounty** | Sí (MSRC) | No formal | No |
| **OSS-Fuzz** | No confirmado | Sí | No |
| **Gobernanza** | Microsoft | Meta (PyTorch Foundation) | Comunidad (1 mantenedor) |

**onnxruntime es más seguro que PyTorch** (formato declarativo vs pickle) y **más seguro que llama-cpp-python** (que tuvo un RCE trivial CVSS 9.7). Es comparable a TensorFlow en postura general.

---

### A.8. Evaluación de Riesgo para PongIA

#### Contexto de uso
- Cargar un modelo propio (TinyStories o DistilGPT-2) convertido a ONNX
- Inferencia local, sin red, sin modelos de terceros no confiables
- Plataformas: macOS y Windows

#### Matriz de riesgo

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| Supply chain (paquete PyPI comprometido) | Muy baja | Alto | Fijar versión en requirements, verificar hashes |
| CVE en operaciones ONNX (heap OOB) | Baja (requiere modelo malicioso) | Medio | Solo cargar modelos propios, mantener actualizado |
| Telemetría filtrando datos | Muy baja (no aplica en pip/macOS) | Bajo | `disable_telemetry_events()` en Windows como precaución |
| Path traversal vía modelo | Nula (no cargamos modelos externos) | Alto | N/A — no aplica |
| Dependencia abandonada | Muy baja (Microsoft activo) | Medio | Monitorear releases |

#### Conclusión de seguridad

**onnxruntime es una dependencia razonablemente segura para PongIA.** Los riesgos principales (modelos maliciosos, path traversal) no aplican porque solo cargaremos nuestros propios modelos. La telemetría no afecta a la distribución pip en macOS, y en Windows se puede mitigar con una llamada a la API.

**Recomendaciones si se adopta:**
1. Fijar versión mínima: `onnxruntime >= 1.24.3` (incluye parches de seguridad)
2. Fijar versión mínima de onnx: `onnx >= 1.16.2` (si se usa como dependencia directa)
3. Llamar a `session.disable_telemetry_events()` al crear sesiones en Windows
4. No cargar modelos ONNX de fuentes no confiables
5. Monitorear releases para parches de seguridad (no publicados como CVE)

---

## Fuentes

### llama.cpp y llama-cpp-python
- [Issue #1583 — CMake assumes AVX2](https://github.com/ggml-org/llama.cpp/issues/1583)
- [Issue #284 — cmake ignores DLLAMA_AVX2=OFF](https://github.com/abetlen/llama-cpp-python/issues/284)
- [Discussion #833 — Illegal hardware instruction](https://github.com/abetlen/llama-cpp-python/discussions/833)
- [Discussion #7723 — AVX2 minimum requirement?](https://github.com/ggml-org/llama.cpp/discussions/7723)
- [Issue #6723 — AVX instructions without AVX support](https://github.com/ggml-org/llama.cpp/issues/6723)
- [DeepWiki — CPU Backend and Optimization](https://deepwiki.com/ggml-org/llama.cpp/4.2-cpu-backend-and-optimization)
- [jllllll/llama-cpp-python-cuBLAS-wheels](https://github.com/jllllll/llama-cpp-python-cuBLAS-wheels)
- [Intel Community — AVX vs SSE4.2 performance](https://community.intel.com/t5/Intel-Fortran-Compiler/AVX-vs-SSE4-2-performance-on-Sandybridge/m-p/957619)

### Runtimes alternativos
- [ONNX Runtime Issue #7010 — SSE/AVX support](https://github.com/microsoft/onnxruntime/issues/7010)
- [ONNX Runtime GPT-2 CPU notebook](https://github.com/microsoft/onnxruntime/blob/main/onnxruntime/python/tools/transformers/notebooks/Inference_GPT2_with_OnnxRuntime_on_CPU.ipynb)
- [PyTorch Issue #94021 — Set AVX2 as minimum](https://github.com/pytorch/pytorch/issues/94021)
- [PyTorch Issue #32724 — Illegal Instruction without AVX2](https://github.com/pytorch/pytorch/issues/32724)
- [KoboldCpp Discussion #1068](https://github.com/LostRuins/koboldcpp/discussions/1068)
- [KoboldCpp Issue #501 — NoAVX2 and Failsafe modes](https://github.com/LostRuins/koboldcpp/issues/501)

### Modelos
- [TinyStories paper (arXiv)](https://arxiv.org/abs/2305.07759)
- [TinyStories-33M en Hugging Face](https://huggingface.co/roneneldan/TinyStories-33M)
- [DistilGPT-2 en Hugging Face](https://huggingface.co/distilbert/distilgpt2)
- [GPT-2 ONNX quantized](https://huggingface.co/brianwoo/GPT2-Onnx-Quantized)

### ONNX Runtime — Oficiales
- [microsoft/onnxruntime (GitHub)](https://github.com/microsoft/onnxruntime)
- [onnxruntime (PyPI)](https://pypi.org/project/onnxruntime/)
- [Privacy.md oficial](https://github.com/microsoft/onnxruntime/blob/main/docs/Privacy.md)
- [SECURITY.md](https://github.com/microsoft/onnxruntime/blob/main/SECURITY.md)
- [Release v1.24.3 — Security fixes](https://github.com/microsoft/onnxruntime/releases/tag/v1.24.3)

### ONNX Runtime — CVEs y Advisories
- [CVE-2022-1941 (NVD)](https://nvd.nist.gov/vuln/detail/cve-2022-1941)
- [CVE-2022-25882 (Snyk)](https://security.snyk.io/vuln/SNYK-PYTHON-ONNX-2395479)
- [CVE-2024-27318 (NVD)](https://nvd.nist.gov/vuln/detail/CVE-2024-27318)
- [CVE-2024-27319 — HiddenLayer Advisory](https://hiddenlayer.com/sai-security-advisory/2024-02-onnx/)
- [CVE-2024-5187 (GHSA-6rq9-53c3-f7vj)](https://github.com/advisories/GHSA-6rq9-53c3-f7vj)
- [CVE-2024-7776 (Wiz)](https://www.wiz.io/vulnerability-database/cve/cve-2024-7776)
- [CVE-2025-51480 (Gecko Security)](https://www.gecko.security/blog/cve-2025-51480)
- [CVE-2026-28500 (GitLab Advisory)](https://advisories.gitlab.com/pkg/pypi/onnx/CVE-2026-28500/)
- [CVE-2024-34359 — llama-cpp-python RCE (GHSA-56xg-wfcc-g829)](https://github.com/advisories/GHSA-56xg-wfcc-g829)

### ONNX Runtime — Telemetría e Issues
- [Issue #3898 — Telemetry clarification](https://github.com/microsoft/onnxruntime/issues/3898)
- [Issue #25573 — Cannot fully disable telemetry](https://github.com/microsoft/onnxruntime/issues/25573)
- [Discussion #16879](https://github.com/microsoft/onnxruntime/discussions/16879)

### ONNX Runtime — Seguridad de modelos
- [RCE vía ONNX metadata PoC](https://github.com/Michael-Obs66/RCE-Via-Metadata-ONNX-Model)
- [Hunting vulns in ML model formats](https://blog.huntr.com/hunting-vulnerabilities-in-machine-learning-model-file-formats)
- [ProtectAI — ONNX backdoor threats](https://protectai.com/insights/knowledge-base/backdoor-threats/PAIT-ONNX-200)

### ONNX Runtime — Incidentes
- [ONNX Store phishing (EclecticIQ)](https://blog.eclecticiq.com/onnx-store-targeting-financial-institution)
- [Microsoft disrupts ONNX phishing (BleepingComputer)](https://www.bleepingcomputer.com/news/security/microsoft-disrupts-onnx-phishing-as-a-service-infrastructure/)
- [Typosquatting PyPI 2024 (Check Point)](https://blog.checkpoint.com/securing-the-cloud/pypi-inundated-by-malicious-typosquatting-campaign/)

---

---

## Adenda B: Auditoría de Seguridad de `tokenizers` (HuggingFace)

**Fecha:** 2026-03-29
**Contexto:** Evaluación de `tokenizers` como tokenizador para el provider ONNX (Tier -1). Se necesita tokenizar/detokenizar texto para DistilGPT-2 o TinyStories-33M sin depender de PyTorch ni de `transformers`.

---

### B.1. Legitimidad del Proyecto

| Aspecto | Detalle |
|---------|---------|
| **Mantenedor** | Hugging Face, Inc. (Nueva York, >$200M en financiación) |
| **Repo** | `github.com/huggingface/tokenizers` |
| **Licencia** | Apache 2.0 |
| **GitHub Stars** | ~10,600+ |
| **Contribuidores** | 146+ |
| **Última versión** | v0.22.2 (enero 2026) |
| **Cadencia de releases** | Cada 2-4 meses |
| **Lenguaje** | Core en Rust, bindings Python vía PyO3 |
| **PyPI** | 5 maintainers verificados (empleados de HF) |
| **SLSA Attestations** | Sí — 405 attestations para v0.22.2 (verificación criptográfica de provenance) |

**Veredicto:** Proyecto legítimo con respaldo corporativo fuerte y uso masivo en el ecosistema ML.

---

### B.2. Seguridad de la Cadena de Suministro (Supply Chain)

#### Publicación en PyPI
- Publicado por 5 maintainers verificados: ArthurZucker, danieldk, McPotato, Nicolas.Patry, xn1t0x (empleados de HF).
- **No usa Trusted Publishing** (OIDC). Los wheels se suben con tokens convencionales. Debilidad compartida con toda la industria ML.
- **Sí tiene SLSA Attestations** — esto permite verificar criptográficamente que los wheels fueron construidos desde el repo oficial vía CI. Es mejor que la mayoría de paquetes ML.
- No se encontró evidencia de builds reproducibles bit-a-bit.

#### Incidentes conocidos
- **No se han documentado ataques de supply chain contra el paquete `tokenizers` en PyPI.**
- En 2023 hubo un caso de "slopsquatting" con `huggingface-cli` (nombre inexistente que LLMs alucinaban). No afecta a `tokenizers`.
- Estudios sobre typosquatting en el ecosistema HuggingFace Hub (modelos/datasets) no reportan afectación al paquete pip.

#### Dependencias Python (transitivas)
`tokenizers` requiere `huggingface_hub` como dependencia obligatoria, que arrastra una cadena significativa:

```
tokenizers
└── huggingface_hub
    ├── httpx → httpcore, h11, h2, certifi, idna, sniffio
    ├── fsspec
    ├── filelock
    ├── pyyaml
    ├── tqdm
    ├── typer-slim → shellingham
    ├── hf-xet
    └── packaging, typing-extensions
```

**Esto es preocupante para un juego de escritorio:** la mayoría de estas dependencias (`httpx`, `httpcore`, `fsspec`, `hf-xet`) son innecesarias si solo se usa tokenización offline. Inflará el bundle de PyInstaller en ~12 MB de código de red que no necesitamos.

#### Dependencias Rust (nativas)
Las dependencias del crate son conservadoras: `serde`, `serde_json`, `regex`, `rayon`, `unicode-normalization-alignments`, `aho-corasick`. No hay dependencias sospechosas. La dependencia opcional `onig` (bindings C a Oniguruma) está habilitada por defecto y contiene código nativo no auditado.

**Veredicto:** Riesgo de supply chain bajo. Las SLSA attestations son un punto positivo. La cadena de dependencias transitivas es innecesariamente pesada para nuestro caso de uso.

---

### B.3. CVEs y Vulnerabilidades Conocidas

#### B.3.1 CVEs directos contra `tokenizers`

**CERO.** En [OpenCVE](https://app.opencve.io/cve/?vendor=huggingface), de los 37 CVEs registrados para Hugging Face, **ninguno** afecta al paquete `tokenizers`. Todos afectan a `transformers`, `diffusers` o `smolagents`.

- **GitHub Security Advisories:** [Cero advisories publicados](https://github.com/huggingface/tokenizers/security/advisories) para el repositorio.
- **Snyk:** Sin vulnerabilidades listadas.
- **NVD:** Sin resultados para "tokenizers huggingface".

#### B.3.2 Vulnerabilidad en versión WASM (JavaScript)
Un [análisis de Kodem Security](https://www.kodemsecurity.com/resources/hugging-face-datasets-and-tokenizers-in-javascript-security-issues-for-ai-pipelines) encontró un buffer overflow en `tokenizers` WASM (JavaScript) por manejo incorrecto de secuencias Unicode malformadas. **No afecta al paquete Python/Rust.**

#### B.3.3 Fuzzing
Una [propuesta para integrar OSS-Fuzz](https://github.com/huggingface/tokenizers/issues/1397) fue cerrada sin implementar (diciembre 2023). El core Rust **no tiene fuzzing continuo**, lo cual es una debilidad. Los tipos de bugs que el fuzzing descubriría (panics en edge cases Unicode, OOM por inputs extremos) podrían existir sin ser detectados.

#### B.3.4 Velocidad de parcheado
No aplica dado que no ha habido CVEs que parchar.

**Veredicto:** Historial de vulnerabilidades excelente (cero CVEs). La falta de fuzzing continuo es la principal debilidad, pero el core en Rust proporciona safety de memoria por defecto.

---

### B.4. Privacidad y Telemetría

#### Conexiones de red por operación

| Operación | Conexión a red | Datos enviados |
|-----------|---------------|----------------|
| `import tokenizers` | **No** | Nada |
| `Tokenizer.from_file("tokenizer.json")` | **No** | Nada |
| `Tokenizer.from_str(json_string)` | **No** | Nada |
| `tokenizer.encode("texto")` / `.decode()` | **No** | Nada |
| `Tokenizer.from_pretrained("gpt2")` | **Sí** | User-Agent, nombre del modelo, token HF si existe |

#### Telemetría de `huggingface_hub`
La dependencia `huggingface_hub` incluye [telemetría](https://github.com/huggingface/huggingface_hub/blob/main/src/huggingface_hub/utils/_telemetry.py) que se ejecuta en un thread separado cuando se usan ciertas funciones del Hub. Se desactiva con variables de entorno:
- `HF_HUB_DISABLE_TELEMETRY=1`
- `HF_HUB_OFFLINE=1`

#### Uso completamente offline
**Sí es posible.** Si se usa `Tokenizer.from_file()` o `Tokenizer.from_str()`, el tokenizer opera 100% en memoria, sin conexiones de red, sin telemetría, sin acceso a archivos adicionales.

#### Acceso a archivos
Solo accede a los archivos que se le pasan explícitamente. No escanea directorios ni lee archivos adicionales. No escribe a disco durante tokenización.

**Veredicto para PongIA:**
- Usar siempre `Tokenizer.from_file()` con un `tokenizer.json` pre-incluido en el bundle.
- No usar `from_pretrained()` en producción.
- Setear `HF_HUB_OFFLINE=1` y `HF_HUB_DISABLE_TELEMETRY=1` como precaución.

---

### B.5. Riesgos de Ejecución de Código

#### Formato `tokenizer.json`
Es **JSON puro declarativo**. Contiene:
- Vocabulario (mapeo token → ID)
- Reglas de merge (BPE)
- Configuración de normalizer, pre-tokenizer, post-processor y decoder

**No puede contener código ejecutable.** No usa pickle, no usa `eval`, no soporta callbacks arbitrarios. Se parsea con `serde_json` en Rust, que es un deserializador estricto de JSON.

#### ¿Puede un `tokenizer.json` malicioso ejecutar código?
**No.** Lo peor que podría hacer un `tokenizer.json` malicioso:
- Causar OOM por vocabulario de tamaño extremo
- Producir tokenización incorrecta

#### `trust_remote_code`
El paquete `tokenizers` standalone **no soporta `trust_remote_code`**. Solo `transformers.AutoTokenizer` soporta esa funcionalidad, y requiere `trust_remote_code=True` explícito. No es un vector de ataque en nuestro caso.

#### Bloques `unsafe` en Rust
- El core de tokenizers usa Rust safe por defecto.
- Las dependencias `onig` (bindings C a Oniguruma) y `esaxx-rs` contienen FFI unsafe.
- PyO3 (bindings Python) usa `unsafe` extensivamente por la naturaleza del FFI Python↔Rust.
- No existe una auditoría formal publicada del código unsafe.

**Veredicto:** Riesgo de ejecución de código: **muy bajo**. El formato JSON declarativo elimina el vector de ataque principal (deserialización de código) que afecta a alternativas como pickle (PyTorch).

---

### B.6. Comparación con Alternativas

| Aspecto | `tokenizers` (standalone) | `transformers.AutoTokenizer` | BPE manual (Python puro) |
|---------|--------------------------|-----------------------------|-----------------------------|
| **Ejecución de código remoto** | No (JSON puro) | Sí si `trust_remote_code=True` | No |
| **Dependencias extra** | ~20 MB (huggingface_hub + httpx…) | ~500 MB+ (torch, transformers…) | 0 |
| **Conexión a red en runtime** | Solo `from_pretrained()` | Solo `from_pretrained()` | Nunca |
| **CVEs conocidos** | 0 | Múltiples | N/A |
| **Rendimiento** | Excelente (Rust nativo) | Igual (usa tokenizers internamente) | Aceptable |
| **Superficie de ataque** | Baja-media | Alta (pickle, remote code) | Mínima |
| **Impacto en bundle PyInstaller** | ~20 MB | ~500 MB+ | 0 |
| **Mantenimiento** | Cero (upstream) | Cero (upstream) | Propio |
| **Riesgo de bugs propios** | Bajo (probado masivamente) | Bajo | Medio |

#### Alternativa minimalista: BPE manual en Python puro
Para nuestro caso concreto (un solo tokenizer GPT-2 fijo, textos cortos de narración de Pong), una implementación BPE en Python puro (~100-150 líneas) sería viable:
- Parsear `tokenizer.json` (vocab + merges) directamente con `json` estándar.
- Implementar encode/decode BPE.
- Cero dependencias extra, superficie de ataque mínima.
- Rendimiento algo menor pero aceptable para generación de textos cortos (<100 tokens).

---

### B.7. Impacto en PyInstaller (Distribución de PongIA)

| Aspecto | Detalle |
|---------|---------|
| **Tamaño del binario nativo** | ~8 MB (`.abi3.so` / `.pyd`) |
| **Dependencias transitivas** | ~12 MB (`huggingface_hub`, `httpx`, `httpcore`, `fsspec`, `hf-xet`…) |
| **Total estimado en bundle** | ~20 MB |
| **Hooks PyInstaller necesarios** | `copy_metadata('tokenizers')` en el spec |
| **Escritura a disco en runtime** | No (con `from_file()`) |
| **Exclusión de módulos innecesarios** | Posible con `--exclude-module` para `httpx`, `httpcore`, `fsspec`, `hf-xet` (verificar que no rompa el import) |

---

### B.8. Evaluación de Riesgo para PongIA

#### Contexto de uso
- Cargar un `tokenizer.json` (GPT-2 BPE) pre-incluido en el bundle.
- Tokenizar/detokenizar textos cortos de narración de partidas de Pong.
- Plataformas: macOS y Windows.
- Nunca descargar tokenizers de fuentes externas en runtime.

#### Matriz de riesgo

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| Supply chain (paquete PyPI comprometido) | Muy baja | Alto | Fijar versión en requirements, verificar SLSA attestations |
| CVE en parsing de tokenizer.json | Muy baja | Bajo-medio | Solo cargar nuestro tokenizer.json, mantener actualizado |
| Telemetría filtrando datos | Nula (offline) | Bajo | `from_file()` + `HF_HUB_OFFLINE=1` |
| Ejecución de código vía tokenizer malicioso | Nula (JSON declarativo) | Alto | N/A — no aplica |
| Inflado del bundle PyInstaller | Segura | Bajo | Excluir módulos de red innecesarios |
| Dependencia abandonada | Muy baja (HF activo) | Medio | Monitorear releases |

#### Conclusión de seguridad

**`tokenizers` es una dependencia segura para PongIA.** Los datos de los usuarios están protegidos: no hay telemetría si se usa `from_file()`, no hay conexiones de red, no hay acceso a archivos no solicitados. El formato JSON declarativo elimina el riesgo de ejecución de código malicioso.

**El principal inconveniente es el peso:** ~20 MB de dependencias transitivas (la mayoría innecesarias) que inflan el bundle. Para un juego que ya incluye `onnxruntime` (~50 MB) y un modelo ONNX (~84 MB), los 20 MB adicionales son tolerables pero no ideales.

**Alternativa viable:** una implementación BPE manual en Python puro (~150 líneas) eliminaría esta dependencia completamente, con superficie de ataque mínima y cero impacto en el bundle. El rendimiento sería aceptable para nuestro volumen de generación.

**Recomendaciones si se adopta `tokenizers`:**
1. Usar siempre `Tokenizer.from_file()` con un `tokenizer.json` pre-incluido en el bundle
2. No usar `from_pretrained()` en producción
3. Setear `HF_HUB_OFFLINE=1` y `HF_HUB_DISABLE_TELEMETRY=1` al inicio de la aplicación
4. Fijar versión en requirements: `tokenizers >= 0.21`
5. Intentar excluir `httpx`, `httpcore`, `fsspec`, `hf-xet` del bundle de PyInstaller
6. No cargar tokenizers de fuentes no confiables

---

## Fuentes (Adenda B)

### tokenizers — Oficiales
- [huggingface/tokenizers (GitHub)](https://github.com/huggingface/tokenizers)
- [tokenizers (PyPI)](https://pypi.org/project/tokenizers/)
- [SLSA Attestations](https://github.com/huggingface/tokenizers/attestations)
- [Cargo.toml — dependencias Rust](https://github.com/huggingface/tokenizers/blob/main/tokenizers/Cargo.toml)

### tokenizers — Seguridad
- [OpenCVE — HuggingFace CVEs](https://app.opencve.io/cve/?vendor=huggingface)
- [GitHub Security Advisories — tokenizers](https://github.com/huggingface/tokenizers/security/advisories)
- [Issue #1397 — OSS-Fuzz proposal (cerrada)](https://github.com/huggingface/tokenizers/issues/1397)
- [Kodem Security — tokenizers WASM vulnerability](https://www.kodemsecurity.com/resources/hugging-face-datasets-and-tokenizers-in-javascript-security-issues-for-ai-pipelines)

### tokenizers — Privacidad
- [HuggingFace Hub — Environment Variables](https://huggingface.co/docs/huggingface_hub/en/package_reference/environment_variables)
- [huggingface_hub telemetry source](https://github.com/huggingface/huggingface_hub/blob/main/src/huggingface_hub/utils/_telemetry.py)

### Ecosistema HuggingFace — Incidentes
- [Typosquatting en HuggingFace Hub (ACM)](https://dl.acm.org/doi/10.1145/3755881.3755921)
- [PyInstaller + transformers issues](https://github.com/huggingface/transformers/issues/38402)
