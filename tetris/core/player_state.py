"""
player_state.py - Encapsulates the game state and logic for a single player.
This component is headless, having no dependencies on visual graphics or key bindings.
All internal timing is measured in integer simulation ticks at 60Hz.
"""

from core.constants import (
    COLS, WALL_KICKS, FALL_SPEEDS, BASE_SCORES
)
from core.board import Board
from core.piece import Piece


class PlayerState:
    """Manages board grid, active tetromino, timers, and input actions for one player."""

    def __init__(self, name="Player"):
        """
        Initialize player state.

        Args:
            name: String identifying the player (e.g., "Player 1")
        """
        self.name = name
        self.reset()

    def reset(self):
        """Reset player state to start a new game."""
        self.board = Board()
        self.piece_index = 0
        self.current_piece = None
        self.next_pieces = []
        self.held_piece = None
        self.can_hold = True
        self.score = 0
        self.lines_cleared = 0
        self.level = 1
        self.combo = -1
        self.fall_timer = 0
        self.lock_timer = 0
        self.lock_delay = 30     # 0.5 seconds * 60 ticks/second
        self.das_timer = 0
        self.das_delay = 9       # 0.15 seconds * 60 ticks/second
        self.das_repeat = 3      # 0.05 seconds * 60 ticks/second
        self.das_direction = 0
        self.das_charged = False
        self.soft_drop = False
        self.game_over = False
        self.back_to_back = False
        self.events = []

    def init_pieces(self, shared_sequence, index_offset=0):
        """
        Setup starting pieces from the shared sequence.

        Args:
            shared_sequence: The PieceSequence instance
            index_offset: Starting position index in the sequence
        """
        self.piece_index = index_offset
        self.current_piece = shared_sequence.get_piece(self.piece_index)
        self.piece_index += 1
        self.next_pieces = [
            shared_sequence.get_piece(self.piece_index),
            shared_sequence.get_piece(self.piece_index + 1),
            shared_sequence.get_piece(self.piece_index + 2)
        ]
        self.piece_index += 3
        self.can_hold = True
        self.lock_timer = 0
        if self.board.is_game_over(self.current_piece):
            self.game_over = True
            self.events.append({"type": "game_over"})

    def spawn_next(self, shared_sequence):
        """Move the first piece from the next queue to active, and fetch a new one."""
        self.current_piece = self.next_pieces.pop(0)
        self.next_pieces.append(shared_sequence.get_piece(self.piece_index))
        self.piece_index += 1
        self.can_hold = True
        self.lock_timer = 0
        if self.board.is_game_over(self.current_piece):
            self.game_over = True
            self.events.append({"type": "game_over"})

    def hold_piece(self, shared_sequence):
        """Swap current piece with held piece."""
        if not self.can_hold or self.game_over:
            return
        self.can_hold = False
        if self.held_piece is None:
            self.held_piece = Piece(self.current_piece.type)
            self.spawn_next(shared_sequence)
        else:
            temp = self.held_piece
            self.held_piece = Piece(self.current_piece.type)
            self.current_piece = temp
            self.current_piece.x = COLS // 2 - 2
            self.current_piece.y = -1
            self.current_piece.rotation = 0
        self.events.append({
            "type": "piece_held",
            "held_type": self.held_piece.type
        })

    def rotate(self, direction=1):
        """
        Rotate current piece (SRS).

        Args:
            direction: 1 for clockwise, -1 for counter-clockwise
        """
        if self.game_over:
            return False
        piece = self.current_piece
        old_rot = piece.rotation
        new_rot = (old_rot + direction) % 4

        kick_key = 'I' if piece.type == 'I' else 'default'
        kick_index = old_rot if direction == 1 else new_rot
        kicks = WALL_KICKS[kick_key][kick_index]

        if direction == -1:
            kicks = [(-dx, -dy) for dx, dy in kicks]

        for dx, dy in kicks:
            new_cells = piece.get_cells_at(piece.x + dx, piece.y + dy, new_rot)
            if self.board.is_valid(new_cells):
                piece.x += dx
                piece.y += dy
                piece.rotation = new_rot
                self.lock_timer = 0
                return True
        return False

    def move(self, dx):
        """Move current piece horizontally."""
        if self.game_over:
            return False
        piece = self.current_piece
        new_cells = piece.get_cells_at(piece.x + dx, piece.y, piece.rotation)
        if self.board.is_valid(new_cells):
            piece.x += dx
            self.lock_timer = 0
            return True
        return False

    def hard_drop(self, shared_sequence):
        """Drop current piece to the bottom and lock it."""
        if self.game_over:
            return
        piece = self.current_piece
        drop_distance = 0
        while True:
            new_cells = piece.get_cells_at(piece.x, piece.y + 1, piece.rotation)
            if not self.board.is_valid(new_cells):
                break
            piece.y += 1
            drop_distance += 1
        self.score += drop_distance * 2
        self.lock_piece(shared_sequence)

    def get_ghost_y(self):
        """Calculate y-coordinate of the ghost piece."""
        piece = self.current_piece
        ghost_y = piece.y
        while True:
            new_cells = piece.get_cells_at(piece.x, ghost_y + 1, piece.rotation)
            if not self.board.is_valid(new_cells):
                break
            ghost_y += 1
        return ghost_y

    def get_fall_speed(self):
        """Get speed of gravity in ticks based on level."""
        idx = min(self.level - 1, len(FALL_SPEEDS) - 1)
        return max(1, int(FALL_SPEEDS[idx] * 60))

    def lock_piece(self, shared_sequence):
        """Lock current piece, clear lines, handle scoring, spawn next."""
        piece = self.current_piece
        self.board.lock_piece(piece)
        cleared = self.board.clear_lines()
        num_cleared = len(cleared)

        # Notify visual layer that a piece locked and lines were cleared
        self.events.append({
            "type": "piece_locked",
            "piece_type": piece.type,
            "cleared_rows": cleared
        })

        # Score calculation
        if num_cleared > 0:
            self.combo += 1
            line_score = BASE_SCORES.get(num_cleared, 0) * self.level

            if num_cleared == 4:
                if self.back_to_back:
                    line_score = int(line_score * 1.5)
                self.back_to_back = True
            else:
                self.back_to_back = False

            if self.combo > 0:
                line_score += 50 * self.combo * self.level

            self.score += line_score
            self.lines_cleared += num_cleared
            self.level = self.lines_cleared // 10 + 1
        else:
            self.combo = -1

        self.spawn_next(shared_sequence)

    def update(self, ticks, shared_sequence):
        """Update physics timers based on integer simulation ticks."""
        if self.game_over:
            return

        # DAS handling
        if self.das_direction != 0:
            self.das_timer += ticks
            if not self.das_charged:
                if self.das_timer >= self.das_delay:
                    self.das_charged = True
                    self.das_timer = 0
                    self.move(self.das_direction)
            else:
                if self.das_timer >= self.das_repeat:
                    self.das_timer = 0
                    self.move(self.das_direction)

        # Gravity handling
        speed = self.get_fall_speed()
        if self.soft_drop:
            speed = max(int(speed * 0.1), 1)
        self.fall_timer += ticks

        if self.fall_timer >= speed:
            self.fall_timer = 0
            new_cells = self.current_piece.get_cells_at(
                self.current_piece.x, self.current_piece.y + 1,
                self.current_piece.rotation)
            if self.board.is_valid(new_cells):
                self.current_piece.y += 1
                if self.soft_drop:
                    self.score += 1
            else:
                self.lock_timer += speed
                if self.lock_timer >= self.lock_delay:
                    self.lock_piece(shared_sequence)

        # Ground contact lock delay
        new_cells = self.current_piece.get_cells_at(
            self.current_piece.x, self.current_piece.y + 1,
            self.current_piece.rotation)
        if not self.board.is_valid(new_cells):
            self.lock_timer += ticks
            if self.lock_timer >= self.lock_delay:
                self.lock_piece(shared_sequence)
