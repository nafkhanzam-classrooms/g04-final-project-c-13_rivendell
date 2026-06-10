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
from constants import SCREEN_WIDTH, SCREEN_HEIGHT, FPS


def main():
    """Initialize pygame and start the Tetris game."""
    pygame.init()
    pygame.mixer.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("✦ TETRIS ✦")
    clock = pygame.time.Clock()

    half_width = SCREEN_WIDTH // 2
    game1 = TetrisGame(screen, offset_x=0)
    game2 = TetrisGame(screen, offset_x=half_width)
    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0
        running = game1.handle_events() and game2.handle_events()
        game1.update(dt)
        game2.update(dt/2)
        game1.draw()
        game2.draw()
        pygame.display.flip()

    sys.exit()


if __name__ == "__main__":
    main()
