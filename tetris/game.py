"""
game.py - Main game logic class (TetrisGame).
Orchestrates board, pieces, input, scoring, and rendering.
"""

import random
import pygame

from constants import (
    COLS, CELL_SIZE, BOARD_X, BOARD_Y,
    SCREEN_WIDTH, SCREEN_HEIGHT, FPS,
    PIECE_COLORS, WALL_KICKS, FALL_SPEEDS, BASE_SCORES,
)
from board import Board
from piece import Piece
from effects import Particle, LineClearEffect
from renderer import Renderer


class TetrisGame:
    """Main Tetris game controller — handles logic, input, and rendering."""

    def __init__(self):
        """Initialize pygame, create the window, and set up initial game state."""
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("✦ TETRIS ✦")
        self.clock = pygame.time.Clock()
        self.renderer = Renderer(self.screen)
        self.reset_game()

    # ─── State Management ─────────────────────────────────────────────────

    def reset_game(self):
        """Reset all game state to start a new game."""
        self.board = Board()
        self.bag = []
        self.current_piece = self._new_piece()
        self.next_pieces = [self._new_piece() for _ in range(3)]
        self.held_piece = None
        self.can_hold = True
        self.score = 0
        self.lines_cleared = 0
        self.level = 1
        self.combo = -1
        self.fall_timer = 0
        self.lock_timer = 0
        self.lock_delay = 0.5
        self.das_timer = 0
        self.das_delay = 0.15
        self.das_repeat = 0.05
        self.das_direction = 0
        self.das_charged = False
        self.soft_drop = False
        self.game_over = False
        self.paused = False
        self.particles = []
        self.line_effects = []
        self.flash_timer = 0
        self.total_time = 0
        self.back_to_back = False

    # ─── Piece Bag System (7-bag randomizer) ──────────────────────────────

    def _fill_bag(self):
        """Refill the piece bag with a shuffled set of all 7 tetromino types."""
        pieces = list(PIECE_COLORS.keys())
        random.shuffle(pieces)
        self.bag.extend(pieces)

    def _new_piece(self):
        """
        Get the next piece from the bag.

        Returns:
            A new Piece instance.
        """
        if len(self.bag) < 4:
            self._fill_bag()
        return Piece(self.bag.pop(0))

    def _spawn_next(self):
        """Move the first piece from the next queue to active, and refill queue."""
        self.current_piece = self.next_pieces.pop(0)
        self.next_pieces.append(self._new_piece())
        self.can_hold = True
        self.lock_timer = 0
        if self.board.is_game_over(self.current_piece):
            self.game_over = True

    # ─── Piece Actions ────────────────────────────────────────────────────

    def hold_piece(self):
        """Swap the current piece with the held piece (once per drop)."""
        if not self.can_hold:
            return
        self.can_hold = False
        if self.held_piece is None:
            self.held_piece = Piece(self.current_piece.type)
            self._spawn_next()
        else:
            temp = self.held_piece
            self.held_piece = Piece(self.current_piece.type)
            self.current_piece = temp
            self.current_piece.x = COLS // 2 - 2
            self.current_piece.y = -1
            self.current_piece.rotation = 0

    def rotate(self, direction=1):
        """
        Rotate the current piece with SRS wall kick tests.

        Args:
            direction: 1 for clockwise, -1 for counter-clockwise.

        Returns:
            True if rotation succeeded.
        """
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
        """
        Move the current piece horizontally.

        Args:
            dx: -1 for left, +1 for right.

        Returns:
            True if the move succeeded.
        """
        piece = self.current_piece
        new_cells = piece.get_cells_at(piece.x + dx, piece.y, piece.rotation)
        if self.board.is_valid(new_cells):
            piece.x += dx
            self.lock_timer = 0
            return True
        return False

    def hard_drop(self):
        """Instantly drop the piece to the bottom and lock it."""
        piece = self.current_piece
        drop_distance = 0
        while True:
            new_cells = piece.get_cells_at(piece.x, piece.y + 1, piece.rotation)
            if not self.board.is_valid(new_cells):
                break
            piece.y += 1
            drop_distance += 1
        self.score += drop_distance * 2
        self._lock_piece()

    def _get_ghost_y(self):
        """
        Calculate the y position where the piece would land (ghost preview).

        Returns:
            The y coordinate of the ghost piece.
        """
        piece = self.current_piece
        ghost_y = piece.y
        while True:
            new_cells = piece.get_cells_at(piece.x, ghost_y + 1, piece.rotation)
            if not self.board.is_valid(new_cells):
                break
            ghost_y += 1
        return ghost_y

    def _get_fall_speed(self):
        """Get the current gravity speed based on level."""
        idx = min(self.level - 1, len(FALL_SPEEDS) - 1)
        return FALL_SPEEDS[idx]

    # ─── Locking & Scoring ────────────────────────────────────────────────

    def _lock_piece(self):
        """Lock the current piece, clear lines, calculate score, and spawn next."""
        piece = self.current_piece
        self.board.lock_piece(piece)
        cleared = self.board.clear_lines()
        num_cleared = len(cleared)

        # Spawn particles and flash effects for cleared lines
        for row in cleared:
            self.line_effects.append(LineClearEffect(row, BOARD_X, BOARD_Y))
            for col in range(COLS):
                px = BOARD_X + col * CELL_SIZE + CELL_SIZE // 2
                py = BOARD_Y + row * CELL_SIZE + CELL_SIZE // 2
                color = PIECE_COLORS.get(piece.type, (255, 255, 255))
                for _ in range(5):
                    self.particles.append(Particle(px, py, color))

        # Scoring
        if num_cleared > 0:
            self.combo += 1
            line_score = BASE_SCORES.get(num_cleared, 0) * self.level

            # Back-to-back bonus for Tetris (4 lines)
            if num_cleared == 4:
                if self.back_to_back:
                    line_score = int(line_score * 1.5)
                self.back_to_back = True
            else:
                self.back_to_back = False

            # Combo bonus
            if self.combo > 0:
                line_score += 50 * self.combo * self.level

            self.score += line_score
            self.lines_cleared += num_cleared
            self.level = self.lines_cleared // 10 + 1
            self.flash_timer = 0.2
        else:
            self.combo = -1

        self._spawn_next()

    # ─── Game Loop ────────────────────────────────────────────────────────

    def update(self, dt):
        """
        Update game state for one frame.

        Args:
            dt: Delta time in seconds since last frame.
        """
        if self.game_over or self.paused:
            return

        self.total_time += dt

        # Update visual effects
        self.particles = [p for p in self.particles if p.update(dt)]
        self.line_effects = [e for e in self.line_effects if e.update(dt)]

        if self.flash_timer > 0:
            self.flash_timer -= dt

        # DAS (Delayed Auto Shift) for smooth horizontal movement
        if self.das_direction != 0:
            self.das_timer += dt
            if not self.das_charged:
                if self.das_timer >= self.das_delay:
                    self.das_charged = True
                    self.das_timer = 0
                    self.move(self.das_direction)
            else:
                if self.das_timer >= self.das_repeat:
                    self.das_timer = 0
                    self.move(self.das_direction)

        # Gravity
        speed = self._get_fall_speed()
        if self.soft_drop:
            speed = max(speed * 0.1, 0.02)
        self.fall_timer += dt

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
                    self._lock_piece()

        # Lock delay when piece is on the ground
        new_cells = self.current_piece.get_cells_at(
            self.current_piece.x, self.current_piece.y + 1,
            self.current_piece.rotation)
        if not self.board.is_valid(new_cells):
            self.lock_timer += dt
            if self.lock_timer >= self.lock_delay:
                self._lock_piece()

    def draw(self):
        """Render the entire frame using the Renderer."""
        r = self.renderer
        r.draw_background()
        r.draw_title_bar(self.total_time)
        r.draw_board(self.board, self.current_piece, self._get_ghost_y())
        r.draw_sidebar(self.held_piece, self.next_pieces,
                        self.score, self.level, self.lines_cleared, self.combo)
        r.draw_controls_hint()
        r.draw_flash(self.flash_timer)

        # Visual effects
        for effect in self.line_effects:
            effect.draw(self.screen)
        for particle in self.particles:
            particle.draw(self.screen)

        # Overlays
        if self.game_over:
            r.draw_game_over(self.score)
        elif self.paused:
            r.draw_pause()

        pygame.display.flip()

    # ─── Input Handling ───────────────────────────────────────────────────

    def handle_events(self):
        """
        Process all pygame events (keyboard input, quit).

        Returns:
            False if the game should exit, True otherwise.
        """
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            if event.type == pygame.KEYDOWN:
                if self.game_over:
                    if event.key == pygame.K_r:
                        self.reset_game()
                    elif event.key == pygame.K_q:
                        return False
                    continue

                if event.key in (pygame.K_p, pygame.K_ESCAPE):
                    self.paused = not self.paused
                    continue

                if self.paused:
                    continue

                if event.key == pygame.K_LEFT:
                    self.move(-1)
                    self.das_direction = -1
                    self.das_timer = 0
                    self.das_charged = False
                elif event.key == pygame.K_RIGHT:
                    self.move(1)
                    self.das_direction = 1
                    self.das_timer = 0
                    self.das_charged = False
                elif event.key == pygame.K_UP:
                    self.rotate(1)
                elif event.key == pygame.K_z:
                    self.rotate(-1)
                elif event.key == pygame.K_DOWN:
                    self.soft_drop = True
                elif event.key == pygame.K_SPACE:
                    self.hard_drop()
                elif event.key == pygame.K_c:
                    self.hold_piece()
                elif event.key == pygame.K_r:
                    self.reset_game()

            if event.type == pygame.KEYUP:
                if event.key == pygame.K_LEFT and self.das_direction == -1:
                    self.das_direction = 0
                elif event.key == pygame.K_RIGHT and self.das_direction == 1:
                    self.das_direction = 0
                elif event.key == pygame.K_DOWN:
                    self.soft_drop = False

        return True

    # ─── Run ──────────────────────────────────────────────────────────────

    def run(self):
        """Main game loop — runs until the player quits."""
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            running = self.handle_events()
            self.update(dt)
            self.draw()

        pygame.quit()
