"""
effects.py - Visual effects classes.
Handles particles and line clear flash animations.
"""

import random
import pygame

from constants import CELL_SIZE, BOARD_WIDTH


class Particle:
    """A single particle used for line clear visual effects."""

    def __init__(self, x, y, color):
        """
        Initialize a particle at position (x, y) with the given color.

        Args:
            x: Starting x pixel position
            y: Starting y pixel position
            color: RGB tuple for the particle color
        """
        self.x = x
        self.y = y
        self.color = color
        self.vx = random.uniform(-3, 3)
        self.vy = random.uniform(-5, -1)
        self.life = random.uniform(0.5, 1.5)
        self.max_life = self.life
        self.size = random.uniform(2, 5)

    def update(self, dt):
        """
        Update particle position and lifetime.

        Args:
            dt: Delta time in seconds.

        Returns:
            True if the particle is still alive.
        """
        self.x += self.vx * dt * 60
        self.y += self.vy * dt * 60
        self.vy += 0.15 * dt * 60  # gravity
        self.life -= dt
        return self.life > 0

    def draw(self, surface):
        """
        Draw the particle on the given surface.

        Args:
            surface: Pygame surface to draw on.
        """
        alpha = max(0, self.life / self.max_life)
        r = int(self.color[0] * alpha)
        g = int(self.color[1] * alpha)
        b = int(self.color[2] * alpha)
        size = max(1, int(self.size * alpha))
        pygame.draw.circle(surface, (r, g, b), (int(self.x), int(self.y)), size)


class LineClearEffect:
    """White flash animation that plays when a line is cleared."""

    def __init__(self, row, board_x, board_y):
        """
        Initialize a line clear flash effect.

        Args:
            row: The row index that was cleared.
            board_x: Pixel x offset of the board.
            board_y: Pixel y offset of the board.
        """
        self.row = row
        self.timer = 0.4
        self.max_timer = 0.4
        self.board_x = board_x
        self.board_y = board_y

    def update(self, dt):
        """
        Update the effect timer.

        Args:
            dt: Delta time in seconds.

        Returns:
            True if the effect is still active.
        """
        self.timer -= dt
        return self.timer > 0

    def draw(self, surface):
        """
        Draw the flash overlay on the cleared row.

        Args:
            surface: Pygame surface to draw on.
        """
        progress = 1.0 - (self.timer / self.max_timer)
        alpha = int(255 * (1.0 - progress))
        y = self.board_y + self.row * CELL_SIZE
        flash_surface = pygame.Surface((BOARD_WIDTH, CELL_SIZE), pygame.SRCALPHA)
        flash_surface.fill((255, 255, 255, alpha))
        surface.blit(flash_surface, (self.board_x, y))
