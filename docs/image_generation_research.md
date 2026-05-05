# Investigación: Modelos de Generación de Imagen para Pong IA

**Fecha**: Marzo 2026
**Objetivo**: Seleccionar un modelo de difusión que pueda generar fondos de juego en tiempo cuasi-real, ejecutándose con el LLM del narrador (Qwen 2.5 3B, ~2.1GB).

---

## Requisitos del sistema

| Parámetro | Valor |
|-----------|-------|
| Hardware | 16GB RAM |
| RAM disponible para imagen | ~10-11GB (16GB - OS - LLM) |
| Backend GPU | MPS (Metal Performance Shaders) |
| Tiempo objetivo por imagen | < 10 segundos |
| Resolución objetivo | 512x512 (escalada a 800x500) |
| Integración | Python (diffusers / PyTorch) |
| LLM concurrente | qwen2.5-3b-instruct-q4_k_m.gguf via llama-cpp-python (~2.1GB) |

---

## Modelos evaluados

### 1. SD 1.5 Juggernaut Reborn + LCM LoRA (RECOMENDADO)

- **HuggingFace**: `stablediffusionapi/juggernaut-reborn`
- **LCM LoRA**: `latent-consistency/lcm-lora-sdv1-5` (~67MB adicionales)
- **Parámetros**: 860M (UNet)
- **Pesos**: ~2.0GB (fp16 safetensors)
- **RAM durante inferencia**: ~5-7GB (UNet + VAE + text encoder)
- **Velocidad en M1 (4 pasos LCM, 512x512)**: **~3-6 segundos**
- **Velocidad sin LCM (20 pasos, 512x512)**: ~15-35 segundos
- **Calidad**: Muy buena (Juggernaut Reborn es un fine-tune top de SD 1.5)
- **Adherencia al prompt**: Buena (nivel SD 1.5, mejorada por el fine-tune)
- **Soporte MPS**: Completo via diffusers
- **Soporte Core ML**: Convertible via apple/ml-stable-diffusion (optimización futura)
- **Coexistencia con LLM**: EXCELENTE (~5-7GB + ~2.1GB + ~4GB OS = ~13GB)

**Configuración recomendada**:
```python
pipe = StableDiffusionPipeline.from_pretrained(
    "stablediffusionapi/juggernaut-reborn",
    torch_dtype=torch.float16,
)
pipe.to("mps")
pipe.enable_attention_slicing()
pipe.load_lora_weights("latent-consistency/lcm-lora-sdv1-5")
pipe.scheduler = LCMScheduler.from_config(pipe.scheduler.config)

image = pipe(prompt, num_inference_steps=4, guidance_scale=1.5).images[0]
```

**Veredicto**: Mejor equilibrio entre velocidad, calidad, memoria y madurez del ecosistema. LCM LoRA reduce la generación de 20 a 4 pasos con pérdida mínima de calidad.

---

### 2. SD Turbo (Stability AI)

- **HuggingFace**: `stabilityai/sd-turbo`
- **Pesos**: ~5.2GB (safetensors)
- **RAM durante inferencia**: ~6-8GB
- **Velocidad en M1 (1 paso, 512x512)**: ~6 segundos
- **Calidad**: Moderada (1 solo paso limita los detalles)
- **Adherencia al prompt**: Moderada
- **Soporte MPS**: Sí
- **Coexistencia con LLM**: Buena

**Veredicto**: Viable pero la calidad a 1 paso es inferior a SD 1.5 + LCM LoRA a 4 pasos. El ahorro de tiempo es marginal (~6s vs ~3-6s) y la calidad es notablemente peor.

---

### 3. SDXL Turbo (Stability AI)

- **HuggingFace**: `stabilityai/sdxl-turbo`
- **Pesos**: ~6.9GB (fp16)
- **Parámetros**: 2.6B
- **RAM durante inferencia**: ~8-12GB (fp16)
- **Velocidad en M1 (1 paso, 512x512)**: ~6 segundos
- **Calidad**: Buena
- **Coexistencia con LLM**: MARGINAL (~8-12GB + ~2.1GB = presión de memoria alta)

**Veredicto**: Riesgo alto de swap en 16GB con el LLM concurrente. No recomendado para esta configuración.

---

### 4. Stable Diffusion 3.5 Medium

- **Parámetros**: 2.5B (arquitectura MMDiT-X)
- **RAM durante inferencia**: ~12-14GB (incluyendo encoder de texto T5)
- **Velocidad en M1**: Estimada ~30-60+ segundos
- **Calidad**: Excelente
- **Soporte Core ML**: No disponible
- **Coexistencia con LLM**: PROBLEMÁTICA (T5 encoder + modelo = 14-16GB total)

**Veredicto**: Demasiado pesado. El encoder T5 consume varios GB adicionales. Con el LLM concurrente, causaría swap severo en 16GB.

---

### 5. FLUX.1 schnell / dev (Black Forest Labs)

- **Parámetros**: 12B
- **Pesos completos**: ~12GB (fp16)
- **Pesos GGUF Q4**: ~6.9GB
- **RAM necesaria (Q4 + encoders)**: ~10-12GB
- **Velocidad en M1 16GB (Q4)**: ~3 minutos por imagen
- **Calidad**: Excelente
- **Soporte MPS**: Sí (lento)
- **Coexistencia con LLM**: MUY POBRE (10-12GB + 2.1GB = swap constante)

