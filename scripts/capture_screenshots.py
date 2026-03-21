"""
Captura 5 screenshots del juego para itch.io con LLM real.

1. Terminal de boot ZX Spectrum
2. Portada pixel art ZX Spectrum
3. Gameplay con narracion IA real
4. Partida avanzada con marcador y narracion
5. Pantalla de fin de partido con logros
"""

import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame
pygame.init()

from pong.config.layout import WINDOW_WIDTH, WINDOW_HEIGHT

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dist", "screenshots")
os.makedirs(OUTPUT_DIR, exist_ok=True)

screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))


def save(name: str) -> None:
    path = os.path.join(OUTPUT_DIR, f"{name}.png")
    pygame.image.save(screen, path)
    print(f"  -> {name}.png")


# === 1. Terminal de boot ZX Spectrum ===
print("1. Terminal de boot ZX Spectrum...")
from pong.splash import ZXTerminal
terminal = ZXTerminal(screen)
total_steps = 9
terminal.add_line("Inicializando motor de juego...")
terminal.render(0, total_steps)
terminal.update_last_line("Motor de juego inicializado")
terminal.add_line("Entidades y marcador listos")
terminal.render(1, total_steps)
terminal.add_line("Generando efectos de sonido...")
terminal.render(2, total_steps)
terminal.update_last_line("Efectos de sonido listos")
terminal.render(3, total_steps)
terminal.add_line("Sintetizando tema musical MIDI...")
terminal.render(4, total_steps)
terminal.update_last_line("Musica cargada (ZX Spectrum beeper)")
terminal.add_line("Cargando narrador IA...")
terminal.render(5, total_steps)
terminal.update_last_line("Narrador: Qwen2.5-3B-Instruct Q4_K_M (4096 ctx)")
terminal.render(6, total_steps)
terminal.add_line("Modelo de difusion: en cache")
terminal.render(7, total_steps)
terminal.add_line("Preparando partida...")
terminal.render(8, total_steps)
terminal.add_line("Formato: 3 pts/juego, 2 juegos/set, 1 sets/partido")
terminal.add_line("Listo!")
terminal.render(total_steps, total_steps)
save("01_terminal_boot")

# === 2. Portada pixel art ZX Spectrum ===
print("2. Portada pixel art ZX Spectrum...")
from pong.splash import ZXTitleScreen
title = ZXTitleScreen(screen)
title.build()
if title._surface is not None:
    screen.blit(title._surface, (0, 0))
    btn_font = pygame.font.Font(None, 28)
    from pong.config.zx_spectrum import (
        ZX_TITLE_BUTTON_WIDTH, ZX_TITLE_BUTTON_HEIGHT,
        ZX_TITLE_BUTTON_GAP, ZX_WHITE, ZX_BLACK,
        ZX_GREEN_BRIGHT, ZX_CYAN_BRIGHT,
    )
    center_x = WINDOW_WIDTH // 2
    btn_y = WINDOW_HEIGHT // 2 + 80
    btn1_rect = pygame.Rect(0, 0, ZX_TITLE_BUTTON_WIDTH, ZX_TITLE_BUTTON_HEIGHT)
    btn1_rect.centerx = center_x
    btn1_rect.y = btn_y
    pygame.draw.rect(screen, ZX_GREEN_BRIGHT, btn1_rect)
    txt = btn_font.render("JUGAR", True, ZX_BLACK)
    screen.blit(txt, txt.get_rect(center=btn1_rect.center))
    btn2_rect = pygame.Rect(0, 0, ZX_TITLE_BUTTON_WIDTH, ZX_TITLE_BUTTON_HEIGHT)
    btn2_rect.centerx = center_x
    btn2_rect.y = btn_y + ZX_TITLE_BUTTON_HEIGHT + ZX_TITLE_BUTTON_GAP
    pygame.draw.rect(screen, ZX_CYAN_BRIGHT, btn2_rect)
    txt2 = btn_font.render("INSTALAR MODELOS IA", True, ZX_BLACK)
    screen.blit(txt2, txt2.get_rect(center=btn2_rect.center))
    pygame.display.flip()
    save("02_portada_zx")

