"""Constantes de UI para la pantalla de rankings/clasificaciones."""

__all__ = [
    # Boton "Ranking" en pantalla final
    "END_SCREEN_RANKING_BUTTON_WIDTH",
    "END_SCREEN_RANKING_BUTTON_HEIGHT",
    "END_SCREEN_RANKING_BUTTON_TEXT",
    "COLOR_RANKING_BUTTON_BG",
    "COLOR_RANKING_BUTTON_HOVER_BG",
    "COLOR_RANKING_BUTTON_BORDER",
    # Pantalla de rankings
    "RANKING_SCREEN_MARGIN_X",
    "RANKING_SCREEN_MARGIN_TOP",
    "RANKING_SCREEN_HEADER_HEIGHT",
    "RANKING_TAB_WIDTH",
    "RANKING_TAB_HEIGHT",
    "RANKING_TAB_GAP",
    "RANKING_ROW_HEIGHT",
    "RANKING_CARD_WIDTH",
    "RANKING_CARD_HEIGHT",
    "RANKING_CARD_GAP_Y",
    # Colores
    "COLOR_RANKING_SELF",
    "COLOR_RANKING_PEER",
    "COLOR_RANKING_HEADER",
    "COLOR_RANKING_SUSPICIOUS",
    "COLOR_RANKING_TAB_ACTIVE",
    "COLOR_RANKING_TAB_INACTIVE",
    "COLOR_RANKING_TAB_HOVER",
    "COLOR_RANKING_FOOTER",
    # Boton "Volver"
    "RANKING_BACK_BUTTON_WIDTH",
    "RANKING_BACK_BUTTON_HEIGHT",
    "RANKING_BACK_BUTTON_TEXT",
    # Prompt de alias
    "ALIAS_PROMPT_WIDTH",
    "ALIAS_PROMPT_HEIGHT",
    "ALIAS_INPUT_WIDTH",
    "ALIAS_INPUT_HEIGHT",
    "ALIAS_MAX_LENGTH",
    "COLOR_ALIAS_INPUT_BG",
    "COLOR_ALIAS_INPUT_BORDER",
    "COLOR_ALIAS_ACCEPT_BG",
    "COLOR_ALIAS_ACCEPT_HOVER_BG",
    # Pantalla de conexion P2P
    "P2P_CONNECT_MIN_SECONDS",
    "P2P_CONNECT_MAX_SECONDS",
    "COLOR_P2P_CONNECT_TEXT",
    "COLOR_P2P_CONNECT_DETAIL",
    "COLOR_P2P_CONNECT_OK",
    "COLOR_P2P_CONNECT_SKIP",
]


# ============================================================
# BOTON "RANKING" EN PANTALLA FINAL
# ============================================================
END_SCREEN_RANKING_BUTTON_WIDTH = 120
END_SCREEN_RANKING_BUTTON_HEIGHT = 34
END_SCREEN_RANKING_BUTTON_TEXT = "Ranking"

COLOR_RANKING_BUTTON_BG = (0, 0, 170)            # ZX_BLUE_DARK
COLOR_RANKING_BUTTON_HOVER_BG = (85, 85, 255)    # ZX_BLUE_BRIGHT
COLOR_RANKING_BUTTON_BORDER = (85, 85, 255)       # ZX_BLUE_BRIGHT


# ============================================================
# PANTALLA DE RANKINGS (overlay)
# ============================================================
RANKING_SCREEN_MARGIN_X = 20
RANKING_SCREEN_MARGIN_TOP = 20
RANKING_SCREEN_HEADER_HEIGHT = 70

# Pestanas (5 categorias de record)
RANKING_TAB_WIDTH = 148
RANKING_TAB_HEIGHT = 28
RANKING_TAB_GAP = 4

# Tabla de rankings
RANKING_ROW_HEIGHT = 28
RANKING_CARD_WIDTH = 760
RANKING_CARD_HEIGHT = 44
RANKING_CARD_GAP_Y = 3

# Colores de la tabla
COLOR_RANKING_SELF = (85, 255, 85)            # ZX_GREEN_BRIGHT — entrada propia
COLOR_RANKING_PEER = (170, 170, 170)          # ZX_GRAY_LIGHT — peers
COLOR_RANKING_HEADER = (85, 255, 255)         # ZX_CYAN_BRIGHT — cabecera tabla
COLOR_RANKING_SUSPICIOUS = (255, 85, 85)      # ZX_RED_BRIGHT — sospechoso
COLOR_RANKING_TAB_ACTIVE = (85, 85, 255)      # ZX_BLUE_BRIGHT
COLOR_RANKING_TAB_INACTIVE = (85, 85, 85)     # ZX_GRAY_DARK
COLOR_RANKING_TAB_HOVER = (0, 0, 170)         # ZX_BLUE_DARK
COLOR_RANKING_FOOTER = (0, 170, 170)          # ZX_CYAN


# ============================================================
# BOTON "VOLVER"
# ============================================================
RANKING_BACK_BUTTON_WIDTH = 110
RANKING_BACK_BUTTON_HEIGHT = 34
RANKING_BACK_BUTTON_TEXT = "Volver"


# ============================================================
# PROMPT DE ALIAS (input de texto)
# ============================================================
ALIAS_PROMPT_WIDTH = 400
ALIAS_PROMPT_HEIGHT = 180
ALIAS_INPUT_WIDTH = 300
ALIAS_INPUT_HEIGHT = 32
ALIAS_MAX_LENGTH = 20

COLOR_ALIAS_INPUT_BG = (30, 30, 30)
COLOR_ALIAS_INPUT_BORDER = (85, 85, 255)      # ZX_BLUE_BRIGHT
COLOR_ALIAS_ACCEPT_BG = (0, 170, 0)           # ZX_GREEN_DARK
COLOR_ALIAS_ACCEPT_HOVER_BG = (85, 255, 85)   # ZX_GREEN_BRIGHT


# ============================================================
# PANTALLA DE CONEXION P2P
# ============================================================
P2P_CONNECT_MIN_SECONDS = 5            # Tiempo minimo de busqueda
P2P_CONNECT_MAX_SECONDS = 15           # Timeout si no encuentra peers
COLOR_P2P_CONNECT_TEXT = (0, 170, 170)    # ZX_CYAN
COLOR_P2P_CONNECT_DETAIL = (170, 170, 170)  # ZX_GRAY
COLOR_P2P_CONNECT_OK = (85, 255, 85)     # ZX_GREEN_BRIGHT
COLOR_P2P_CONNECT_SKIP = (170, 170, 170)  # ZX_GRAY
