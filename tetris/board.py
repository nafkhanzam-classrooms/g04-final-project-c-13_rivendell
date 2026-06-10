"""
board.py - Game board (grid) class.
Manages the locked cells, collision detection, and line clearing.
"""

from constants import COLS, ROWS


class Board:
    """Represents the Tetris game board (10x20 grid)."""

    def __init__(self):
        """Initialize an empty board grid."""
        self.grid = [[None for _ in range(COLS)] for _ in range(ROWS)]

    def is_valid(self, cells):
        """
        Check if a set of cells can legally occupy the board.

        Args:
            cells: List of (x, y) tuples representing cell positions.

        Returns:
            True if all cells are within bounds and not overlapping locked pieces.
        """
        for x, y in cells:
            if x < 0 or x >= COLS or y >= ROWS:
                return False
            if y >= 0 and self.grid[y][x] is not None:
                return False
        return True

    def lock_piece(self, piece):
        """
        Lock a piece onto the board by writing its type into the grid cells.

        Args:
            piece: The Piece object to lock in place.
        """
        for x, y in piece.get_cells():
            if 0 <= y < ROWS and 0 <= x < COLS:
                self.grid[y][x] = piece.type

    def clear_lines(self):
        """
        Clear all completed lines from the board.

        Returns:
            List of row indices that were cleared.
        """
        cleared = []
        for y in range(ROWS):
            if all(cell is not None for cell in self.grid[y]):
                cleared.append(y)
        for y in cleared:
            del self.grid[y]
            self.grid.insert(0, [None for _ in range(COLS)])
        return cleared

    def is_game_over(self, piece):
        """
        Check if a newly spawned piece overlaps locked cells (game over).

        Args:
            piece: The newly spawned Piece object.

        Returns:
            True if the piece cannot be placed (game over condition).
        """
        return not self.is_valid(piece.get_cells())