pygame.quit()

# === 3, 4, 5: Gameplay con LLM real ===
print("\n3-5. Iniciando juego con LLM real...")

from pong.harness import GameHarness, HeadlessConfig


def capture(h: GameHarness, name: str) -> None:
    path = os.path.join(OUTPUT_DIR, f"{name}.png")
    h.save_screenshot(path)
    s = h.get_state()["score"]
    r = h.get_state()["rally_hits"]
    narr = h.get_state()["narration_text"][:80] if h.get_state()["narration_text"] else "(vacio)"
    print(f"  -> {name}.png  [{s['player_points']}-{s['computer_points']}  "
          f"G:{s['player_games']}-{s['computer_games']}  "
          f"S:{s['player_sets']}-{s['computer_sets']}  rally:{r}]")
    print(f"     narr: {narr}")


def track_ball(h: GameHarness) -> None:
    state = h.get_state()
    ball_y = state["ball"]["y"]
    player_y = state["player"]["y"]
    if ball_y < player_y:
        h.press_keys([pygame.K_UP])
    elif ball_y > player_y + 60:
        h.press_keys([pygame.K_DOWN])
    else:
        h.release_all_keys()


def force_goal(h: GameHarness, scorer: str = "computer") -> None:
    """Fuerza un gol moviendo la pelota fuera de la pantalla."""
    if scorer == "computer":
        # Pelota sale por la izquierda -> punto para computer
        h.game.ball.rect.x = -20
    else:
        # Pelota sale por la derecha -> punto para player
        h.game.ball.rect.x = WINDOW_WIDTH + 20
    h.step(1)  # El update() detecta el gol


def wait_for_narration(h: GameHarness, max_wait: float = 20.0) -> bool:
    initial = h.get_state()["narration_text"]
    start = time.monotonic()
    while time.monotonic() - start < max_wait:
        track_ball(h)
        h.step(1)
        current = h.get_state()["narration_text"]
        if current != initial and len(current) > 15:
            for _ in range(90):
                track_ball(h)
                h.step(1)
            return True
    print(f"     (timeout {max_wait}s)")
    return False


random.seed(42)
config = HeadlessConfig(
    enable_narration=True,
    enable_music=False,
    enable_sound=False,
    enable_imagegen=False,
    skip_splash=True,
)

with GameHarness.create(config) as h:
    # === 3. Gameplay con narracion ===
    print("3. Esperando narracion inicial...")
    h.step(1)
    wait_for_narration(h, max_wait=30.0)

    # Jugar un rally para escena dinamica
    for _ in range(200):
        track_ball(h)
        h.step(1)
    wait_for_narration(h, max_wait=15.0)
    capture(h, "03_gameplay_narracion")

    # === 4. Partida avanzada con marcador ===
    print("4. Forzando marcador avanzado...")
    # Forzar goles: computer 1, player 2, computer 1 -> puntos 2-2
    force_goal(h, "computer")
    wait_for_narration(h, max_wait=10.0)

    force_goal(h, "player")
    wait_for_narration(h, max_wait=10.0)

    force_goal(h, "player")
    wait_for_narration(h, max_wait=10.0)

    force_goal(h, "computer")
    wait_for_narration(h, max_wait=10.0)

    # Jugar un rally tras los goles
    for _ in range(200):
        track_ball(h)
        h.step(1)
    wait_for_narration(h, max_wait=10.0)

    capture(h, "04_partida_avanzada")

    # === 5. Fin de partido ===
    print("5. Forzando fin de partido...")
    # Necesitamos: 3 pts/juego, 2 juegos/set, 1 set/partido
    # Dar puntos al player para que gane
    for _ in range(20):
        if h.get_state()["showing_end_screen"]:
            break
        force_goal(h, "player")
        h.step(5)

    if h.get_state()["showing_end_screen"]:
        # Esperar renderizado + resumen LLM
        for _ in range(15):
            h.step(60)
            time.sleep(1)
        print("   Fin de partido!")
        capture(h, "05_fin_partido")
    else:
        print("   Estado final (no end screen)")
        capture(h, "05_estado_final")

print(f"\nScreenshots en: {OUTPUT_DIR}")
