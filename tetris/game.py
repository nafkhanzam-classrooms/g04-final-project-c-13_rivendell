"""
game.py - Main game logic class (TetrisGame) and PieceSequence generator.
Coordinates dual player updates, routing controls, and drawing.
"""

import pygame
from constants import (
    SCREEN_WIDTH, SCREEN_HEIGHT, FPS,
    BOARD_1_X, BOARD_2_X, BOARD_Y,
)
from piece import Piece
from player_state import PlayerState
from renderer import Renderer

# ─── Dual Keyboard Control Schemes ──────────────────────────────────────────
P1_KEYS = {
    'left': pygame.K_a,
    'right': pygame.K_d,
    'rotate_cw': pygame.K_w,
    'rotate_ccw': pygame.K_q,
    'soft_drop': pygame.K_s,
    'hard_drop': pygame.K_SPACE,
    'hold': pygame.K_LSHIFT
}

P2_KEYS = {
    'left': pygame.K_LEFT,
    'right': pygame.K_RIGHT,
    'rotate_cw': pygame.K_UP,
    'rotate_ccw': pygame.K_PERIOD,
    'soft_drop': pygame.K_DOWN,
    'hard_drop': pygame.K_RETURN,
    'hold': pygame.K_RSHIFT
}


class PieceSequence:
    """Generates a synchronized, deterministic stream of Tetris pieces for both players."""

    def __init__(self):
        self.bag = []
        self.sequence = []

    def get_piece(self, index):
        """Fetch or generate the piece at the given index in the sequence."""
        while len(self.sequence) <= index:
            if not self.bag:
                # 7-bag randomizer refill
                pieces = ['I', 'O', 'T', 'S', 'Z', 'J', 'L']
                import random
                random.shuffle(pieces)
                self.bag.extend(pieces)
            self.sequence.append(self.bag.pop(0))
        return Piece(self.sequence[index])


