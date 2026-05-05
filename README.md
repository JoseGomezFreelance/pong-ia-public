# pong-ia

[![Tests](https://github.com/JoseGomezFreelance/pong-ia-public/actions/workflows/tests.yml/badge.svg)](https://github.com/JoseGomezFreelance/pong-ia-public/actions/workflows/tests.yml)
[![Type check](https://github.com/JoseGomezFreelance/pong-ia-public/actions/workflows/type-check.yml/badge.svg)](https://github.com/JoseGomezFreelance/pong-ia-public/actions/workflows/type-check.yml)

The classic Pong but with AI, what could go wrong?

> **A retro Pong game powered by local AI.** A local LLM narrates each match in real time while Stable Diffusion generates unique artwork during gameplay. ZX Spectrum aesthetic, procedural music, emotional AI opponent — everything runs offline on your machine. No cloud, no API keys, no telemetry.

## Descargar

Prototipo disponible en [itch.io](https://jgf-games.itch.io/pong-ia) (Windows / macOS).

## Versión oficial
- 🏷️ **Beta 0.10**

<p align="center">
  <img src="assets/images/01_portada_PONG-IA_zx_beta_V0.10.jpeg" alt="Portada PongIA Beta 0.10" width="480">
</p>

## Historial de versiones
- 📘 Ver [`CHANGELOG.md`](CHANGELOG.md) para el detalle completo de cambios por versión.
- Método acordado para próximas versiones:
  1. Documentar cambios nuevos bajo `## [Unreleased]` en `CHANGELOG.md`.
  2. Al cerrar versión, crear sección `## [Alfa X.YY] - YYYY-MM-DD` y mover ahí los cambios.
  3. Actualizar `Versión oficial` en este `README` y `APP_VERSION` en `pong/config/version.py`.

## Estado actual
- ✅ Fase 1 jugable (Pong clásico 1972), código organizado en el paquete modular `pong/`.
- ✅ Narrador local integrado en la zona inferior con la familia `Qwen2.5 Instruct Q4_K_M` (5 niveles: 3B a 72B, seleccionable según hardware).
- ✅ Sistema de preguntas interactivas del narrador con bullet time (Sí/No/Duda).
- ✅ Pantalla final con resumen LLM, barra de progreso y exportación de logs.
- ✅ Indicador visual `LLM ON/off` en el HUD.
- ✅ IA emocional: la paleta del ordenador modula velocidad, predicción y agresividad según el estado emocional generado por el LLM.
- ✅ Colores dinámicos ZX Spectrum: paleta de 16 colores del Sinclair ZX Spectrum con transiciones suaves según el humor de la IA.
- ✅ Motor musical MIDI: tema sintetizado con ondas cuadradas emulando el chip AY-3-8912, con remix emocional en tiempo real.
- ✅ Pausa del juego con la tecla P.
- ✅ Efecto de sonido retro libre de derechos (generado proceduralmente) con estrategia dual de beep (retro + musical).
- ✅ Sistema de logros: 45 logros en 4 categorías (carrera, hazaña, secreto, emocional) con popup visual ZX Spectrum y persistencia entre sesiones.
- ✅ Fase visual generativa: fondos artísticos generados por Stable Diffusion (Juggernaut Reborn + LCM LoRA) que reaccionan al estado emocional, el marcador y el contexto del partido. Se desbloquea a los 5 minutos de juego acumulado y se activa al minuto 3 de cada partida. Prompts enriquecidos por el LLM con estética pixel art ZX Spectrum.
- ✅ Sistema de providers y `models.toml`: configuración declarativa de modelos de IA con abstracción de carga para LLM y difusión.
- ✅ Modo headless (`GameHarness`): API de testing programático para ejecutar partidas sin ventana gráfica.
- ✅ Calidad de código: type hints exhaustivos con mypy --strict en CI, logging estructurado con `--debug`, jerarquía de excepciones personalizadas, Protocol interfaces formales y cobertura de tests 81%+.
- ✅ Selector multi-tier de modelos LLM: 5 niveles de calidad (3B/7B/14B/32B/72B) con detección automática de hardware, recomendaciones por color, benchmark IA-vs-IA y cascade de fallback.
- ✅ Fallbacks de hardware: tier 0 oculto (Qwen 1.5B) para hardware limitado, tier -1 ONNX (DistilGPT-2) para CPUs sin AVX2, detección automática de capacidades.
- ⚖️ Sistema RPG (balance sin validar por playtest masivo): barra de XP, 50 niveles, 10 habilidades de gameplay canjeables por tiempo jugado, sistema de ascensión con 10 habilidades permanentes multinivel (hasta nivel 10), persistencia completa entre sesiones. Se desbloquea a los 10 minutos de juego acumulado.
- ✅ Modo agente secreto (tecla A): control del juego via computer-use para demos y testing automatizado.
- ✅ Escalado anti-rally infinito: dificultad progresiva que previene exploits de rallies eternos.
- ✅ Icono personalizado de aplicación en app, instalador y DMG.
- ✅ Protección contra kernel panic en Apple Silicon por presión de memoria GPU.
- ✅ Profiling y benchmarks integrados para métricas de rendimiento.
- ✅ Integridad criptográfica de saves: cadena de hashes (blockchain-style) + HMAC-SHA256 con UUID de placa base. Descarte total si se detecta manipulación.
- 🧪 Leaderboard P2P distribuido (experimental — probado con pocos peers, no a escala): 5 categorías de ranking (puntuación, victoria rápida, rally largo, racha, dominación) con intercambio de records entre jugadores vía red descentralizada.
- 🧪 Red P2P protocolo 4.0 (experimental): cifrado XChaCha20-Poly1305 desde el primer byte, forward secrecy (triple ECDH), firmas Ed25519, pinning de identidad, rate limiting, gossip sin IPs.
- 🧪 NAT traversal adaptativo (experimental): 3 tiers de privacidad (DIRECT / RELAY / ONION) seleccionados automáticamente según el tamaño de la red. Hole punching UDP, relay trustless y onion routing de 3 saltos.
- 🧪 Seed node desplegado, auditado y fortificado (9 vulnerabilidades cerradas pre-despliegue).
- ✅ Sin APIs externas: todo el cómputo de IA ocurre en local.

> Quizá este sea el primer sistema P2P de la era de la Inteligencia Artificial, ¿Skynet nos lo agradecerá?

## Requisitos
- Python 3.11+
- Dependencias Python de `requirements.txt`

## Ejecutar Pong (Fase 1 + narración local)
```bash
python3 -m pip install -r requirements.txt
./scripts/bootstrap_local_model.sh
python3 main.py
```

Si no descargas el modelo, el juego igual corre y mostrará un mensaje indicando que falta el narrador IA.

## Banco de pruebas (tests)

Se usan tests unitarios con `unittest`, ejecutados con `pytest` + `pytest-cov` para medición de cobertura.

### Ejecutar tests por terminal
```bash
pip install -r requirements-dev.txt
python3 -m pytest                         # ejecutar todos los tests
python3 -m pytest --cov --cov-report=term # con informe de cobertura
python3 -m pytest -m "not slow"           # excluir tests lentos de integración
```

### Ejecutar tests en VS Code
1. Abre la carpeta del proyecto en VS Code.
2. Instala la extensión oficial **Python** (si no la tienes).
3. Abre la paleta de comandos (`Cmd+Shift+P` en macOS / `Ctrl+Shift+P` en Windows/Linux).
4. Ejecuta `Python: Configure Tests`.
5. Elige:
   - Framework: `pytest`
   - Carpeta de tests: `tests`
6. Ve a la pestaña **Testing** (icono de probeta) y pulsa `Run All Tests`.

Tests incluidos (39 archivos, 847+ tests, cobertura 80%+):
- `test_scoring.py` — sistema de puntuación (puntos, juegos, sets, partido)
- `test_entities.py` — entidades (Paddle, Ball, colisiones, rebotes)
- `test_save_manager.py` — persistencia JSON, HMAC, cadena de hashes
- `test_game_ai.py` — IA del ordenador y modulación emocional
- `test_question_system.py` — máquina de estados de preguntas y bullet time
- `test_narrator_summary.py` — resumen de partido con LLM
- `test_narrator_questions.py` — preguntas interactivas del narrador
- `test_narrator_questions_extra.py` — helpers puros de preguntas
- `test_achievements.py` — sistema de logros
- `test_achievement_icons.py` — iconos de logros
- `test_emotional_state.py` — estados emocionales de la IA
- `test_theme.py` — colores ZX Spectrum
- `test_music.py` — motor musical MIDI
- `test_idle_detection.py` — detección de inactividad
- `test_harness.py` — API de testing headless
- `test_renderer_llm_status.py` — indicador visual LLM ON/off
- `test_narration_bridge_summary.py` — resumen de narración
- `test_game_copy_logs.py` — exportación de logs
- `test_integration.py` — tests de integración (flujos completos)
- `test_protocols.py` — conformidad de protocolos
- `test_exceptions.py` — jerarquía de excepciones
- `test_benchmark.py` — benchmarks de rendimiento
- `test_models_config.py` — configuración de modelos (models.toml)
- `test_providers.py` — sistema de providers de IA
- `test_rpg_engine.py` — motor RPG: XP, niveles, habilidades, ascensión multinivel
- `test_p2p.py` — red P2P: cache, seeds, handshake, gossip, promoción, rate limiting
- `test_punch.py` — NAT traversal: STUN, hole punch, relay, onion routing
- `test_crypto.py` — primitivas criptográficas (X25519, XChaCha20, Ed25519, KDF)
- `test_leaderboard.py` — rankings, firmas, plausibilidad, merge de entries
- `test_game_p2p_sync.py` — sincronización de records locales con la red P2P
- `test_security.py` — hardening: hex validation, anti-amplificación, relay hijacking, DoS

## Generar ejecutables (.app y .exe)

### Build local con PyInstaller
Instala dependencias de build y ejecuta el script:

```bash
python3 -m pip install pyinstaller pygame mido tomli
python3 scripts/build_with_pyinstaller.py
```

- En macOS genera: `dist/PongIA.app` (~1.2 GB con IA completa)
- En Windows genera: `dist/PongIA.exe`
- El script detecta automáticamente los paquetes de IA instalados (torch, diffusers, llama-cpp-python) y los incluye en el ejecutable.

> Nota: con esta configuración no hay compilación cruzada.
> Debes construir `.app` en macOS y `.exe` en Windows.

### Modelo local en binarios
El ejecutable funciona sin modelo, pero para habilitar narración IA:

- Usa el selector de modelos integrado en la pantalla de descarga para elegir el nivel adecuado a tu hardware (de 3B a 72B).
- Alternativamente, coloca un archivo GGUF en `dist/models/` (junto al `.app`) o define `PONG_IA_MODEL_PATH` con una ruta absoluta al modelo.

> Guía completa con requisitos, troubleshooting y arquitectura de rutas:
> ver [`docs/build-executables.md`](docs/build-executables.md).

## Plan LLM local (sin Ollama)
Este repo ofrece 5 niveles de la familia `Qwen2.5 Instruct` en formato GGUF (3B/7B/14B/32B/72B) con selección automática según hardware.

Detalle y comparación de modelos:
- Ver [`docs/local_model_options.md`](docs/local_model_options.md).

### Bootstrap automático del modelo
```bash
./scripts/bootstrap_local_model.sh
```

Eso instala runtime local (`llama-cpp-python`) y descarga el modelo en `models/`.

> Nota: los pesos no se versionan en Git por tamaño, pero el proyecto queda autónomo tras el bootstrap.
