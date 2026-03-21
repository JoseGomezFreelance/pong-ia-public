"""
Pong IA -- Punto de entrada principal.

Ejecuta el juego con:
    python main.py
    python main.py --debug   # logging detallado
"""

import argparse
import logging
import multiprocessing
import sys

from pong.game import Game


def setup_logging(*, debug: bool) -> None:
    """Configura el logging raiz del proceso."""
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.WARNING,
        format="%(levelname)s [%(name)s] %(message)s",
        stream=sys.stderr,
    )


if __name__ == "__main__":
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description="Pong IA")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Activa logging detallado (DEBUG)",
    )
    args = parser.parse_args()
    setup_logging(debug=args.debug)
    game = Game()
    game.run()
