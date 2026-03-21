"""
Perfil de rendimiento del game loop con cProfile.

Uso:
    python scripts/profile_game.py              # 600 frames, salida a terminal
    python scripts/profile_game.py --frames 1200 --output saves/profile.prof

Visualizar con snakeviz (pip install snakeviz):
    python -m snakeviz saves/profile.prof

Alternativa con py-spy (pip install py-spy):
    py-spy record -o saves/flamegraph.svg -- python main.py
"""

from __future__ import annotations

import argparse
import cProfile
import pstats
import sys
import os

# Asegurar que el directorio raiz del proyecto este en sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# SDL dummy drivers para headless
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


def main() -> None:
    parser = argparse.ArgumentParser(description="Profiling del game loop de Pong-IA")
    parser.add_argument("--frames", type=int, default=600, help="Frames a simular (default: 600)")
    parser.add_argument("--output", type=str, default=None, help="Guardar stats binarios (.prof)")
    args = parser.parse_args()

    from pong.harness import GameHarness

    with GameHarness.create() as h:
        # Warmup
        h.step(60)
        h.game.perf.reset()

        profiler = cProfile.Profile()
        profiler.enable()
        h.step(args.frames)
        profiler.disable()

        perf = h.get_perf()
        print(f"\n--- Metricas de rendimiento ({args.frames} frames) ---")
        print(h.game.perf.summary_line())
        print()

    if args.output:
        profiler.dump_stats(args.output)
        print(f"Perfil guardado en {args.output}")
        print(f"Visualizar: python -m snakeviz {args.output}")
    else:
        stats = pstats.Stats(profiler)
        stats.strip_dirs()
        stats.sort_stats("cumulative")
        stats.print_stats(30)


if __name__ == "__main__":
    main()
