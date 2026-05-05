"""Ventana, disposicion (layout), marcador, linea central y zona de narracion."""

__all__ = [
    # Ventana y disposicion
    "WINDOW_WIDTH",
    "GAME_AREA_HEIGHT",
    "NARRATION_HEIGHT",
    "SCORE_BAND_HEIGHT",
    "GAME_AREA_TOP",
    "XP_BAR_HEIGHT",
    "XP_BAR_TOP",
    "NARRATION_TOP",
    "WINDOW_HEIGHT",
    # Marcador y fuentes
    "SCORE_FONT_SIZE",
    "SCORE_DETAILS_FONT_SIZE",
    "SCORE_Y_POSITION",
    # Linea central punteada
    "CENTER_DASH_WIDTH",
    "CENTER_DASH_HEIGHT",
    "CENTER_DASH_GAP",
    # Zona de narracion
    "NARRATION_FONT_SIZE",
    "NARRATION_MARGIN_X",
    "NARRATION_LINE_SPACING",
    "NARRATION_TEXT_OFFSET_Y",
    "NARRATION_MAX_VISIBLE_LINES",
    "LLM_STATUS_FONT_SIZE",
]


# ============================================================
# VENTANA Y DISPOSICION (layout)
# ============================================================
# La ventana se divide en cuatro zonas apiladas de arriba a abajo:
#   1. Banda de marcador  (SCORE_BAND_HEIGHT)
#   2. Zona de juego      (GAME_AREA_HEIGHT)
#   3. Barra de XP RPG    (XP_BAR_HEIGHT)  — vacia si RPG no activo
#   4. Zona de narracion  (NARRATION_HEIGHT)

WINDOW_WIDTH = 800
GAME_AREA_HEIGHT = 500
NARRATION_HEIGHT = 200
SCORE_BAND_HEIGHT = 44
XP_BAR_HEIGHT = 22

# Posiciones calculadas a partir de las alturas anteriores
GAME_AREA_TOP = SCORE_BAND_HEIGHT
XP_BAR_TOP = GAME_AREA_TOP + GAME_AREA_HEIGHT
NARRATION_TOP = XP_BAR_TOP + XP_BAR_HEIGHT
WINDOW_HEIGHT = NARRATION_TOP + NARRATION_HEIGHT


# ============================================================
# INTERFAZ: MARCADOR Y FUENTES
# ============================================================
SCORE_FONT_SIZE = 48
SCORE_DETAILS_FONT_SIZE = 28
SCORE_Y_POSITION = 30


# ============================================================
# INTERFAZ: LINEA CENTRAL PUNTEADA
# ============================================================
# La linea vertical del centro esta hecha de pequenos rectangulos (dashes)
# separados por huecos, como en el Pong original de 1972.
CENTER_DASH_WIDTH = 4
CENTER_DASH_HEIGHT = 15
CENTER_DASH_GAP = 10


# ============================================================
# INTERFAZ: ZONA DE NARRACION
# ============================================================
NARRATION_FONT_SIZE = 26
NARRATION_MARGIN_X = 20         # Margen horizontal del texto de narracion
NARRATION_LINE_SPACING = 8      # Espacio extra entre lineas de narracion
NARRATION_TEXT_OFFSET_Y = 30    # Separacion vertical desde el borde superior de la zona
NARRATION_MAX_VISIBLE_LINES = 4 # Lineas visibles de narracion a la vez
LLM_STATUS_FONT_SIZE = 18       # Tamano del indicador "LLM ON/OFF" en esquina inferior
