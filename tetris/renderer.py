"""
renderer.py - Rendering / drawing class.
Handles all visual output: board, pieces, sidebar, overlays, and effects.
"""

import pygame

from constants import (
    CELL_SIZE, COLS, ROWS, BOARD_WIDTH, BOARD_HEIGHT,
    SCREEN_WIDTH, SCREEN_HEIGHT, BOARD_1_X, BOARD_2_X, BOARD_Y,
    BG_COLOR, GRID_COLOR, GRID_LINE_COLOR, BORDER_COLOR,
    TEXT_COLOR, TEXT_DIM, GHOST_ALPHA,
    PIECE_COLORS, PIECE_GLOW, SHAPES,
)


class Renderer:
    """Handles all drawing operations for the Tetris game."""

    def __init__(self, screen):
        """
        Initialize the renderer with a pygame display surface.

        Args:
            screen: The main pygame display surface.
        """
        self.screen = screen
        self.font_large = pygame.font.SysFont("Segoe UI", 36, bold=True)
        self.font_medium = pygame.font.SysFont("Segoe UI", 22)
        self.font_small = pygame.font.SysFont("Segoe UI", 16)
        self.font_tiny = pygame.font.SysFont("Segoe UI", 13)

    # ─── Block Drawing ────────────────────────────────────────────────────

    def draw_block(self, x, y, color, glow=None, ghost=False):
        """
        Draw a single tetromino block at pixel position (x, y).

        Args:
            x: Pixel x position
            y: Pixel y position
            color: RGB tuple for the block
            glow: Optional RGB tuple for inner glow effect
            ghost: If True, draw as a semi-transparent ghost block
        """
        rect = pygame.Rect(x, y, CELL_SIZE - 1, CELL_SIZE - 1)
        if ghost:
            s = pygame.Surface((CELL_SIZE - 1, CELL_SIZE - 1), pygame.SRCALPHA)
            s.fill((*color, GHOST_ALPHA))
            self.screen.blit(s, (x, y))
            pygame.draw.rect(self.screen, (*color, 100), rect, 1)
            return

        # Main block
        pygame.draw.rect(self.screen, color, rect)

        # Highlight (top-left shine)
        highlight = tuple(min(c + 60, 255) for c in color)
        pygame.draw.line(self.screen, highlight, (x, y), (x + CELL_SIZE - 2, y), 2)
        pygame.draw.line(self.screen, highlight, (x, y), (x, y + CELL_SIZE - 2), 2)

        # Shadow (bottom-right)
        shadow = tuple(max(c - 80, 0) for c in color)
        pygame.draw.line(self.screen, shadow, (x + CELL_SIZE - 2, y),
                         (x + CELL_SIZE - 2, y + CELL_SIZE - 2), 2)
        pygame.draw.line(self.screen, shadow, (x, y + CELL_SIZE - 2),
                         (x + CELL_SIZE - 2, y + CELL_SIZE - 2), 2)

        # Inner glow
        if glow:
            inner = pygame.Rect(x + 3, y + 3, CELL_SIZE - 7, CELL_SIZE - 7)
            glow_surface = pygame.Surface((inner.width, inner.height), pygame.SRCALPHA)
            glow_surface.fill((*glow, 40))
            self.screen.blit(glow_surface, inner.topleft)

    def draw_mini_piece(self, piece_type, cx, cy, scale=0.7):
        """
        Draw a small piece preview (used in sidebar for HOLD / NEXT).

        Args:
            piece_type: The piece type key (e.g. 'T', 'I')
            cx: Pixel x for the top-left of the preview area
            cy: Pixel y for the top-left of the preview area
            scale: Scale factor relative to CELL_SIZE
        """
        cells = SHAPES[piece_type][0]
        color = PIECE_COLORS[piece_type]
        size = int(CELL_SIZE * scale)
        for bx, by in cells:
            px = cx + bx * size
            py = cy + by * size
            rect = pygame.Rect(px, py, size - 1, size - 1)
            pygame.draw.rect(self.screen, color, rect)
            highlight = tuple(min(c + 50, 255) for c in color)
            pygame.draw.line(self.screen, highlight, (px, py), (px + size - 2, py), 1)
            pygame.draw.line(self.screen, highlight, (px, py), (px, py + size - 2), 1)

    # ─── Board Drawing ────────────────────────────────────────────────────

    def draw_board(self, board, current_piece, ghost_y, board_x, board_y):
        """
        Draw the game board: grid, locked blocks, ghost piece, and active piece.

        Args:
            board: The Board object containing locked cell data.
            current_piece: The currently active Piece.
            ghost_y: The y position of the ghost (hard-drop preview).
            board_x: Pixel x offset of the board grid.
            board_y: Pixel y offset of the board grid.
        """
        # Board background & border
        board_rect = pygame.Rect(board_x - 2, board_y - 2,
                                  BOARD_WIDTH + 4, BOARD_HEIGHT + 4)
        pygame.draw.rect(self.screen, GRID_COLOR, board_rect)
        pygame.draw.rect(self.screen, BORDER_COLOR, board_rect, 2)

        # Grid lines
        for x in range(COLS + 1):
            px = board_x + x * CELL_SIZE
            pygame.draw.line(self.screen, GRID_LINE_COLOR,
                             (px, board_y), (px, board_y + BOARD_HEIGHT), 1)
        for y in range(ROWS + 1):
            py = board_y + y * CELL_SIZE
            pygame.draw.line(self.screen, GRID_LINE_COLOR,
                             (board_x, py), (board_x + BOARD_WIDTH, py), 1)

        # Locked blocks
        for y in range(ROWS):
            for x in range(COLS):
                cell = board.grid[y][x]
                if cell is not None:
                    px = board_x + x * CELL_SIZE
                    py = board_y + y * CELL_SIZE
                    self.draw_block(px, py, PIECE_COLORS[cell], PIECE_GLOW[cell])

        # Ghost piece
        if ghost_y != current_piece.y:
            ghost_cells = current_piece.get_cells_at(
                current_piece.x, ghost_y, current_piece.rotation)
            for gx, gy in ghost_cells:
                if gy >= 0:
                    px = board_x + gx * CELL_SIZE
                    py = board_y + gy * CELL_SIZE
                    self.draw_block(px, py, current_piece.color, ghost=True)

        # Current piece
        for cx, cy in current_piece.get_cells():
            if cy >= 0:
                px = board_x + cx * CELL_SIZE
                py = board_y + cy * CELL_SIZE
                self.draw_block(px, py, current_piece.color, current_piece.glow)

    # ─── Sidebar Drawing ─────────────────────────────────────────────────

    def draw_sidebar(self, held_piece, next_pieces, score, level, lines_cleared, combo, board_x, board_y):
        """
        Draw the sidebar containing HOLD, NEXT, SCORE, LEVEL, LINES, and COMBO.
        """
        sidebar_x = board_x + BOARD_WIDTH + 20

        # ── HOLD ──
        label = self.font_medium.render("HOLD", True, TEXT_DIM)
        self.screen.blit(label, (sidebar_x, board_y))
        hold_rect = pygame.Rect(sidebar_x, board_y + 28, 120, 75)
        pygame.draw.rect(self.screen, (20, 20, 45), hold_rect)
        pygame.draw.rect(self.screen, BORDER_COLOR, hold_rect, 1)
        if held_piece:
            self.draw_mini_piece(held_piece.type,
                                 sidebar_x + 15, board_y + 42, 0.6)

        # ── NEXT ──
        next_y = board_y + 120
        label = self.font_medium.render("NEXT", True, TEXT_DIM)
        self.screen.blit(label, (sidebar_x, next_y))
        for i, piece in enumerate(next_pieces):
            box_y = next_y + 28 + i * 75
            box_rect = pygame.Rect(sidebar_x, box_y, 120, 70)
            pygame.draw.rect(self.screen, (20, 20, 45), box_rect)
            pygame.draw.rect(self.screen, BORDER_COLOR, box_rect, 1)
            self.draw_mini_piece(piece.type, sidebar_x + 15, box_y + 12, 0.6)

        # ── SCORE ──
        score_y = next_y + 255
        label = self.font_small.render("SCORE", True, TEXT_DIM)
        self.screen.blit(label, (sidebar_x, score_y))
        score_text = self.font_large.render(f"{score:,}", True, TEXT_COLOR)
        self.screen.blit(score_text, (sidebar_x, score_y + 18))

        # ── LEVEL ──
        level_y = score_y + 60
        label = self.font_small.render("LEVEL", True, TEXT_DIM)
        self.screen.blit(label, (sidebar_x, level_y))
        level_text = self.font_medium.render(str(level), True, TEXT_COLOR)
        self.screen.blit(level_text, (sidebar_x, level_y + 18))

        # ── LINES ──
        lines_y = level_y + 50
        label = self.font_small.render("LINES", True, TEXT_DIM)
        self.screen.blit(label, (sidebar_x, lines_y))
        lines_text = self.font_medium.render(str(lines_cleared), True, TEXT_COLOR)
        self.screen.blit(lines_text, (sidebar_x, lines_y + 18))

        # ── COMBO ──
        if combo > 0:
            combo_y = lines_y + 55
            combo_color = (255, 200, 50) if combo >= 3 else (200, 200, 100)
            combo_text = self.font_medium.render(f"COMBO x{combo}", True, combo_color)
            self.screen.blit(combo_text, (sidebar_x, combo_y))

    # ─── Overlays ─────────────────────────────────────────────────────────

    def draw_title_bar(self, total_time):
        """Draw the title bar with game title and elapsed time."""
        title = self.font_medium.render("✦ T E T R I S  D U O ✦", True, (140, 140, 255))
        title_rect = title.get_rect(center=(SCREEN_WIDTH // 2, 20))
        self.screen.blit(title, title_rect)

        minutes = int(total_time) // 60
        seconds = int(total_time) % 60
        time_str = f"{minutes:02d}:{seconds:02d}"
        time_text = self.font_small.render(time_str, True, TEXT_DIM)
        time_rect = time_text.get_rect(center=(SCREEN_WIDTH // 2, 45))
        self.screen.blit(time_text, time_rect)

    def draw_controls_hint(self):
        """Draw the keyboard controls hint at the bottom."""
        p1_hints = [
            "Player 1 (Left):",
            "A/D Move  W Rotate CW  Q Rotate CCW",
            "S Soft Drop  SPACE Hard Drop  LSHIFT Hold"
        ]
        p2_hints = [
            "Player 2 (Right):",
            "←→ Move  ↑ Rotate CW  . Rotate CCW",
            "↓ Soft Drop  ENTER Hard Drop  RSHIFT Hold"
        ]
        y1 = BOARD_Y + BOARD_HEIGHT + 8
        for hint in p1_hints:
            text = self.font_tiny.render(hint, True, (80, 80, 120))
            self.screen.blit(text, (BOARD_1_X, y1))
            y1 += 15

        y2 = BOARD_Y + BOARD_HEIGHT + 8
        for hint in p2_hints:
            text = self.font_tiny.render(hint, True, (80, 80, 120))
            self.screen.blit(text, (BOARD_2_X, y2))
            y2 += 15

    def draw_game_over(self, score_p1, score_p2, p1_over, p2_over):
        """Draw the game over overlay with scores and winner details."""
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        go_text = self.font_large.render("GAME OVER", True, (255, 60, 60))
        go_rect = go_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 80))
        self.screen.blit(go_text, go_rect)

        if p1_over and p2_over:
            if score_p1 > score_p2:
                result_str = "Player 1 Wins!"
                color = (100, 255, 100)
            elif score_p2 > score_p1:
                result_str = "Player 2 Wins!"
                color = (100, 255, 100)
            else:
                result_str = "It's a Draw!"
                color = (255, 255, 100)
        else:
            if p1_over:
                result_str = "Player 2 Wins (P1 topped out)!"
                color = (100, 255, 100)
            else:
                result_str = "Player 1 Wins (P2 topped out)!"
                color = (100, 255, 100)

        result_text = self.font_medium.render(result_str, True, color)
        result_rect = result_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 20))
        self.screen.blit(result_text, result_rect)

        p1_score = self.font_medium.render(f"P1 Score: {score_p1:,}", True, TEXT_COLOR)
        p1_score_rect = p1_score.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 20))
        self.screen.blit(p1_score, p1_score_rect)

        p2_score = self.font_medium.render(f"P2 Score: {score_p2:,}", True, TEXT_COLOR)
        p2_score_rect = p2_score.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 50))
        self.screen.blit(p2_score, p2_score_rect)

        restart_text = self.font_small.render("Press R to Restart  |  Q to Quit", True, TEXT_DIM)
        restart_rect = restart_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 100))
        self.screen.blit(restart_text, restart_rect)

    def draw_player_game_over(self, board_x, board_y):
        """Draw an overlay over a single player's board when they game over."""
        overlay = pygame.Surface((BOARD_WIDTH, BOARD_HEIGHT), pygame.SRCALPHA)
        overlay.fill((80, 0, 0, 150))
        self.screen.blit(overlay, (board_x, board_y))

        go_text = self.font_medium.render("GAME OVER", True, (255, 100, 100))
        go_rect = go_text.get_rect(center=(board_x + BOARD_WIDTH // 2, board_y + BOARD_HEIGHT // 2))
        self.screen.blit(go_text, go_rect)

    def draw_pause(self):
        """Draw the pause overlay."""
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))

        pause_text = self.font_large.render("PAUSED", True, (180, 180, 255))
        pause_rect = pause_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 10))
        self.screen.blit(pause_text, pause_rect)

        hint_text = self.font_small.render("Press P or ESC to Resume", True, TEXT_DIM)
        hint_rect = hint_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 30))
        self.screen.blit(hint_text, hint_rect)

    def draw_flash(self, flash_timer, board_x, board_y):
        """Draw the board-wide flash when lines are cleared."""
        if flash_timer > 0:
            flash = pygame.Surface((BOARD_WIDTH, BOARD_HEIGHT), pygame.SRCALPHA)
            a = int(80 * (flash_timer / 0.2))
            flash.fill((255, 255, 255, a))
            self.screen.blit(flash, (board_x, board_y))

    def draw_background(self):
        """Draw the background with a subtle gradient."""
        self.screen.fill(BG_COLOR)
        for i in range(SCREEN_HEIGHT):
            alpha = int(15 + i * 0.02)
            pygame.draw.line(self.screen, (alpha, alpha, alpha + 10),
                             (0, i), (SCREEN_WIDTH, i))