class TetrisGame:
    """Coordinates the dual-player game loop, event management, and drawing."""

    def __init__(self):
        """Initialize pygame display and dual players."""
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("✦ TETRIS DUO ✦")
        self.clock = pygame.time.Clock()
        self.renderer = Renderer(self.screen)

        self.p1_keys = P1_KEYS
        self.p2_keys = P2_KEYS
        self.reset_game()

    def reset_game(self):
        """Reset dual player boards and recreate the synchronized piece stream."""
        self.shared_sequence = PieceSequence()

        self.p1 = PlayerState("Player 1", BOARD_1_X, BOARD_Y, self.p1_keys)
        self.p2 = PlayerState("Player 2", BOARD_2_X, BOARD_Y, self.p2_keys)

        # Initialize matching active pieces and previews
        self.p1.init_pieces(self.shared_sequence, index_offset=0)
        self.p2.init_pieces(self.shared_sequence, index_offset=0)

        self.paused = False
        self.total_time = 0

    @property
    def is_game_over(self):
        """Game is over when both players have topped out."""
        return self.p1.game_over and self.p2.game_over

    def update(self, dt):
        """Update game logic for both players."""
        if self.is_game_over or self.paused:
            return

        self.total_time += dt

        # Update players independently
        self.p1.update(dt, self.shared_sequence)
        self.p2.update(dt, self.shared_sequence)

    def draw(self):
        """Render the visual components for both players side-by-side."""
        r = self.renderer
        r.draw_background()
        r.draw_title_bar(self.total_time)

        # Draw Player 1 (Left)
        r.draw_board(self.p1.board, self.p1.current_piece, self.p1.get_ghost_y(),
                     self.p1.board_x, self.p1.board_y)
        r.draw_sidebar(self.p1.held_piece, self.p1.next_pieces, self.p1.score,
                       self.p1.level, self.p1.lines_cleared, self.p1.combo,
                       self.p1.board_x, self.p1.board_y)
        r.draw_flash(self.p1.flash_timer, self.p1.board_x, self.p1.board_y)

        for effect in self.p1.line_effects:
            effect.draw(self.screen)
        for particle in self.p1.particles:
            particle.draw(self.screen)

        if self.p1.game_over:
            r.draw_player_game_over(self.p1.board_x, self.p1.board_y)

        # Draw Player 2 (Right)
        r.draw_board(self.p2.board, self.p2.current_piece, self.p2.get_ghost_y(),
                     self.p2.board_x, self.p2.board_y)
        r.draw_sidebar(self.p2.held_piece, self.p2.next_pieces, self.p2.score,
                       self.p2.level, self.p2.lines_cleared, self.p2.combo,
                       self.p2.board_x, self.p2.board_y)
        r.draw_flash(self.p2.flash_timer, self.p2.board_x, self.p2.board_y)

        for effect in self.p2.line_effects:
            effect.draw(self.screen)
        for particle in self.p2.particles:
            particle.draw(self.screen)

        if self.p2.game_over:
            r.draw_player_game_over(self.p2.board_x, self.p2.board_y)

        # General info and overlays
        r.draw_controls_hint()

        if self.is_game_over:
            r.draw_game_over(self.p1.score, self.p2.score, self.p1.game_over, self.p2.game_over)
        elif self.paused:
            r.draw_pause()

        pygame.display.flip()

    def handle_events(self):
        """Process keyboard inputs, routing keys to active players."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            if event.type == pygame.KEYDOWN:
                # Global Pause/Resume
                if event.key in (pygame.K_p, pygame.K_ESCAPE):
                    if not self.is_game_over:
                        self.paused = not self.paused
                    continue

                # Restart / Quit
                if event.key == pygame.K_r:
                    self.reset_game()
                    continue
                if event.key == pygame.K_q and self.is_game_over:
                    return False

                if self.paused or self.is_game_over:
                    continue

                # Route Inputs to Player 1 (Left)
                p1_ctrl = self.p1.controls
                if not self.p1.game_over:
                    if event.key == p1_ctrl['left']:
                        self.p1.move(-1)
                        self.p1.das_direction = -1
                        self.p1.das_timer = 0
                        self.p1.das_charged = False
                    elif event.key == p1_ctrl['right']:
                        self.p1.move(1)
                        self.p1.das_direction = 1
                        self.p1.das_timer = 0
                        self.p1.das_charged = False
                    elif event.key == p1_ctrl['rotate_cw']:
                        self.p1.rotate(1)
                    elif event.key == p1_ctrl['rotate_ccw']:
                        self.p1.rotate(-1)
                    elif event.key == p1_ctrl['soft_drop']:
                        self.p1.soft_drop = True
                    elif event.key == p1_ctrl['hard_drop']:
                        self.p1.hard_drop(self.shared_sequence)
                    elif event.key == p1_ctrl['hold']:
                        self.p1.hold_piece(self.shared_sequence)

                # Route Inputs to Player 2 (Right)
                p2_ctrl = self.p2.controls
                if not self.p2.game_over:
                    if event.key == p2_ctrl['left']:
                        self.p2.move(-1)
                        self.p2.das_direction = -1
                        self.p2.das_timer = 0
                        self.p2.das_charged = False
                    elif event.key == p2_ctrl['right']:
                        self.p2.move(1)
                        self.p2.das_direction = 1
                        self.p2.das_timer = 0
                        self.p2.das_charged = False
                    elif event.key == p2_ctrl['rotate_cw']:
                        self.p2.rotate(1)
                    elif event.key == p2_ctrl['rotate_ccw']:
                        self.p2.rotate(-1)
                    elif event.key == p2_ctrl['soft_drop']:
                        self.p2.soft_drop = True
                    elif event.key == p2_ctrl['hard_drop']:
                        self.p2.hard_drop(self.shared_sequence)
                    elif event.key == p2_ctrl['hold']:
                        self.p2.hold_piece(self.shared_sequence)

            if event.type == pygame.KEYUP:
                # P1 Key Release
                p1_ctrl = self.p1.controls
                if event.key == p1_ctrl['left'] and self.p1.das_direction == -1:
                    self.p1.das_direction = 0
                elif event.key == p1_ctrl['right'] and self.p1.das_direction == 1:
                    self.p1.das_direction = 0
                elif event.key == p1_ctrl['soft_drop']:
                    self.p1.soft_drop = False

                # P2 Key Release
                p2_ctrl = self.p2.controls
                if event.key == p2_ctrl['left'] and self.p2.das_direction == -1:
                    self.p2.das_direction = 0
                elif event.key == p2_ctrl['right'] and self.p2.das_direction == 1:
                    self.p2.das_direction = 0
                elif event.key == p2_ctrl['soft_drop']:
                    self.p2.soft_drop = False

        return True

    def run(self):
        """Main game loop."""
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            running = self.handle_events()
            self.update(dt)
            self.draw()

        pygame.quit()
