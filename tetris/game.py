"""
game.py - Main game logic class (TetrisGame) and PieceSequence generator.
Coordinates start menu navigation, single/dual player updates, and rendering.
"""

import random
import pygame
from constants import (
    SCREEN_WIDTH, SCREEN_HEIGHT, FPS,
    BOARD_1_X, BOARD_2_X, BOARD_SINGLE_X, BOARD_Y,
)
from piece import Piece
from player_state import PlayerState
from renderer import Renderer
from effects import Particle

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

# ─── Game States ────────────────────────────────────────────────────────────
STATE_MENU = 0
STATE_PLAYING = 1


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
    """Coordinates the start menu, single/dual-player game loops, and visual drawing."""

    def __init__(self):
        """Initialize pygame display and main menu states."""
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("✦ TETRIS DUO ✦")
        self.clock = pygame.time.Clock()
        self.renderer = Renderer(self.screen)

        self.p1_keys = P1_KEYS
        self.p2_keys = P2_KEYS

        # Main Menu Options
        self.menu_options = ["Solo Player", "Duo Player", "Exit"]
        self.reset_game_to_menu()

    def reset_game_to_menu(self):
        """Clean all playing state and open the start menu page."""
        self.state = STATE_MENU
        self.menu_selection = 0
        self.menu_particles = []
        self.p1 = None
        self.p2 = None
        self.single_player_mode = False
        self.paused = False
        self.total_time = 0

    def start_game(self, single_player=False):
        """Launch the game in either Single or Duo player mode."""
        self.state = STATE_PLAYING
        self.single_player_mode = single_player
        self.shared_sequence = PieceSequence()

        if self.single_player_mode:
            # Create a single player centered on screen
            self.p1 = PlayerState("Player 1", BOARD_SINGLE_X, BOARD_Y, self.p1_keys)
            self.p2 = None
            self.p1.init_pieces(self.shared_sequence, index_offset=0)
        else:
            # Create two players side-by-side
            self.p1 = PlayerState("Player 1", BOARD_1_X, BOARD_Y, self.p1_keys)
            self.p2 = PlayerState("Player 2", BOARD_2_X, BOARD_Y, self.p2_keys)
            self.p1.init_pieces(self.shared_sequence, index_offset=0)
            self.p2.init_pieces(self.shared_sequence, index_offset=0)

        self.paused = False
        self.total_time = 0

    def restart_match(self):
        """Restart the active game mode using a fresh piece sequence."""
        if self.state == STATE_PLAYING:
            self.start_game(self.single_player_mode)

    @property
    def is_game_over(self):
        """Returns True if the active players are game over."""
        if self.state != STATE_PLAYING:
            return False
        if self.single_player_mode:
            return self.p1.game_over
        return self.p1.game_over and self.p2.game_over

    def update_menu_particles(self, dt):
        """Spawn and update rising menu background particle sparks."""
        if len(self.menu_particles) < 40 and random.random() < 0.15:
            px = random.randint(0, SCREEN_WIDTH)
            py = SCREEN_HEIGHT + 10
            color = random.choice([
                (0, 240, 240), (240, 240, 0), (180, 0, 255),
                (0, 240, 0), (255, 50, 50), (50, 80, 255), (255, 160, 0)
            ])
            p = Particle(px, py, color)
            p.vy = random.uniform(-2.0, -0.5)
            p.vx = random.uniform(-0.4, 0.4)
            p.life = random.uniform(2.0, 5.0)
            p.max_life = p.life
            p.size = random.uniform(1.5, 4.0)
            self.menu_particles.append(p)

        self.menu_particles = [p for p in self.menu_particles if p.update(dt)]

    def update(self, dt):
        """Update active states depending on current mode."""
        if self.state == STATE_MENU:
            self.update_menu_particles(dt)
        elif self.state == STATE_PLAYING:
            if self.is_game_over or self.paused:
                return
            self.total_time += dt
            self.p1.update(dt, self.shared_sequence)
            if not self.single_player_mode:
                self.p2.update(dt, self.shared_sequence)

    def draw(self):
        """Render either the main menu or the playing boards."""
        r = self.renderer
        if self.state == STATE_MENU:
            r.draw_menu(self.menu_options, self.menu_selection, self.menu_particles)
        elif self.state == STATE_PLAYING:
            r.draw_background()
            r.draw_title_bar(self.total_time)

            # Draw Player 1
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

            # Draw Player 2 (If playing Duo)
            if not self.single_player_mode:
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

            # Global display guidelines
            r.draw_controls_hint()

            # Global overlays
            if self.is_game_over:
                score_p2 = 0 if self.single_player_mode else self.p2.score
                p2_over = True if self.single_player_mode else self.p2.game_over
                r.draw_game_over(self.p1.score, score_p2, self.p1.game_over, p2_over,
                                 self.single_player_mode)
            elif self.paused:
                r.draw_pause()

        pygame.display.flip()

    def handle_events(self):
        """Process start menu selectors and active gameplay keystrokes."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            if event.type == pygame.KEYDOWN:
                # ─── MENU STATE INPUTS ──────────────────────────────────────
                if self.state == STATE_MENU:
                    if event.key == pygame.K_UP:
                        self.menu_selection = (self.menu_selection - 1) % len(self.menu_options)
                    elif event.key == pygame.K_DOWN:
                        self.menu_selection = (self.menu_selection + 1) % len(self.menu_options)
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        # Action selection
                        if self.menu_selection == 0:  # Solo Player
                            self.start_game(single_player=True)
                        elif self.menu_selection == 1:  # Duo Player
                            self.start_game(single_player=False)
                        elif self.menu_selection == 2:  # Exit
                            return False
                    continue

                # ─── PLAYING STATE INPUTS ───────────────────────────────────
                if self.state == STATE_PLAYING:
                    # Escape or M behavior
                    if self.is_game_over:
                        if event.key == pygame.K_r:
                            self.restart_match()
                        elif event.key in (pygame.K_m, pygame.K_ESCAPE):
                            self.reset_game_to_menu()
                        elif event.key == pygame.K_q:
                            return False
                        continue

                    # Pause/Resume Escape toggle
                    if event.key == pygame.K_ESCAPE:
                        self.paused = not self.paused
                        continue
                    if event.key == pygame.K_p:
                        self.paused = not self.paused
                        continue

                    # If paused, check if Escape is pressed again to exit to menu
                    if self.paused:
                        if event.key == pygame.K_ESCAPE or event.key == pygame.K_m:
                            self.reset_game_to_menu()
                        continue

                    # Local Reset hotkey
                    if event.key == pygame.K_r:
                        self.restart_match()
                        continue

                    # Route Inputs to Player 1 (Active in both modes)
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

                    # Route Inputs to Player 2 (Only in Duo mode)
                    if not self.single_player_mode:
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

            if event.type == pygame.KEYUP and self.state == STATE_PLAYING and not self.paused:
                # P1 Key Release
                p1_ctrl = self.p1.controls
                if event.key == p1_ctrl['left'] and self.p1.das_direction == -1:
                    self.p1.das_direction = 0
                elif event.key == p1_ctrl['right'] and self.p1.das_direction == 1:
                    self.p1.das_direction = 0
                elif event.key == p1_ctrl['soft_drop']:
                    self.p1.soft_drop = False

                # P2 Key Release (Only in Duo Mode)
                if not self.single_player_mode:
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
