# Profiling y metricas de rendimiento

## Metricas automaticas

El juego recopila metricas de rendimiento durante la ejecucion:

- **FPS**: ventana rodante de los ultimos 120 frames
- **Latencia LLM**: duracion de cada llamada al narrador (commentate, summary, question, enrich_image)
- **Tiempo SD**: duracion de cada generacion de imagen con Stable Diffusion

Al cerrar el juego, las metricas se exportan a `saves/perf_last.json` y se muestran en la terminal.

## Profiling manual con cProfile

```bash
# 600 frames headless, resultados en terminal
python scripts/profile_game.py

# 1200 frames, guardar stats binarios
python scripts/profile_game.py --frames 1200 --output saves/profile.prof

# Visualizar con snakeviz
pip install snakeviz
python -m snakeviz saves/profile.prof
```

## Flamegraphs con py-spy

```bash
pip install py-spy

# Grabar flamegraph del juego real (con ventana)
py-spy record -o saves/flamegraph.svg -- python main.py

# Top interactivo
py-spy top -- python main.py
```

## Benchmarks automatizados

Los benchmarks estan en `tests/test_benchmark.py` y se ejecutan en CI:

| Test | Que mide | Umbral |
|------|----------|--------|
| `test_fps_headless_baseline` | FPS promedio en 600 frames | >= 200 |
| `test_frame_budget_no_spikes` | Peor frame individual | < 50ms |
| `test_update_throughput` | Updates/s (solo logica) | >= 500 |

Ejecutar localmente:

```bash
python -m pytest tests/test_benchmark.py -v
```

## Ajustar umbrales

Los umbrales son generosos para funcionar en CI (GitHub Actions). Si detectas falsos positivos, ajusta los valores en `tests/test_benchmark.py`. El objetivo es detectar regresiones graves (2x+), no micro-optimizaciones.

## Formato de saves/perf_last.json

```json
{
  "timestamp": "2026-03-19T14:30:00",
  "duration_seconds": 245.3,
  "frames": 14718,
  "fps": { "avg": 59.8, "min": 42.1, "samples": 120 },
  "frame_worst_ms": 23.7,
  "llm": { "calls": 23, "avg_ms": 1850.5, "max_ms": 3200.1 },
  "sd": { "calls": 8, "avg_ms": 4200.3, "max_ms": 5100.0 }
}
```