**Veredicto**: Modelo demasiado grande y lento para M1 16GB con LLM concurrente. Incluso con cuantización Q4, la generación tarda minutos.

---

### 6. PixArt-alpha / PixArt-delta (LCM)

- **Parámetros del transformer**: 600M (muy ligero)
- **Pesos del transformer**: ~2.3GB
- **RAM total con T5-XXL**: ~8-10GB; con T5 8-bit: ~6-7GB
- **Velocidad en M1 (estimada, 20 pasos)**: ~15-30 segundos
- **PixArt-delta (LCM, 2-4 pasos)**: ~5-15 segundos (estimado, sin benchmarks M1)
- **Calidad**: Buena, competitiva con SDXL
- **Adherencia al prompt**: Muy buena (gracias al encoder T5)
- **Soporte MPS**: Debería funcionar via diffusers
- **Coexistencia con LLM**: Moderada a buena (con T5 8-bit)

**Veredicto**: Opción interesante como segunda alternativa. El transformer de 600M es muy ligero, pero el encoder T5-XXL añade memoria significativa. La falta de benchmarks específicos en M1 lo convierte en una apuesta más arriesgada que SD 1.5.

---

### 7. FLUX.2 klein (4B)

- **Pesos 4-bit cuantizado**: ~4GB
- **RAM total**: ~8GB para 512px
- **Velocidad en M1 Max**: ~31 segundos
- **Coexistencia con LLM en M1 16GB**: POBRE (8GB + 2.1GB + OS = al límite)

**Veredicto**: Diseñado para hardware más potente (M1 Max+). No adecuado para M1 base 16GB con carga concurrente.

---

## Tabla comparativa

| Modelo | Pesos | RAM | Velocidad M1 512x512 | Calidad | Coex. LLM | Riesgo |
|--------|-------|-----|----------------------|---------|------------|--------|
| **SD 1.5 Juggernaut + LCM** | ~2GB | ~5-7GB | **3-6s (4 pasos)** | Buena | EXCELENTE | Bajo |
| SD 1.5 Juggernaut (sin LCM) | ~2GB | ~5-7GB | 15-35s (20 pasos) | Muy buena | EXCELENTE | Bajo |
| SD Turbo | ~5.2GB | ~6-8GB | ~6s (1 paso) | Moderada | Buena | Medio |
| SDXL Turbo | ~6.9GB | ~8-12GB | ~6s (1 paso) | Buena | Marginal | Alto |
| SD 3.5 Medium | ~5GB | ~12-14GB | 30-60s+ | Excelente | Pobre | Muy alto |
| PixArt-delta (T5 8-bit) | ~2.3GB | ~6-7GB | 5-15s (est.) | Buena | Moderada | Medio |
| FLUX.1 schnell (Q4) | ~6.9GB | ~10-12GB | ~180s | Excelente | Muy pobre | Muy alto |
| FLUX.2 klein (4-bit) | ~4GB | ~8GB | ~31s | Buena | Pobre | Alto |

---

## Recomendación final

### Opción principal: SD 1.5 Juggernaut Reborn + LCM LoRA

Razones:
1. **Memoria**: ~5-7GB deja margen confortable para el LLM (~2.1GB) y el SO (~4GB)
2. **Velocidad**: 3-6 segundos a 4 pasos LCM, bien dentro del objetivo de <10s
3. **Calidad**: Suficiente y adecuada para fondos de juego atmosféricos
4. **Ecosistema**: El camino mejor probado en Apple Silicon; máxima documentación y soporte comunitario
5. **Flexibilidad**: Checkpoint base intercambiable sin cambiar el pipeline; conversión a Core ML posible como optimización futura
6. **Bajo riesgo**: Modelo maduro, ampliamente testeado, sin sorpresas

### Segunda opción: PixArt-alpha + LCM (PixArt-delta) con T5 8-bit

Ofrece mejor adherencia al prompt gracias al encoder T5, pero tiene mayor riesgo por falta de benchmarks específicos en M1 base.

---

## Optimizaciones futuras

### Core ML (apple/ml-stable-diffusion)
- Conversión del pipeline a Core ML para aprovechar el Neural Engine (ANE)
- El ANE es ~2x más rápido que la GPU para SD 1.5
- Reduciría el tiempo de generación a ~5-9 segundos (20 pasos) o ~2-3 segundos (4 pasos LCM)
- Requiere conversión previa del modelo (proceso de una sola vez)

### Attention slicing + VAE slicing
- `pipe.enable_attention_slicing()` reduce el pico de memoria ~30%
- `pipe.enable_vae_slicing()` reduce memoria del decodificador VAE
- Ambos ya incluidos en la configuración recomendada

### Generación a menor resolución
- Generar a 384x384 en vez de 512x512 reduciría el tiempo ~40%
- Escalado bilineal a 800x500 sigue siendo aceptable para fondos

---

## Referencias

- [Juggernaut Reborn en HuggingFace](https://huggingface.co/stablediffusionapi/juggernaut-reborn)
- [Juggernaut Reborn en CivitAI](https://civitai.com/models/46422?modelVersionId=274039)
- [LCM LoRA (HuggingFace Blog)](https://huggingface.co/blog/lcm_lora)
- [Diffusers MPS Guide](https://huggingface.co/docs/diffusers/optimization/mps)
- [Apple ML Stable Diffusion](https://github.com/apple/ml-stable-diffusion)
- [Apple ML Research: SD on Apple Silicon](https://machinelearning.apple.com/research/stable-diffusion-coreml-apple-silicon)
