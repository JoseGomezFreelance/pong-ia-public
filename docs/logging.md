# Logging estructurado

Pong IA usa el módulo `logging` de Python para reportar errores y
diagnósticos internos. En ejecución normal el juego no imprime nada
extra; con el flag `--debug` se activan mensajes detallados.


## Uso rápido

```bash
# Ejecucion normal (solo muestra WARNING y superiores)
python main.py

# Logging detallado (muestra DEBUG, INFO, WARNING, ERROR)
python main.py --debug

# Guardar los logs en un archivo
python main.py --debug 2> debug.log
```

Los mensajes de logging se emiten por **stderr**, por lo que no
interfieren con el output de juego en stdout
(`_emit_terminal_line`).


## Formato de salida

Cada línea de log sigue el patrón:

```
NIVEL [modulo] mensaje
```

Ejemplo:

```
ERROR [pong.narrator] Error en narracion LLM: connection timeout
DEBUG [pong.image_generator] Cargando pipeline de difusion...
```


## Niveles de logging

| Nivel     | Cuándo aparece | Ejemplo                              |
|-----------|----------------|--------------------------------------|
| `DEBUG`   | Solo con `--debug` | Detalles internos de carga de modelos |
| `INFO`    | Solo con `--debug` | Inicio de subsistemas                |
| `WARNING` | Siempre            | Situaciones inesperadas no críticas  |
| `ERROR`   | Siempre            | Fallos en llamadas LLM, generación de imágenes |


## Añadir logging a un módulo nuevo

Seguir el patrón ya establecido en `narrator.py` e `image_generator.py`:

```python
import logging

logger = logging.getLogger(__name__)

# Uso
logger.debug("Detalle solo visible con --debug")
logger.info("Evento informativo")
logger.warning("Algo inesperado pero no fatal")
logger.error("Fallo en operacion: %s", exc)
```

No hace falta configurar handlers ni formatters en cada módulo.
`setup_logging()` en `main.py` se encarga de la configuración
global al arrancar el proceso.


## Arquitectura

```
main.py / pong.py
  └─ setup_logging(debug=bool)
       └─ logging.basicConfig(level, format, stream=stderr)

pong/narrator.py      → logger = logging.getLogger(__name__)  (6 usos)
pong/image_generator.py → logger = logging.getLogger(__name__)
```

- `setup_logging()` se llama una vez al inicio, antes de crear `Game()`.
- Cada módulo obtiene su propio logger con `getLogger(__name__)`.
- El nivel global se controla con `--debug` (DEBUG) o por defecto (WARNING).


## Qué NO usa logging

- **`_emit_terminal_line()` en `game.py`**: Es output de juego para el
  usuario (puntos, narración, resumen). Se muestra en stdout y se
  acumula en `terminal_log_lines` para la función de copiar/exportar.
  No es logging diagnóstico.

- **`scripts/build_with_pyinstaller.py`**: Script standalone de build.
  Sus `print()` son mensajes de progreso del proceso de compilación.
