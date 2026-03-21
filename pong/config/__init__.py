"""
pong/config -- Constantes de configuracion del juego.

Aqui viven TODAS las constantes del proyecto: tamanos, colores, velocidades,
formato de partido, etc. Si necesitas cambiar algo del juego (la velocidad de
la pelota, el tamano de la ventana...), busca en el submodulo correspondiente.

Las constantes estan agrupadas por categoria en submodulos:
  - version:          Version de la aplicacion
  - zx_spectrum:      Pantalla de carga ZX y paleta de 16 colores + tema dinamico
  - layout:           Ventana, marcador, linea central, zona de narracion
  - colors:           Colores del juego (estilo Pong 1972)
  - gameplay:         Paletas, pelota, IA, formato de partido, FPS
  - narrator:         Narrador IA local, tiempos y sistema de preguntas
  - ui_end_screen:    Pantalla final de depuracion y resumen LLM
  - ui_achievements:  Sistema de logros (popup, galeria, estadisticas)
  - media:            Sonido retro, musica ZX Spectrum e imagen generativa

Para compatibilidad, todas las constantes se re-exportan desde este __init__,
por lo que `from pong.config import X` sigue funcionando.
"""

from pong.config.version import *
from pong.config.zx_spectrum import *
from pong.config.layout import *
from pong.config.colors import *
from pong.config.gameplay import *
from pong.config.narrator import *
from pong.config.ui_end_screen import *
from pong.config.ui_achievements import *
from pong.config.media import *
