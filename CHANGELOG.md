# Changelog

Todas las actualizaciones relevantes del proyecto se documentan aquí.

## [Unreleased]

### Added
- Pendiente.

### Changed
- Pendiente.

### Fixed
- Pendiente.

## [Alfa 0.07] - 2026-03-20

### Added
- Modo headless (`GameHarness`): API de testing programatico para ejecutar partidas sin ventana grafica, util para tests de integracion y benchmarks automatizados.
- Enriquecimiento de prompts de imagen con LLM: el narrador genera descripciones artisticas mas variadas para Stable Diffusion, evitando repeticion visual entre fondos consecutivos.
- Type hints exhaustivos y mypy --strict en CI: anotaciones de tipo en todo el codigo fuente con chequeo estricto automatizado en el pipeline de integracion continua.
- Logging estructurado con flag `--debug`: sustituye todos los `print(stderr)` por el modulo `logging` estandar con niveles configurables. Nuevo argumento de linea de comandos `--debug` para activar nivel DEBUG.
- Jerarquia de excepciones personalizadas: excepciones especificas del proyecto (`PongError`, `NarrationError`, `ImageGenError`, etc.) para mejor depuracion y manejo de errores.
- Protocol interfaces formales: interfaces `Protocol` (PEP 544) para los subsistemas del juego (`GameProtocol`, `RendererProtocol`, `NarratorProtocol`), facilitando el desacoplamiento y testing.
- Cobertura de tests con pytest-cov: configuracion de medicion de cobertura automatica, alcanzando 81%+ de cobertura global.
- Profiling, benchmarks y metricas de rendimiento: herramientas de profiling integradas y benchmarks reproducibles para medir el impacto de cambios en el rendimiento del juego.
- Sistema de providers y `models.toml`: configuracion declarativa de modelos de IA en formato TOML, con sistema de providers que abstrae la carga de modelos LLM y de difusion.
- Estetica pixel art ZX Spectrum en prompts de Stable Diffusion: los prompts artisticos ahora incluyen directivas de estilo retro coherentes con la estetica visual del juego.

### Changed
- Refactorizacion de `game.py`, `renderer.py` y `narrator.py` en mixins para reducir el tamano de cada archivo y mejorar la mantenibilidad.
- Refactorizacion del modulo monolitico `config.py` en paquete `config/` con 9 submodulos especializados (`version`, `display`, `gameplay`, `scoring`, `ai`, `narration`, `imagegen`, `audio`, `paths`).
- Reemplazo de `except Exception` catch-all por excepciones especificas en todo el proyecto.

### Fixed
- Eliminados tirones (frame drops) durante la generacion de imagenes con Stable Diffusion mediante mejor gestion de hilos.
- El generador de imagenes SD se detiene correctamente en la pantalla final para liberar la GPU al LLM del resumen.
- Las notificaciones de logros ahora aparecen inmediatamente al conseguirse, sin retraso.
- Corregidos errores de CI en type-check y tests de integracion (discrepancias mypy local/CI, type stubs faltantes).
- Eliminados comentarios `type: ignore` obsoletos en `image_generator`.

### Stats
- 24 archivos de test, 398+ tests, cobertura 81%+.

## [Alfa 0.06] - 2026-03-07

### Added
- Fase visual generativa: nuevo sistema de fondos artisticos generados por IA de imagen que reaccionan al estado emocional, el marcador y el contexto del partido.
- Modelo de difusion: Stable Diffusion 1.5 Juggernaut Reborn con LCM LoRA para generacion rapida (~7 s por imagen).
- Descarga automatica de modelos: los pesos de Juggernaut Reborn (~2.7 GB) y LCM LoRA (~128 MB) se descargan en la pantalla de carga ZX Terminal la primera vez que se ejecuta el juego con la fase desbloqueada.
- Sistema de desbloqueo por progresion: la fase visual se desbloquea al acumular 5 minutos de juego total entre partidas (persistido en `game_history.json`). Una vez desbloqueada, se activa al minuto 3 de cada partida.
- Nuevo modulo: `pong/image_generator.py` — motor de generacion de imagenes con arquitectura de hilo de fondo + cola (identica a `NarrationBridge`), carga lazy del modelo y conversion PIL a pygame Surface.
- Constructor de prompts artisticos: mapeo de 9 estados emocionales (`neutral`, `relajado`, `tenso`, `irritado`, `furioso`, `deprimido`, `aburrido`, `euforico`, `erratico`) a estilos visuales descriptivos, con modificadores basados en la intensidad del rally y el dominio del marcador.
- Crossfade suave entre imagenes generadas con transicion configurable de 3 segundos.
- Overlay oscuro semi-transparente sobre la imagen de fondo para mantener la legibilidad de paletas, pelota y linea central.
- Warm-up del modelo: primera inferencia dummy al cargar para compilar kernels MPS y evitar latencia en la primera imagen real.
- Informe de investigacion de modelos de imagen: `docs/image_generation_research.md` con comparativa detallada de 8 modelos (SD 1.5, SD Turbo, SDXL Turbo, SD 3.5, FLUX, PixArt) evaluados para ordenador de gama media-baja Mac.

