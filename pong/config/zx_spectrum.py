"""Pantalla de carga ZX Spectrum y paleta de 16 colores."""

__all__ = [
    # Borde (franjas coloreadas estilo carga de cinta ZX)
    "ZX_BORDER_WIDTH",
    "ZX_BORDER_STRIPE_HEIGHT",
    "ZX_BORDER_TOP_HEIGHT",
    "ZX_BORDER_BOTTOM_HEIGHT",
    "ZX_BORDER_STRIPE_COLORS",
    # Area de terminal
    "ZX_TERMINAL_FONT_SIZE",
    "ZX_TERMINAL_LINE_HEIGHT",
    "ZX_TERMINAL_PADDING_X",
    "ZX_TERMINAL_PADDING_Y",
    "ZX_TERMINAL_MAX_LINES",
    # Cursor parpadeante
    "ZX_CURSOR_BLINK_MS",
    # Beep de arranque
    "ZX_BOOT_BEEP_FREQ",
    "ZX_BOOT_BEEP_DURATION",
    "ZX_BOOT_BEEP_VOLUME",
    # Portada (titulo pixel art procedural)
    "ZX_TITLE_DISPLAY_SECONDS",
    "ZX_TITLE_PIXEL_SIZE",
    # Paleta ZX Spectrum (16 colores, 4-bit)
    "ZX_BLACK",
    "ZX_WHITE",
    "ZX_GRAY_LIGHT",
    "ZX_GRAY_DARK",
    "ZX_BROWN",
    "ZX_GREEN_BRIGHT",
    "ZX_GREEN_DARK",
    "ZX_BLUE_BRIGHT",
    "ZX_BLUE_DARK",
    "ZX_MAGENTA_BRIGHT",
    "ZX_MAGENTA_DARK",
    "ZX_YELLOW",
    "ZX_RED_BRIGHT",
    "ZX_RED_DARK",
    "ZX_CYAN",
    "ZX_CYAN_BRIGHT",
    # Tema dinamico: tiempos de transicion
    "THEME_AWAKENING_DURATION",
    "THEME_COLOR_LERP_FACTOR",
    "THEME_BULLET_TIME_LERP",
    # Botones de portada
    "ZX_TITLE_BUTTON_WIDTH",
    "ZX_TITLE_BUTTON_HEIGHT",
    "ZX_TITLE_BUTTON_GAP",
    "ZX_TITLE_BUTTON_FONT_SIZE",
    # Pantalla de descarga
    "ZX_DOWNLOAD_PROGRESS_WIDTH",
]


# ============================================================
# PANTALLA DE CARGA ZX SPECTRUM
# ============================================================
# La pantalla de carga imita la estetica del Sinclair ZX Spectrum:
# borde de franjas de colores, terminal monocromo y portada pixel art.

# --- Borde (franjas coloreadas estilo carga de cinta ZX) ---
ZX_BORDER_WIDTH = 48               # Ancho de cada franja lateral (pixeles)
ZX_BORDER_STRIPE_HEIGHT = 6        # Altura de cada franja de color
ZX_BORDER_TOP_HEIGHT = 32          # Barra solida superior
ZX_BORDER_BOTTOM_HEIGHT = 32       # Barra solida inferior
ZX_BORDER_STRIPE_COLORS = [        # Patron ciclico de colores de las franjas
    (0, 170, 170),                  # ZX_CYAN
    (170, 0, 0),                    # ZX_RED_DARK
    (255, 255, 85),                 # ZX_YELLOW
    (0, 0, 170),                    # ZX_BLUE_DARK
    (170, 0, 170),                  # ZX_MAGENTA_DARK
    (0, 170, 0),                    # ZX_GREEN_DARK
    (255, 85, 85),                  # ZX_RED_BRIGHT
    (85, 85, 255),                  # ZX_BLUE_BRIGHT
]

# --- Area de terminal ---
ZX_TERMINAL_FONT_SIZE = 20         # Tamano de fuente monoespaciada
ZX_TERMINAL_LINE_HEIGHT = 24       # Separacion vertical entre lineas
ZX_TERMINAL_PADDING_X = 16         # Padding horizontal interior
ZX_TERMINAL_PADDING_Y = 12         # Padding vertical interior
ZX_TERMINAL_MAX_LINES = 28         # Maximo de lineas visibles

# --- Cursor parpadeante ---
ZX_CURSOR_BLINK_MS = 530           # Intervalo de parpadeo en ms

# --- Beep de arranque ---
ZX_BOOT_BEEP_FREQ = 880            # Frecuencia del beep (Hz)
ZX_BOOT_BEEP_DURATION = 0.15       # Duracion del beep (segundos)
ZX_BOOT_BEEP_VOLUME = 0.20         # Volumen (0.0 a 1.0)

# --- Portada (titulo pixel art procedural) ---
ZX_TITLE_DISPLAY_SECONDS = 4.0     # Segundos que se muestra la portada
ZX_TITLE_PIXEL_SIZE = 4            # Cada pixel logico = 4x4 pixeles reales


# ============================================================
# PALETA ZX SPECTRUM (16 colores, 4-bit)
# ============================================================
# Colores exactos del Sinclair ZX Spectrum (1982).
# Se usan para el tema dinamico que acompana el estado emocional de la IA.
ZX_BLACK          = (0, 0, 0)          # #000000
ZX_WHITE          = (255, 255, 255)    # #FFFFFF
ZX_GRAY_LIGHT     = (170, 170, 170)    # #AAAAAA
ZX_GRAY_DARK      = (85, 85, 85)       # #555555
ZX_BROWN          = (170, 85, 0)       # #AA5500
ZX_GREEN_BRIGHT   = (85, 255, 85)      # #55FF55
ZX_GREEN_DARK     = (0, 170, 0)        # #00AA00
ZX_BLUE_BRIGHT    = (85, 85, 255)      # #5555FF
ZX_BLUE_DARK      = (0, 0, 170)        # #0000AA
ZX_MAGENTA_BRIGHT = (255, 85, 255)     # #FF55FF
ZX_MAGENTA_DARK   = (170, 0, 170)      # #AA00AA
ZX_YELLOW         = (255, 255, 85)     # #FFFF55
ZX_RED_BRIGHT     = (255, 85, 85)      # #FF5555
ZX_RED_DARK       = (170, 0, 0)        # #AA0000
ZX_CYAN           = (0, 170, 170)      # #00AAAA
ZX_CYAN_BRIGHT    = (85, 255, 255)     # #55FFFF


# ============================================================
# TEMA DINAMICO: TIEMPOS DE TRANSICION
# ============================================================
# Controlan la velocidad de las transiciones de color entre fases
# y estados emocionales.
THEME_AWAKENING_DURATION = 3.0         # Segundos que dura la fase "despertar"
THEME_COLOR_LERP_FACTOR = 0.03        # Interpolacion por frame (~2-3 s)
THEME_BULLET_TIME_LERP = 0.08         # Lerp mas rapido durante bullet time


# ============================================================
# BOTONES DE PORTADA
# ============================================================
ZX_TITLE_BUTTON_WIDTH = 260            # Ancho de boton en la portada
ZX_TITLE_BUTTON_HEIGHT = 36            # Alto de boton en la portada
ZX_TITLE_BUTTON_GAP = 12              # Separacion vertical entre botones
ZX_TITLE_BUTTON_FONT_SIZE = 22        # Tamano de fuente de los botones


# ============================================================
# PANTALLA DE DESCARGA DE MODELOS
# ============================================================
ZX_DOWNLOAD_PROGRESS_WIDTH = 30       # Caracteres de la barra de progreso
