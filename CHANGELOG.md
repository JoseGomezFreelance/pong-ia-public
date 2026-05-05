# Changelog

Todas las actualizaciones relevantes del proyecto se documentan aquí.

## [Unreleased]

### Added
- Pendiente.

### Changed
- Pendiente.

### Fixed
- Pendiente.

## [Beta 0.10] - 2026-04-16

### Added
- Integridad criptográfica de archivos de guardado: cadena de hashes SHA-256 (blockchain-style) para detectar inserciones/eliminaciones + HMAC-SHA256 con clave derivada del UUID de placa base para impedir falsificación. Descarte total si se detecta manipulación.
- Red P2P para leaderboard distribuido (protocolo 4.0): descubrimiento por UDP beacon anónimo en LAN, cache persistente de peers (`known_peers.json`) con gossip cada 30 s, fichero de seed peers (`known_peers.txt`), y seeds hardcoded (`DEFAULT_SEEDS`) como fallback.
- Handshake TCP cifrado desde el primer byte: XChaCha20-Poly1305 con nonce de 24 bytes, forward secrecy vía triple ECDH (ephemeral-ephemeral + static-ephemeral + ephemeral-static), autenticación mutua con firma Ed25519 y challenge con nonces.
- Identidad P2P determinista con pinning de verify_key, sistema de strikes y rechazo de peers con identidad inconsistente.
- Leaderboard con 5 categorías de ranking: mayor puntuación, victoria más rápida, rally más largo, racha imparable y victoria más dominante. Entries firmadas con Ed25519 por el autor original, relay trustless entre nodos (estilo Bitcoin), validación de plausibilidad y timestamps.
- Pantalla de conexión P2P: prompt de alias (max 20 chars), indicador de estado de conexión, sufijo visual Base64 para aliases duplicados, backup offline de entries remotas.
- NAT traversal con privacidad adaptativa (`pong/punch.py`): 3 tiers automáticos según peers conectados — DIRECT (<8, UDP hole punch), RELAY (8-14, 1-hop relay), ONION (>=15, 3-hop onion routing con forward secrecy total). STUN para descubrimiento de endpoint reflexivo, keepalive UDP cada 20 s.
- Seed node headless para VPS (`seed_node.py`): arranca solo la capa P2P sin pygame, genera keypair Ed25519, acepta `--debug` y `--alias`, shutdown limpio con SIGINT/SIGTERM, log de estado periódico cada 60 s.
- Servicio systemd para despliegue del seed node con auto-restart y permisos restrictivos.
- Seed desplegado, records cruzados exitosamente.
- Soporte Linux para derivación de machine key (necesario para el seed node).
- 27 tests de seguridad en `tests/test_security.py`: hex validation, IP privada, relay duplicado, conn_tracker cleanup, relay cap, timeout, strike expiry, onion cleanup, bootstrap pruning.
- Tests de P2P: seed loading con claves temporales, promoción a fp real, port preservation, bootstrap candidacy, cache exclusion, gossip exclusion.
- Tests de NAT punch: STUN roundtrip, DIRECT punch, RELAY forwarding, ONION binary format, ONION full handshake E2E, signature verification, degraded mode.
- Auditoría de seguridad, preparación, SCP, smoke test, systemd, verificación, mantenimiento.

### Changed
- Protocolo P2P actualizado a versión 4.0: incompatible con v3.0/v2.0/v1.0. Peers antiguos son rechazados inmediatamente en el handshake.
- Rate limiting endurecido en todas las capas de la red P2P.
- Timeout TCP de conexiones entrantes reducido (anti-slowloris).
- Strikes ahora expiran tras un período configurable (antes eran permanentes).
- `_RawEncoder` custom eliminado en `crypto.py`: sustituido por `nacl.encoding.RawEncoder`.
- Type annotations explícitas en `crypto.py`, `p2p.py` y `punch.py` para satisfacer mypy strict.

### Fixed
- Hardening de seguridad pre-despliegue: auditoría completa del código expuesto a Internet con múltiples correcciones en validación de inputs, gestión de recursos y limpieza de estado.
- Puerto preservado durante promoción de seed peer temporal a fingerprint real.
- Guard contra estado nulo en punch data handler.

