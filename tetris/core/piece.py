"""
piece.py - Tetromino piece class.
Handles piece state, rotation, and cell position calculations.
"""

from core.constants import COLS, SHAPES, PIECE_COLORS, PIECE_GLOW


class Piece:
    """Represents a single Tetris piece (tetromino)."""

    def __init__(self, shape_type):
        """
        Initialize a new piece.

        Args:
            shape_type: One of 'I', 'O', 'T', 'S', 'Z', 'J', 'L'
        """
        self.type = shape_type
        self.rotation = 0
        self.x = COLS // 2 - 2
        self.y = -1
        self.color = PIECE_COLORS[shape_type]
        self.glow = PIECE_GLOW[shape_type]

    def get_cells(self):
        """Get the board positions of all cells in the current state."""
        return [(self.x + cx, self.y + cy)
                for cx, cy in SHAPES[self.type][self.rotation]]

    def get_cells_at(self, x, y, rotation):
        """
        Get the board positions of all cells at a hypothetical position/rotation.

        Args:
            x: Hypothetical x position
            y: Hypothetical y position
            rotation: Hypothetical rotation index (0-3)
        """
        return [(x + cx, y + cy)
                for cx, cy in SHAPES[self.type][rotation]]
