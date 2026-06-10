"""
tetris.py - Entry point for the Tetris game.

Structure (OOP):
    constants.py  → Game constants, colors, shapes
    piece.py      → Piece (tetromino) class
    board.py      → Board (grid) class
    effects.py    → Particle & LineClearEffect classes
    renderer.py   → Renderer (drawing) class
    game.py       → TetrisGame (main controller) class
    tetris.py     → Entry point (this file)
"""

import sys
import pygame

from game import TetrisGame


def main():
    """Initialize pygame and start the Tetris game."""
    pygame.init()
    pygame.mixer.init()

    game = TetrisGame()
    game.run()

    sys.exit()


if __name__ == "__main__":
    main()