### Stats
- 38 archivos de test, 847+ tests, cobertura 80%+.

## [Alfa 0.09] - 2026-04-03

### Added
- Sistema RPG completo: barra de XP con 50 niveles (curva cuadrática), 10 habilidades de gameplay comprables con tiempo jugado (spin, control direccional, pala ampliada, reacción veloz, golpe tenso, reflejo automático, bonus XP, disparo curvo, doble impulso, instinto dual) y sistema de ascensión con 10 habilidades permanentes multinivel (hasta nivel 10 cada una, coste escalado). Se desbloquea a los 10 minutos de juego acumulado.
- Pantalla de habilidades RPG: overlay con tarjetas de habilidades (bloqueada/disponible/comprada), balance de segundos disponibles y compra interactiva.
- Pantalla de ascensión: diálogo de confirmación irreversible, tarjetas de habilidades de ascensión con niveles (Nv. X/10), botón ASCENDER que resetea progresión y muestra pantalla de título.
- Modo agente secreto (tecla A): control del juego vía computer-use MCP para demos y testing automatizado. Nuevo módulo `pong/agent_mode.py`.
- Tier 0 fallback oculto: Qwen 2.5 1.5B para hardware muy limitado, no visible en el selector pero activable automáticamente por cascade de fallback.
- Tier -1 ONNX fallback: DistilGPT-2 vía ONNX Runtime para CPUs sin soporte AVX2. Nuevo módulo `pong/onnx_provider.py`.
- Detección de CPUs sin AVX2: desactivación automática de narración IA en hardware incompatible con llama.cpp.
- Icono personalizado de aplicación integrado en app macOS, instalador Windows y DMG.
- Escalado anti-rally infinito: dificultad progresiva que previene exploits de rallies eternos.
- Protección contra kernel panic en Apple Silicon: límites de presión de memoria GPU para evitar crashes del sistema.
- Documentación de auditoría de seguridad de tokenizers (Adenda B).
- Documentación técnica del sistema RPG (`docs/rpg_system.md`).

### Changed
- Layout de ventana: nueva zona de 22px para barra XP entre campo de juego (y=544) y narración (y=566). Altura total 766px.
- Habilidades de ascensión: formato de almacenamiento cambiado de lista a diccionario `{skill_id: level}` con migración automática.
- Flujo de ascensión: requiere confirmación explícita (diálogo Aceptar/Cancelar), pantalla de ascensión sin botón de volver para evitar gasto de AP sin ascender.
- MRO de Game: `GameRPGMixin` antes de `GamePersistenceMixin` para resolver conflictos de métodos entre mixins.
- Paleta izquierda del benchmark corregida para evitar rallies infinitos en demos.

### Fixed
- Errores de mypy en sistema RPG: `float` asignado a variables `int` de velocidad, conflictos de atributos entre mixins resueltos con `getattr()`.
- Cobertura CI restaurada a 80%+ con 66 tests nuevos para `rpg_engine.py` y omisión de archivos pygame-heavy.
- Posición de reinicio de paleta del ordenador (home x) corregida.
- Errores de CI con numpy/onnxruntime no disponibles en GitHub Actions.
- Cobertura CI: exclusión de `onnx_provider.py` y funciones de red.

### Stats
- 25 archivos de test, 490+ tests, cobertura 80%+.

## [Alfa 0.08] - 2026-03-24

