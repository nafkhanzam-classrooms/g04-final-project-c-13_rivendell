"""
piece_sequence.py - Generates synchronized, deterministic streams of Tetris pieces.
"""

import random
from core.piece import Piece


class PieceSequence:
    """Generates a synchronized, deterministic stream of Tetris pieces for both players."""

    def __init__(self, seed=None):
        self.bag = []
        self.sequence = []
        self.random = random.Random(seed)

    def get_piece(self, index):
        """Fetch or generate the piece at the given index in the sequence."""
        while len(self.sequence) <= index:
            if not self.bag:
                # 7-bag randomizer refill
                pieces = ['I', 'O', 'T', 'S', 'Z', 'J', 'L']
                self.random.shuffle(pieces)
                self.bag.extend(pieces)
            self.sequence.append(self.bag.pop(0))
        return Piece(self.sequence[index])
