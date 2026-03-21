"""Paletas, pelota, IA, formato de partido y velocidad del juego."""

__all__ = [
    # Paletas (paddles)
    "PADDLE_WIDTH",
    "PADDLE_HEIGHT",
    "PADDLE_SPEED",
    "PADDLE_MARGIN",
    # Pelota (ball)
    "BALL_SIZE",
    "BALL_SPEED_X",
    "BALL_SPEED_Y",
    # IA del ordenador
    "AI_SPEED",
    "AI_REACTION_ZONE",
    "AI_SPEED_MIN",
    "AI_SPEED_MAX",
    "EMOTION_LERP_FACTOR",
    # Deteccion de inactividad del jugador
    "PLAYER_TRACK_WINDOW",
    "PLAYER_IDLE_VARIANCE_THRESHOLD",
    "RALLY_IDLE_THRESHOLD",
    "RALLY_IDLE_RAMP",
    # Formato de partido
    "GAME_POINTS_TO_WIN",
    "SET_GAMES_TO_WIN",
    "MATCH_SETS_TO_WIN",
    # Velocidad del juego
    "FPS",
]


# ============================================================
# PALETAS (paddles)
# ============================================================
PADDLE_WIDTH = 15          # Ancho del rectangulo de la paleta (pixeles)
PADDLE_HEIGHT = 80         # Alto del rectangulo de la paleta (pixeles)
PADDLE_SPEED = 6           # Pixeles que se mueve la paleta del jugador por frame
PADDLE_MARGIN = 30         # Distancia desde el borde de la ventana a la paleta


# ============================================================
# PELOTA (ball)
# ============================================================
BALL_SIZE = 12             # Lado del cuadrado de la pelota (pixeles)
BALL_SPEED_X = 5           # Velocidad horizontal inicial (pixeles/frame)
BALL_SPEED_Y = 5           # Velocidad vertical inicial (pixeles/frame)


# ============================================================
# IA DEL ORDENADOR
# ============================================================
# El ordenador es mas lento que el jugador para que el juego sea justo.
AI_SPEED = 4               # Pixeles que se mueve la paleta de la IA por frame
AI_REACTION_ZONE = 10      # Zona muerta: la IA no se mueve si esta a menos de
                           # 10 pixeles del objetivo (evita temblequeo)

# --- IA emocional (activa tras la primera pregunta) ---
# La conversacion con el LLM modula el comportamiento de la paleta.
AI_SPEED_MIN = 2           # Velocidad minima (relajado / rendido)
AI_SPEED_MAX = 7           # Velocidad maxima (agresivo al maximo)
EMOTION_LERP_FACTOR = 0.02 # Interpolacion por frame: ~2-3 s de transicion

# --- Deteccion de inactividad del jugador ---
# El juego vigila si el jugador deja la raqueta quieta y explota el rally
# infinito (pelota recta). Cuando lo detecta, sube la agresividad autonomamente.
PLAYER_TRACK_WINDOW = 40              # Muestras de posicion (a 4 Hz = 10 segundos)
PLAYER_IDLE_VARIANCE_THRESHOLD = 100  # Varianza por debajo = idle
RALLY_IDLE_THRESHOLD = 15             # Golpes de rally a partir de los cuales se vigila
RALLY_IDLE_RAMP = 30                  # Golpes adicionales para urgencia maxima (15+30=45)


# ============================================================
# FORMATO DE PARTIDO
# ============================================================
# Un partido se estructura como en el tenis: puntos → juegos → sets.
# Estos valores son bajos para partidas rapidas de prueba.
GAME_POINTS_TO_WIN = 3     # Puntos necesarios para ganar un juego
SET_GAMES_TO_WIN = 2       # Juegos necesarios para ganar un set
MATCH_SETS_TO_WIN = 1      # Sets necesarios para ganar el partido


# ============================================================
# VELOCIDAD DEL JUEGO
# ============================================================
FPS = 60                   # Frames por segundo del bucle principal