### Added
- Selector multi-tier de modelos LLM: 5 niveles de calidad (Qwen 2.5 3B/7B/14B/32B/72B) accesible desde la pantalla de descarga, con recomendaciones por color (verde/amarillo/rojo) según el hardware del usuario.
- Detección automática de hardware: RAM total, tipo de GPU (CUDA/MPS/CPU), VRAM, espacio en disco y modelo de CPU. Nuevo módulo `pong/system_info.py`.
- Definición de tiers LLM: dataclass `LLMTier` con 5 niveles preconfigurados, umbrales de RAM y lógica de recomendación. Nuevo módulo `pong/config/llm_tiers.py`.
- Descarga de modelos split GGUF: los modelos de 7B en adelante se distribuyen en múltiples archivos en HuggingFace. Nueva función `_download_hf_split()` que consulta la API de HF para obtener archivos y tamaños, y descarga cada parte por HTTP directo con barra de progreso acumulada real (MB descargados / MB totales).
- Benchmark integrado IA-vs-IA: partida demo de 45 segundos con dos paletas controladas por IA y llamadas periódicas al LLM. Mide FPS y latencia LLM en tiempo real con criterios de aprobación (FPS >= 30, LLM <= 15 s, mínimo 2 llamadas). Nuevo módulo `pong/benchmark.py`.
- Cascade automático de fallback: si el benchmark falla, el sistema desciende al nivel inmediatamente inferior, descarga si es necesario y vuelve a probar.
- Diálogo de limpieza de modelos: al seleccionar un modelo nuevo, ofrece eliminar modelos anteriores no usados para liberar espacio. Agrupa archivos split como unidad.
- Guardado de configuración LLM: nueva función `save_llm_config()` en `pong/config/models.py` que escribe la sección `[llm]` de `models.toml` preservando `[image]`.
- Empaquetado Windows con ZIP (itch.io) e instalador Inno Setup.
- Script para capturar screenshots de tienda (itch.io).
- Script DMG para macOS con nombre personalizable.
- Informe de desarrollo con análisis de eficiencia IA (PDF).

### Changed
- Aceleración GPU en Apple Silicon: `n_gpu_layers` cambiado de `1` a `-1` para MPS, aprovechando la memoria unificada y offloadeando todas las capas a Metal. Esto permite mover modelos de 7B-14B con latencias de 1-3 s en vez de 40+ s.
- `LocalLLMProvider.reload()`: ahora relee `models.toml` y detecta cambios de modelo (filename distinto) para forzar recarga.
- Pantalla de descarga: el botón de LLM reemplazado por "SELECCIONAR MODELO >" que abre el selector multi-tier. "DESCARGAR TODO" renombrado a "DESCARGAR DIFUSIÓN".
- Refactorización de `pong/config/models.py`: extraída `_resolve_toml_path()` como función reutilizable.
- Refactorización interna de `pong/model_downloader.py`: extraída lógica común de descarga HTTP en `_download_file()`.
- Refactor de estado del juego en dataclasses y factory de subsistemas.
- Eliminación de duplicación if/else en `apply_point` con helpers de acceso por lado.
- Reemplazo de `Any` por tipos concretos en firmas de `providers.py` e `image_generator.py`.
- Dependencia `psutil>=5.9.0` añadida para detección de hardware.

### Fixed
- Error HTTP 404 al descargar modelos de 7B+ (HuggingFace no tiene GGUF single-file para esos tamaños; ahora se usan archivos split).
- FPS del benchmark siempre mostraba 0: `perf.snapshot()` devuelve dict anidado (`snap["fps"]["avg"]`) pero se leían claves planas inexistentes (`snap.get("fps_avg")`).
- Benchmark siempre fallaba con "LLM no completó suficientes llamadas" por el mismo bug de claves planas (leía `llm_count=0`).
- Parseo JSON de emociones robustecido ante inputs adversariales del LLM.
- `CacheNotFound` al comprobar modelos de difusión cuando el directorio `models/diffusion` no existía.
- Rutas de datos redirigidas a Application Support en macOS y empaquetado correcto de `llama_cpp` con libs nativas en builds de Windows y macOS.
- SSL en descarga de modelos: uso de `certifi` para contexto SSL fiable en todas las plataformas.
- Redirección de stdout/stderr a devnull en builds `--windowed` para evitar crashes por pipes rotas.

### Stats
- 24 archivos de test, 427+ tests, cobertura 81%+.

## [Alfa 0.07] - 2026-03-20