### Changed
- `save_manager.py`: formato JSON ampliado a v1.2 con clave `phases_unlocked` para tracking de fases desbloqueadas. Nueva funcion `check_phase_unlocks()`. Firma de `save_session()` ampliada para devolver fases recien desbloqueadas (3-tupla).
- `renderer.py`: nuevo estado de fondo generativo (`_bg_surface`, `_bg_prev_surface`, `_bg_transition_t`) y metodos `set_background_image()`, `update_background_transition()`, `clear_background_image()`, `_draw_generated_background()`. Logica condicional en `draw_game()` para renderizar imagen de fondo o color solido.
- `game.py`: orquestacion completa de la fase visual generativa — activacion/desactivacion del generador, consumo de imagenes, solicitud periodica cada 15 s, shutdown limpio, retroactividad de desbloqueo al iniciar, y reset al reiniciar partida.
- `config.py`: nuevas constantes `IMAGEGEN_*` (umbrales de desbloqueo/activacion, modelo, LoRA, pasos, resolucion, intervalo, transicion, overlay, directorio de cache).
- `requirements.txt`: nuevas dependencias `diffusers>=0.27.0`, `transformers>=4.38.0`, `accelerate>=0.27.0`, `safetensors>=0.4.0`, `peft>=0.9.0`, `huggingface_hub>=0.21.0`, `torch>=2.1.0`.
- Pantalla de carga ZX Terminal: nuevo paso condicional para descarga de modelos de difusion (solo si la fase esta desbloqueada y los modelos no estan en cache).

## [Alfa 0.05] - 2026-03-02

### Added
- Sistema de logros: 45 logros en 4 categorias (carrera, hazana, secreto, emocional) con motor data-driven autocontenido en `pong/achievements.py`.
- Logros de carrera: hitos acumulados entre sesiones (partidos jugados, victorias, puntos totales, rallies acumulados) con escalado progresivo.
- Logros de hazana: proezas en un solo partido (rallies largos, rachas, juego/set/partido perfecto, remontada, velocidad).
- Logros secretos: 7 logros ocultos con condiciones sorpresa (rally de 42, trasnochador, respuestas unanimes, humillacion total, victoria monocromo).
- Logros emocionales: 6 logros relacionados con el estado emocional de la IA (furioso, deprimido, euforico, erratico, espectro completo, domador de fieras).
- Notificacion visual de logro desbloqueado: popup estilo ZX Spectrum con borde cyan, nombre en amarillo y flavor text en blanco. Auto-cierre tras 3.5 segundos con fade-out. Cola FIFO para multiples logros.
- Sonido de logro: chirp ascendente (880-1320 Hz) generado proceduralmente con onda cuadrada.
- Persistencia de logros y estadisticas de carrera en `game_history.json` con migracion automatica desde formato v1.0 (Alfa 0.04).
- Retroactividad: al actualizar desde Alfa 0.04, los logros de carrera se conceden automaticamente segun las sesiones existentes.
- Resumen de logros en la pantalla final: contador X/45 y lista de ultimos logros desbloqueados.
- Nuevo modulo: `pong/achievements.py`.
- Nuevos tests: `test_achievements.py` (53 tests). Total proyecto: 163 tests.

### Changed
- `save_manager.py`: formato JSON ampliado a v1.1 con claves `achievements` y `career_stats`. Firma de `save_session()` ampliada con parametros opcionales retrocompatibles.
- `sound.py`: nueva funcion `_build_achievement_chirp()` y metodo `play_achievement()` en `RetroSoundManager`.
- `renderer.py`: nuevos metodos `draw_achievement_popup()` y `_draw_achievements_summary()`. Firma de `draw_end_screen()` ampliada con parametro `achievements`.
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

