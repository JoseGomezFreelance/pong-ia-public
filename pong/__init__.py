from __future__ import annotations

"""
Pong IA -- Pong clasico con narracion por IA local.

Este paquete contiene todo el codigo del juego, organizado en modulos:
- config.py          → Constantes (tamanos, colores, velocidades...)
- entities.py        → Paleta y Pelota
- sound.py           → Efectos de sonido retro
- narrator.py        → Narrador deportivo con IA local (LLM)
- scoring.py         → Sistema de marcador y logica de partido
- narration_bridge.py → Hilo de fondo para narracion sin congelar el juego
- renderer.py        → Dibujado de todos los elementos visuales
- achievements.py    → Sistema de logros inspirado en Cookie Clicker
- game.py            → Clase principal que orquesta todo

Para ejecutar el juego:
    python main.py
"""

from pong.config.version import APP_VERSION
from pong.game import Game
from pong.harness import GameHarness, HeadlessConfig

__all__ = ["Game", "APP_VERSION", "GameHarness", "HeadlessConfig"]