### Added
- Modo headless (`GameHarness`): API de testing programático para ejecutar partidas sin ventana gráfica, útil para tests de integración y benchmarks automatizados.
- Enriquecimiento de prompts de imagen con LLM: el narrador genera descripciones artísticas más variadas para Stable Diffusion, evitando repetición visual entre fondos consecutivos.
- Type hints exhaustivos y mypy --strict en CI: anotaciones de tipo en todo el código fuente con chequeo estricto automatizado en el pipeline de integración continua.
- Logging estructurado con flag `--debug`: sustituye todos los `print(stderr)` por el módulo `logging` estándar con niveles configurables. Nuevo argumento de línea de comandos `--debug` para activar nivel DEBUG.
- Jerarquía de excepciones personalizadas: excepciones específicas del proyecto (`PongError`, `NarrationError`, `ImageGenError`, etc.) para mejor depuración y manejo de errores.
- Protocol interfaces formales: interfaces `Protocol` (PEP 544) para los subsistemas del juego (`GameProtocol`, `RendererProtocol`, `NarratorProtocol`), facilitando el desacoplamiento y testing.
- Cobertura de tests con pytest-cov: configuración de medición de cobertura automática, alcanzando 81%+ de cobertura global.
- Profiling, benchmarks y métricas de rendimiento: herramientas de profiling integradas y benchmarks reproducibles para medir el impacto de cambios en el rendimiento del juego.
- Sistema de providers y `models.toml`: configuración declarativa de modelos de IA en formato TOML, con sistema de providers que abstrae la carga de modelos LLM y de difusión.
- Estética pixel art ZX Spectrum en prompts de Stable Diffusion: los prompts artísticos ahora incluyen directivas de estilo retro coherentes con la estética visual del juego.

### Changed
- Refactorización de `game.py`, `renderer.py` y `narrator.py` en mixins para reducir el tamaño de cada archivo y mejorar la mantenibilidad.
- Refactorización del módulo monolítico `config.py` en paquete `config/` con 9 submódulos especializados (`version`, `display`, `gameplay`, `scoring`, `ai`, `narration`, `imagegen`, `audio`, `paths`).
- Reemplazo de `except Exception` catch-all por excepciones específicas en todo el proyecto.

### Fixed
- Eliminados tirones (frame drops) durante la generación de imágenes con Stable Diffusion mediante mejor gestión de hilos.
- El generador de imágenes SD se detiene correctamente en la pantalla final para liberar la GPU al LLM del resumen.
- Las notificaciones de logros ahora aparecen inmediatamente al conseguirse, sin retraso.
- Corregidos errores de CI en type-check y tests de integración (discrepancias mypy local/CI, type stubs faltantes).
- Eliminados comentarios `type: ignore` obsoletos en `image_generator`.

### Stats
- 24 archivos de test, 398+ tests, cobertura 81%+.

## [Alfa 0.06] - 2026-03-07

### Added
- Fase visual generativa: nuevo sistema de fondos artísticos generados por IA de imagen que reaccionan al estado emocional, el marcador y el contexto del partido.
- Modelo de difusión: Stable Diffusion 1.5 Juggernaut Reborn con LCM LoRA para generación rápida (~7 s por imagen).
- Descarga automática de modelos: los pesos de Juggernaut Reborn (~2.7 GB) y LCM LoRA (~128 MB) se descargan en la pantalla de carga ZX Terminal la primera vez que se ejecuta el juego con la fase desbloqueada.
- Sistema de desbloqueo por progresión: la fase visual se desbloquea al acumular 5 minutos de juego total entre partidas (persistido en `game_history.json`). Una vez desbloqueada, se activa al minuto 3 de cada partida.
- Nuevo módulo: `pong/image_generator.py` — motor de generación de imágenes con arquitectura de hilo de fondo + cola (idéntica a `NarrationBridge`), carga lazy del modelo y conversión PIL a pygame Surface.
- Constructor de prompts artísticos: mapeo de 9 estados emocionales (`neutral`, `relajado`, `tenso`, `irritado`, `furioso`, `deprimido`, `aburrido`, `euforico`, `erratico`) a estilos visuales descriptivos, con modificadores basados en la intensidad del rally y el dominio del marcador.
- Crossfade suave entre imágenes generadas con transición configurable de 3 segundos.
- Overlay oscuro semi-transparente sobre la imagen de fondo para mantener la legibilidad de paletas, pelota y línea central.
- Warm-up del modelo: primera inferencia dummy al cargar para compilar kernels MPS y evitar latencia en la primera imagen real.
- Informe de investigación de modelos de imagen: `docs/image_generation_research.md` con comparativa detallada de 8 modelos (SD 1.5, SD Turbo, SDXL Turbo, SD 3.5, FLUX, PixArt) evaluados para ordenador de gama media-baja Mac.

