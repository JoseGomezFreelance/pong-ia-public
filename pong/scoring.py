"""
pong/scoring.py -- Sistema de marcador y logica de partido.

Este modulo maneja toda la logica de puntuacion del juego:
- Cuantos puntos lleva cada jugador.
- Cuando se gana un juego, un set o el partido.
- Las rachas de puntos consecutivos.

Usa un sistema parecido al tenis:
  Puntos → Juegos → Sets → Partido

La logica esta separada del resto del juego para que sea facil de
entender, probar y modificar sin tocar el codigo de pygame.

Contiene:
- ScoreState: dataclass con todo el estado del marcador.
- PointResult: dataclass con el resultado de aplicar un punto.
- apply_point(): funcion principal que aplica un punto y evalua consecuencias.
"""

from __future__ import annotations

from dataclasses import dataclass

from pong.config.gameplay import GAME_POINTS_TO_WIN, MATCH_SETS_TO_WIN, SET_GAMES_TO_WIN


# ============================================================
# ESTADO DEL MARCADOR
# ============================================================

@dataclass
class ScoreState:
    """
    Estado completo del marcador del partido.

    Agrupa todos los contadores de puntuacion en un solo objeto
    en vez de tenerlos como variables sueltas. Esto facilita pasar
    el marcador entre funciones y modulos.

    Atributos:
        player_points / computer_points:
            Puntos en el juego actual (se reinician al ganar un juego).
        player_games / computer_games:
            Juegos ganados en el set actual (se reinician al ganar un set).
        player_sets / computer_sets:
            Sets ganados en el partido.
        player_point_streak / computer_point_streak:
            Puntos consecutivos sin que el otro anote (para narracion).
    """

    player_points: int = 0
    computer_points: int = 0
    player_point_streak: int = 0
    computer_point_streak: int = 0
    player_games: int = 0
    computer_games: int = 0
    player_sets: int = 0
    computer_sets: int = 0

    def scoreboard_text(self) -> str:
        """
        Texto compacto del marcador para logs y prompts del narrador.

        Ejemplo: "Sets 1-0, Juegos 2-1, Puntos 2-0"

        Returns:
            String con el marcador formateado.
        """
        return (
            f"Sets {self.player_sets}-{self.computer_sets}, "
            f"Juegos {self.player_games}-{self.computer_games}, "
            f"Puntos {self.player_points}-{self.computer_points}"
        )

    def display_score_line(self) -> str:
        """
        Texto del marcador para la banda superior de la pantalla.

        Ejemplo: "SETS 1-0   |   JUEGOS 2-1   |   PUNTOS 2-0"

        Returns:
            String con el marcador formateado para el HUD.
        """
        return (
            f"SETS {self.player_sets}-{self.computer_sets}   |   "
            f"JUEGOS {self.player_games}-{self.computer_games}   |   "
            f"PUNTOS {self.player_points}-{self.computer_points}"
        )


# ============================================================
# RESULTADO DE UN PUNTO
# ============================================================

@dataclass
class PointResult:
    """
    Resultado de aplicar un punto al marcador.

    Cuando alguien anota, no solo sube el contador de puntos: puede
    que ese punto cierre un juego, un set o el partido entero. Este
    objeto dice exactamente que paso.

    Atributos:
        scorer_id:      "jugador" o "ordenador" (para el narrador).
        event_label:    Etiqueta del evento ("punto del jugador", "juego de...", etc.).
        last_play:      Texto descriptivo de lo que paso ("El jugador gano el punto").
        scoring_streak: Cuantos puntos consecutivos lleva el anotador.
        point_won:      True siempre (se anoto un punto).
        game_won:       True si ese punto ademas cerro un juego.
        set_won:        True si ese punto ademas cerro un set.
        match_won:      True si ese punto ademas cerro el partido.
    """

    scorer_id: str
    event_label: str
    last_play: str
    scoring_streak: int = 0
    point_won: bool = True
    game_won: bool = False
    set_won: bool = False
    match_won: bool = False


# ============================================================
# LOGICA DE MARCADOR
# ============================================================

def apply_point(score: ScoreState, winner: str) -> PointResult:
    """
    Aplica un punto al marcador y evalua si cierra juego, set o partido.

    Esta es la funcion principal del modulo. Recibe el estado del marcador
    y el ganador del punto, actualiza los contadores y devuelve un PointResult
    que indica todo lo que paso (si se gano juego, set, partido...).

    La logica escala asi:
    1. Siempre: sumar punto y actualizar rachas.
    2. Si el punto llega al limite → cerrar juego, resetear puntos.
    3. Si el juego llega al limite → cerrar set, resetear juegos.
    4. Si el set llega al limite → cerrar partido.

    Args:
        score:  ScoreState con el marcador actual (se modifica in-place).
        winner: "player" o "computer".

    Returns:
        PointResult con el detalle de lo que ocurrio.
    """

    # --- Paso 1: Sumar punto y actualizar rachas ---

    if winner == "player":
        score.player_points += 1
        winner_points = score.player_points
        loser_points = score.computer_points
        scorer_id = "jugador"
        winner_name = "el jugador"
        score.player_point_streak += 1
        score.computer_point_streak = 0
        scoring_streak = score.player_point_streak
        event_label = "punto del jugador"
    else:
        score.computer_points += 1
        winner_points = score.computer_points
        loser_points = score.player_points
        scorer_id = "ordenador"
        winner_name = "el ordenador"
        score.computer_point_streak += 1
        score.player_point_streak = 0
        scoring_streak = score.computer_point_streak
        event_label = "punto del ordenador"

    last_play = f"{winner_name.capitalize()} ganó el punto"

    result = PointResult(
        scorer_id=scorer_id,
        event_label=event_label,
        last_play=last_play,
        scoring_streak=scoring_streak,
    )

    # --- Paso 2: Comprobar si ese punto cierra un juego ---

    if winner_points < GAME_POINTS_TO_WIN:
        # No se gano juego todavia, solo fue un punto normal
        return result

    # Se gano el juego: sumar juego y resetear puntos
    if winner == "player":
        score.player_games += 1
    else:
        score.computer_games += 1

    result.last_play = f"Juego para {winner_name}"
    result.event_label = (
        "juego del jugador" if winner == "player" else "juego del ordenador"
    )
    result.game_won = True
    score.player_points = 0
    score.computer_points = 0

    # --- Paso 3: Comprobar si ese juego cierra un set ---

    if winner == "player":
        winner_games = score.player_games
    else:
        winner_games = score.computer_games

    if winner_games < SET_GAMES_TO_WIN:
        # No se gano set todavia
        return result

    # Se gano el set: sumar set y resetear juegos
    if winner == "player":
        score.player_sets += 1
    else:
        score.computer_sets += 1

    result.last_play = f"Set para {winner_name}"
    result.event_label = (
        "set del jugador" if winner == "player" else "set del ordenador"
    )
    result.set_won = True

    # --- Paso 4: Comprobar si ese set cierra el partido ---

    if (
        score.player_sets >= MATCH_SETS_TO_WIN
        or score.computer_sets >= MATCH_SETS_TO_WIN
    ):
        result.last_play = f"Partido para {winner_name}"
        result.event_label = (
            "partido del jugador"
            if winner == "player"
            else "partido del ordenador"
        )
        result.match_won = True
    else:
        # Nuevo set: resetear juegos
        score.player_games = 0
        score.computer_games = 0
        text = f"Comienza un nuevo set tras el set de {winner_name}"
        result.last_play = text.replace(" de el ", " del ")

    return result
