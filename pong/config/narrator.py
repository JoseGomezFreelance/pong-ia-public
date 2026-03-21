"""Narrador IA local, tiempos de narracion y sistema de preguntas."""

from __future__ import annotations

__all__ = [
    # Narrador IA local
    "NARRATION_INTERVAL_SECONDS",
    # Narracion asincrona
    "SUMMARY_MIN_REASONING_SECONDS",
    # Sistema de preguntas
    "QUESTION_FIRST_DELAY_SECONDS",
    "QUESTION_INTERVAL_SECONDS",
    "BULLET_TIME_DURATION_SECONDS",
    "BULLET_TIME_SPEED_MULTIPLIER",
    "ANSWER_THRESHOLD_PX",
    "COLOR_ANSWER_INACTIVE",
    "COLOR_ANSWER_ACTIVE",
    "COLOR_COUNTDOWN",
    "ANSWER_LABEL_X",
    "QUESTION_FONT_SIZE",
    "ANSWER_FONT_SIZE",
    "COUNTDOWN_FONT_SIZE",
    "INITIAL_QUESTIONS",
]


# ============================================================
# NARRADOR IA LOCAL
# ============================================================
# La configuracion del modelo LLM (archivo GGUF, context window, etc.)
# se define ahora en models.toml. Ver pong/config/models.py.
NARRATION_INTERVAL_SECONDS = 8  # Segundos entre narraciones automaticas (durante rallies)

# Breve pausa antes de mostrar el resumen
SUMMARY_MIN_REASONING_SECONDS = 0.5


# ============================================================
# SISTEMA DE PREGUNTAS DEL NARRADOR
# ============================================================
# El narrador hace preguntas al jugador durante el partido.
# El jugador responde moviendo la paleta: arriba del todo = Si,
# abajo del todo = No, cualquier otra posicion = Duda.
# Durante la pregunta el juego entra en "bullet time" (camara lenta).

# --- Tiempos ---
QUESTION_FIRST_DELAY_SECONDS = 30     # Segundos antes de la primera pregunta
QUESTION_INTERVAL_SECONDS = 30        # Segundos entre preguntas sucesivas
BULLET_TIME_DURATION_SECONDS = 5.0    # Duracion del bullet time en segundos reales
BULLET_TIME_SPEED_MULTIPLIER = 0.2    # Multiplicador de velocidad durante bullet time

# --- Umbral de respuesta ---
# La paleta (rect.top) se mueve de 0 (arriba) a GAME_AREA_HEIGHT - PADDLE_HEIGHT (abajo).
# Con umbral estricto: Si/No solo cuando la paleta esta pegada a la pared.
ANSWER_THRESHOLD_PX = 5               # Pixeles de margen desde el borde para Si/No

# --- Colores de las opciones ---
COLOR_ANSWER_INACTIVE = (80, 80, 80)   # Gris — opcion no seleccionada
COLOR_ANSWER_ACTIVE = (255, 255, 255)  # Blanco — opcion seleccionada
COLOR_COUNTDOWN = (120, 120, 120)      # Gris claro — temporizador de cuenta regresiva

# --- Posicion y fuentes ---
ANSWER_LABEL_X = 5                     # Pixeles desde el borde izquierdo de la ventana
QUESTION_FONT_SIZE = 22
ANSWER_FONT_SIZE = 20
COUNTDOWN_FONT_SIZE = 36

# --- 10 preguntas iniciales ---
# Al inicio del partido se elige una al azar y el LLM la reformula
# para que nunca se formule exactamente igual.
INITIAL_QUESTIONS = [
    "Crees que la suerte influye mas que la habilidad en este partido?",
    "Sientes que el ordenador esta jugando de forma predecible?",
    "Te parece que el ritmo del partido esta siendo demasiado rapido?",
    "Consideras que estas dominando el partido hasta ahora?",
    "Crees que podrias ganar este partido sin perder ningun set?",
    "Te sientes presionado por el marcador en este momento?",
    "Piensas que el ordenador deberia ser mas agresivo?",
    "Crees que tu estrategia actual es la correcta para ganar?",
    "Sientes que cada punto se esta volviendo mas importante?",
    "Te parece que este partido esta siendo emocionante hasta ahora?",
]