### Changed
- `save_manager.py`: formato JSON ampliado a v1.2 con clave `phases_unlocked` para tracking de fases desbloqueadas. Nueva función `check_phase_unlocks()`. Firma de `save_session()` ampliada para devolver fases recién desbloqueadas (3-tupla).
- `renderer.py`: nuevo estado de fondo generativo (`_bg_surface`, `_bg_prev_surface`, `_bg_transition_t`) y métodos `set_background_image()`, `update_background_transition()`, `clear_background_image()`, `_draw_generated_background()`. Lógica condicional en `draw_game()` para renderizar imagen de fondo o color sólido.
- `game.py`: orquestación completa de la fase visual generativa — activación/desactivación del generador, consumo de imágenes, solicitud periódica cada 15 s, shutdown limpio, retroactividad de desbloqueo al iniciar, y reset al reiniciar partida.
- `config.py`: nuevas constantes `IMAGEGEN_*` (umbrales de desbloqueo/activación, modelo, LoRA, pasos, resolución, intervalo, transición, overlay, directorio de cache).
- `requirements.txt`: nuevas dependencias `diffusers>=0.27.0`, `transformers>=4.38.0`, `accelerate>=0.27.0`, `safetensors>=0.4.0`, `peft>=0.9.0`, `huggingface_hub>=0.21.0`, `torch>=2.1.0`.
- Pantalla de carga ZX Terminal: nuevo paso condicional para descarga de modelos de difusión (solo si la fase está desbloqueada y los modelos no están en cache).

## [Alfa 0.05] - 2026-03-02

### Added
- Sistema de logros: 45 logros en 4 categorías (carrera, hazaña, secreto, emocional) con motor data-driven autocontenido en `pong/achievements.py`.
- Logros de carrera: hitos acumulados entre sesiones (partidos jugados, victorias, puntos totales, rallies acumulados) con escalado progresivo.
- Logros de hazaña: proezas en un solo partido (rallies largos, rachas, juego/set/partido perfecto, remontada, velocidad).
- Logros secretos: 7 logros ocultos con condiciones sorpresa (rally de 42, trasnochador, respuestas unánimes, humillación total, victoria monocromo).
- Logros emocionales: 6 logros relacionados con el estado emocional de la IA (furioso, deprimido, eufórico, errático, espectro completo, domador de fieras).
- Notificación visual de logro desbloqueado: popup estilo ZX Spectrum con borde cyan, nombre en amarillo y flavor text en blanco. Auto-cierre tras 3.5 segundos con fade-out. Cola FIFO para múltiples logros.
- Sonido de logro: chirp ascendente (880-1320 Hz) generado proceduralmente con onda cuadrada.
- Persistencia de logros y estadísticas de carrera en `game_history.json` con migración automática desde formato v1.0 (Alfa 0.04).
- Retroactividad: al actualizar desde Alfa 0.04, los logros de carrera se conceden automáticamente según las sesiones existentes.
- Resumen de logros en la pantalla final: contador X/45 y lista de últimos logros desbloqueados.
- Nuevo módulo: `pong/achievements.py`.
- Nuevos tests: `test_achievements.py` (53 tests). Total proyecto: 163 tests.

### Changed
- `save_manager.py`: formato JSON ampliado a v1.1 con claves `achievements` y `career_stats`. Firma de `save_session()` ampliada con parámetros opcionales retrocompatibles.
- `sound.py`: nueva función `_build_achievement_chirp()` y método `play_achievement()` en `RetroSoundManager`.
- `renderer.py`: nuevos métodos `draw_achievement_popup()` y `_draw_achievements_summary()`. Firma de `draw_end_screen()` ampliada con parámetro `achievements`.
- `game.py`: hooks de logros en `__init__`, `_handle_point`, `update`, `_save_game` y `draw`.

## [Alfa 0.04] - 2026-02-27

### Added
- IA emocional: sistema de estado emocional continuo (`EmotionalState`) con 4 ejes —agresividad, estabilidad, motivación, humor— que modula el comportamiento de la paleta del ordenador en 7 pasos. El LLM genera emociones en formato JSON junto con las preguntas.
- Detección de inactividad del jugador: seguimiento de posición a 4 Hz con cálculo de varianza. Si el jugador deja la raqueta quieta durante un rally largo, la IA sube su agresividad autónomamente (anti-exploit de rally infinito).
- Colores dinámicos ZX Spectrum: paleta de 16 colores exactos del Sinclair ZX Spectrum (1982) con `ThemeManager` que gestiona 3 fases visuales —monocromo → despertar → emocional— y 9 esquemas de color por mood_tag con interpolación RGB suave.
- Motor musical MIDI: parseo y reproducción de un tema MIDI con síntesis de ondas cuadradas emulando el chip AY-3-8912 del ZX Spectrum 128K. Tres fases de audio: silencio → melodía original → remix emocional. `EmotionalRemixer` mapea cada mood_tag a parámetros musicales (tempo, transposición, voces activas, percusión).
- Pausa con tecla P: pausar/reanudar el juego. Overlay semi-transparente con texto «PAUSA» centrado.
- Nuevos módulos: `pong/emotional_state.py`, `pong/theme.py`, `pong/music.py`.
- Nuevo asset: `assets/music/main_theme.mid`.
- Nuevos tests: `test_emotional_state.py` (24), `test_idle_detection.py` (15), `test_theme.py` (21), `test_music.py` (24). Total proyecto: 110 tests.

### Changed
- Sistema de sonido refactorizado con estrategia dual de beep: beep retro (1240 Hz) para la fase silenciosa y beep musical (620 Hz) para la fase con música. Funciones de síntesis extraídas como utilidades reutilizables.
- El renderer acepta colores dinámicos (`ThemeColors`) en todos sus métodos, sustituyendo las constantes fijas.
- IA del ordenador (`update_ai`) ampliada con comportamiento modulado por emoción: predicción de trayectoria, golpe con el canto, jitter por inestabilidad y motivación variable.
- Nueva dependencia: `mido>=1.3.0`.

## [Alfa 0.03] - 2026-02-26

### Added
- Sistema de preguntas interactivas Sí/No/Duda del narrador con efecto bullet time (cámara lenta). El jugador responde moviendo la paleta durante una pausa en cámara lenta.
- Indicador visual `LLM ON`/`LLM off` en la esquina inferior del HUD.
- Pantalla final con resumen generado por el LLM entre « », barra de progreso estilo Pong y botón "copiar" para exportar el historial de terminal al portapapeles.
- Conversación dinámica: preguntas evolutivas que se adaptan al contexto del partido y comentarios del narrador influidos por el diálogo previo con el jugador.

### Changed
- Refactorización del archivo monolítico `pong.py` en paquete modular `pong/` (`game.py`, `renderer.py`, `narrator.py`, `narration_bridge.py`, `config.py`, `sound.py`).
- Cadencia de preguntas del narrador ajustada a 30 segundos.
- Mejora del sistema de preguntas: pool de 10 preguntas iniciales que el LLM reformula para variedad.
- Renombrado de "la computadora" por "el ordenador" en todos los textos del juego.

### Fixed
- Corrección de la UI de preguntas para que el prompt se renderice correctamente en la caja de texto del narrador.

## [Alfa 0.02] - 2026-02-23

### Changed
- Se ajustó el flujo de narración para que los eventos de puntuación se comenten de forma inmediata y sin congelar el gameplay.
- Se mantuvo el procesamiento asíncrono del LLM para los mensajes de juego en curso.

### Fixed
- Se eliminó el "lagazo" que aparecía tras anotar un punto al quitar la pausa obligatoria post-punto.
- Se descartaron respuestas de narración obsoletas con `request_id` antiguo para evitar comentarios fuera de contexto.

## [Alfa 0.01] - 2026-02-22

### Added
- Primera versión jugable de Pong en `pygame` con formato de partido (puntos, juegos, sets).
- Integración de narrador local con `Qwen2.5-3B-Instruct` vía `llama-cpp-python`.
- Zona de narración en HUD, memoria breve del narrador y logs de depuración de eventos.
- Sonido retro procedural al contacto de pelota con paletas.
- Scripts para bootstrap de modelo local y build de ejecutables (`.app`/`.exe`).

