"""
renderer.py - Rendering / drawing class.
Handles all visual output: board, pieces, sidebar, overlays, and effects.
"""

import pygame

from core.constants import (
    CELL_SIZE, COLS, ROWS, BOARD_WIDTH, BOARD_HEIGHT,
    SCREEN_WIDTH, SCREEN_HEIGHT, BOARD_1_X, BOARD_2_X, BOARD_SINGLE_X, BOARD_Y,
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
        self.font_small_bold = pygame.font.SysFont("Segoe UI", 16, bold=True)
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

    def draw_network_labels(self):
        """Label the invariant network layout: local left, opponent right."""
        local = self.font_small.render("YOU - LOCAL", True, (0, 230, 245))
        remote = self.font_small.render("OPPONENT - VIA SERVER", True, (190, 100, 255))
        self.screen.blit(local, (BOARD_1_X, BOARD_Y - 20))
        self.screen.blit(remote, (BOARD_2_X, BOARD_Y - 20))

    def draw_network_latency(self, latency_ms, disconnected=False):
        """Draw a compact RTT indicator in the opponent/server-side corner."""
        if disconnected or latency_ms is None:
            color = (125, 130, 150)
            value = "-- ms"
        elif latency_ms < 80:
            color = (80, 225, 135)
            value = f"{latency_ms:.0f} ms"
        elif latency_ms < 150:
            color = (245, 195, 70)
            value = f"{latency_ms:.0f} ms"
        else:
            color = (255, 95, 105)
            value = f"{latency_ms:.0f} ms"

        panel_rect = pygame.Rect(SCREEN_WIDTH - 154, 10, 134, 34)
        panel = pygame.Surface(panel_rect.size, pygame.SRCALPHA)
        panel.fill((15, 17, 38, 225))
        self.screen.blit(panel, panel_rect)
        pygame.draw.rect(self.screen, (*color, 170), panel_rect, 1, border_radius=7)
        pygame.draw.circle(self.screen, color, (panel_rect.x + 15, panel_rect.centery), 5)
        text = self.font_small_bold.render(f"PING  {value}", True, color)
        self.screen.blit(text, text.get_rect(midleft=(panel_rect.x + 28, panel_rect.centery)))

    def draw_network_controls_hint(self, status):
        """Draw controls for the local player and transport status for the opponent."""
        hints = [
            "Local controls: A/D Move  W/Q Rotate  S Soft Drop",
            "SPACE Hard Drop  LSHIFT Hold  ESC/P Request Pause",
        ]
        y = BOARD_Y + BOARD_HEIGHT + 8
        for hint in hints:
            text = self.font_tiny.render(hint, True, (80, 80, 120))
            self.screen.blit(text, (BOARD_1_X, y))
            y += 16

        status_label = self.font_tiny.render("NETWORK", True, TEXT_DIM)
        self.screen.blit(status_label, (BOARD_2_X, BOARD_Y + BOARD_HEIGHT + 8))
        status_lines = self._wrap_text(status, self.font_tiny, 460)
        for index, line in enumerate(status_lines[:2]):
            status_text = self.font_tiny.render(line, True, (140, 140, 220))
            self.screen.blit(status_text,
                             (BOARD_2_X, BOARD_Y + BOARD_HEIGHT + 25 + index * 16))

    def draw_game_over(self, score_p1, score_p2, p1_over, p2_over, is_single_player=False):
        """Draw the game over overlay with scores and winner details."""
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        go_text = self.font_large.render("GAME OVER", True, (255, 60, 60))
        go_rect = go_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 80))
        self.screen.blit(go_text, go_rect)

        if is_single_player:
            score_text = self.font_medium.render(f"Final Score: {score_p1:,}", True, TEXT_COLOR)
            score_rect = score_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 10))
            self.screen.blit(score_text, score_rect)

            restart_text = self.font_small.render("Press R to Restart  |  M to Menu  |  Q to Quit", True, TEXT_DIM)
            restart_rect = restart_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 40))
            self.screen.blit(restart_text, restart_rect)
            return

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

        restart_text = self.font_small.render("Press R to Restart  |  M to Menu  |  Q to Quit", True, TEXT_DIM)
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

    def draw_pause(self, escape_hold_seconds=None):
        """Draw the pause overlay."""
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))

        pause_text = self.font_large.render("PAUSED", True, (180, 180, 255))
        pause_rect = pause_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 10))
        self.screen.blit(pause_text, pause_rect)

        if escape_hold_seconds is None:
            hint = "Press P or ESC to Resume"
        else:
            hint = "Tap P/ESC to Resume  |  Hold ESC 2 seconds to forfeit"
        hint_text = self.font_small.render(hint, True, TEXT_DIM)
        hint_rect = hint_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 30))
        self.screen.blit(hint_text, hint_rect)

        if escape_hold_seconds is not None:
            hold = min(max(escape_hold_seconds / 2.0, 0.0), 1.0)
            bar_rect = pygame.Rect(0, 0, 360, 10)
            bar_rect.center = (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 60)
            pygame.draw.rect(self.screen, (40, 42, 68), bar_rect, border_radius=5)
            if hold > 0:
                fill_rect = bar_rect.copy()
                fill_rect.width = max(1, int(bar_rect.width * hold))
                pygame.draw.rect(
                    self.screen, (255, 105, 115), fill_rect, border_radius=5
                )
            pygame.draw.rect(
                self.screen, (85, 90, 125), bar_rect, 1, border_radius=5
            )

    def draw_pause_pending(self):
        """Show that the client is waiting for the server pause decision."""
        panel = pygame.Surface((360, 54), pygame.SRCALPHA)
        panel.fill((15, 15, 35, 220))
        panel_rect = panel.get_rect(center=(SCREEN_WIDTH // 2, 95))
        self.screen.blit(panel, panel_rect)
        pygame.draw.rect(self.screen, (140, 140, 255), panel_rect, 1, border_radius=5)
        text = self.font_small.render("Waiting for server pause approval...", True, TEXT_COLOR)
        self.screen.blit(text, text.get_rect(center=panel_rect.center))

    def draw_reconnect_overlay(self, remaining_seconds, escape_hold_seconds):
        """Freeze-screen notice shared by the disconnected and waiting clients."""
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((4, 5, 16, 205))
        self.screen.blit(overlay, (0, 0))

        panel_rect = pygame.Rect(0, 0, 540, 250)
        panel_rect.center = (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)
        panel = pygame.Surface(panel_rect.size, pygame.SRCALPHA)
        panel.fill((18, 19, 44, 245))
        self.screen.blit(panel, panel_rect)
        pygame.draw.rect(
            self.screen, (255, 90, 105), panel_rect, 2, border_radius=12
        )

        title = self.font_large.render("CLIENT DISCONNECTED!", True, (255, 105, 115))
        self.screen.blit(title, title.get_rect(center=(panel_rect.centerx, panel_rect.y + 55)))

        waiting = self.font_medium.render(
            "Waiting for reconnection...", True, TEXT_COLOR
        )
        self.screen.blit(
            waiting, waiting.get_rect(center=(panel_rect.centerx, panel_rect.y + 103))
        )

        if remaining_seconds > 0:
            detail_text = f"Reconnect window: {remaining_seconds:.1f} seconds"
        else:
            detail_text = "Connection is still unavailable"
        detail = self.font_small.render(detail_text, True, TEXT_DIM)
        self.screen.blit(
            detail, detail.get_rect(center=(panel_rect.centerx, panel_rect.y + 137))
        )

        hold = min(max(escape_hold_seconds / 2.0, 0.0), 1.0)
        hint = self.font_small_bold.render(
            "Hold ESC for 2 seconds to forfeit and exit", True, (190, 195, 225)
        )
        self.screen.blit(
            hint, hint.get_rect(center=(panel_rect.centerx, panel_rect.y + 181))
        )

        bar_rect = pygame.Rect(panel_rect.x + 85, panel_rect.y + 210, 370, 12)
        pygame.draw.rect(self.screen, (40, 42, 68), bar_rect, border_radius=6)
        if hold > 0:
            fill_rect = bar_rect.copy()
            fill_rect.width = max(1, int(bar_rect.width * hold))
            pygame.draw.rect(self.screen, (255, 105, 115), fill_rect, border_radius=6)
        pygame.draw.rect(self.screen, (85, 90, 125), bar_rect, 1, border_radius=6)

    def draw_flash(self, flash_timer, board_x, board_y):
        """Draw the board-wide flash when lines are cleared."""
        if flash_timer > 0:
            flash = pygame.Surface((BOARD_WIDTH, BOARD_HEIGHT), pygame.SRCALPHA)
            a = int(80 * (flash_timer / 0.2))
            flash.fill((255, 255, 255, a))
            self.screen.blit(flash, (board_x, board_y))

    def draw_menu(self, options, selection, menu_particles):
        """Draw the interactive main start menu with rising background particles."""
        self.draw_background()

        # Draw background menu particles
        for p in menu_particles:
            p.draw(self.screen)

        # Draw title
        title_large = pygame.font.SysFont("Segoe UI", 64, bold=True)
        title_sub = pygame.font.SysFont("Segoe UI", 24)

        title_text = title_large.render("T E T R I S", True, (140, 140, 255))
        # Add a neon duplicate shadow
        title_glow = title_large.render("T E T R I S", True, (80, 80, 200))

        title_rect = title_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 140))
        glow_rect = title_glow.get_rect(center=(SCREEN_WIDTH // 2 + 4, SCREEN_HEIGHT // 2 - 136))

        self.screen.blit(title_glow, glow_rect)
        self.screen.blit(title_text, title_rect)

        sub_text = title_sub.render("✦  D U O   E D I T I O N  ✦", True, (200, 200, 255))
        sub_rect = sub_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 70))
        self.screen.blit(sub_text, sub_rect)

        # Draw options
        option_y = SCREEN_HEIGHT // 2 + 10
        for i, option in enumerate(options):
            is_selected = (i == selection)
            color = (255, 255, 255) if is_selected else TEXT_DIM
            text_style = pygame.font.SysFont("Segoe UI", 32, bold=is_selected)

            # Select indicator prefix
            text_str = f"▶  {option}  ◀" if is_selected else option
            text_surface = text_style.render(text_str, True, color)
            rect = text_surface.get_rect(center=(SCREEN_WIDTH // 2, option_y))

            # Draw selector background highlight
            if is_selected:
                highlight = pygame.Surface((rect.width + 40, rect.height + 10), pygame.SRCALPHA)
                highlight.fill((100, 100, 255, 30))
                self.screen.blit(highlight, (rect.x - 20, rect.y - 5))

            self.screen.blit(text_surface, rect)
            option_y += 60

        # Footer hints
        hint_text = self.font_small.render("Use ↑ / ↓ to Navigate  |  Press ENTER to Select", True, (80, 80, 120))
        hint_rect = hint_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 40))
        self.screen.blit(hint_text, hint_rect)

    def draw_duo_setup(self, ip_address, port, active_input, join_log,
                        create_log, ui_rects, menu_particles):
        """Draw side-by-side Join Server and Create Server placeholder panels."""
        self.draw_background()
        for particle in menu_particles:
            particle.draw(self.screen)

        title_font = pygame.font.SysFont("Segoe UI", 42, bold=True)
        section_font = pygame.font.SysFont("Segoe UI", 27, bold=True)
        input_font = pygame.font.SysFont("Consolas", 22)

        title = title_font.render("D U O   N E T W O R K", True, (140, 140, 255))
        self.screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 72)))
        subtitle = self.font_small.render(
            "Join an existing endpoint or prepare a local server endpoint",
            True, TEXT_DIM,
        )
        self.screen.blit(subtitle, subtitle.get_rect(center=(SCREEN_WIDTH // 2, 116)))

        left_panel = pygame.Rect(40, 150, 455, 515)
        right_panel = pygame.Rect(525, 150, 455, 515)
        for panel, accent in ((left_panel, (0, 220, 240)),
                              (right_panel, (180, 80, 255))):
            panel_surface = pygame.Surface(panel.size, pygame.SRCALPHA)
            panel_surface.fill((20, 20, 48, 225))
            self.screen.blit(panel_surface, panel.topleft)
            pygame.draw.rect(self.screen, accent, panel, 2, border_radius=8)

        join_title = section_font.render("JOIN SERVER", True, (0, 230, 245))
        self.screen.blit(join_title, join_title.get_rect(center=(267, 200)))
        create_title = section_font.render("CREATE SERVER", True, (190, 100, 255))
        self.screen.blit(create_title, create_title.get_rect(center=(752, 200)))

        self._draw_form_label("IP ADDRESS", 75, 248)
        from network.network_setup import get_local_ip
        self._draw_text_input(ui_rects["ip"], ip_address, get_local_ip(),
                              active_input == "ip", input_font)
        self._draw_form_label("PORT", 75, 348)
        self._draw_text_input(ui_rects["port"], port, "6578",
                              active_input == "port", input_font)
        self._draw_ui_button(ui_rects["join"], "JOIN", (0, 180, 210))

        join_lines = self._wrap_text(join_log, self.font_small, 370)
        is_error = "Invalid" in join_log or "must" in join_log
        for index, line in enumerate(join_lines[:3]):
            color = (255, 110, 110) if is_error else (120, 220, 230)
            rendered = self.font_small.render(line, True, color)
            self.screen.blit(rendered, (80, 545 + index * 23))

        create_hint = self.font_small.render(
            "Selects the first available configured port.", True, TEXT_DIM,
        )
        self.screen.blit(create_hint, create_hint.get_rect(center=(752, 253)))
        self._draw_ui_button(ui_rects["create"], "CREATE", (150, 70, 220))

        log_rect = pygame.Rect(565, 390, 380, 195)
        pygame.draw.rect(self.screen, (10, 10, 28), log_rect, border_radius=5)
        pygame.draw.rect(self.screen, (80, 70, 130), log_rect, 1, border_radius=5)
        log_title = self.font_small.render("SERVER LOG", True, TEXT_DIM)
        self.screen.blit(log_title, (580, 405))
        log_y = 440
        for entry in create_log:
            color = (170, 255, 190) if "prepared" in entry else TEXT_COLOR
            rendered = self.font_small.render(entry, True, color)
            self.screen.blit(rendered, (580, log_y))
            log_y += 28

        footer = self.font_small.render(
            "TAB: Switch Field   ENTER: Join   ESC: Back to Main Menu",
            True, (90, 90, 140),
        )
        self.screen.blit(footer, footer.get_rect(center=(SCREEN_WIDTH // 2, 735)))

    def _draw_form_label(self, text, x, y):
        label = self.font_small.render(text, True, TEXT_DIM)
        self.screen.blit(label, (x, y))

    def _draw_text_input(self, rect, value, placeholder, active, font):
        pygame.draw.rect(self.screen, (8, 8, 22), rect, border_radius=4)
        border = (0, 230, 245) if active else (75, 75, 125)
        pygame.draw.rect(self.screen, border, rect, 2, border_radius=4)
        display_value = value if value else placeholder
        color = TEXT_COLOR if value else (70, 70, 105)
        rendered = font.render(display_value, True, color)
        self.screen.blit(rendered, (rect.x + 14, rect.y + 11))
        if active and pygame.time.get_ticks() % 1000 < 500:
            cursor_x = rect.x + 14 + font.size(value)[0] + 2
            pygame.draw.line(self.screen, TEXT_COLOR,
                             (cursor_x, rect.y + 10), (cursor_x, rect.bottom - 10), 2)

    def _draw_ui_button(self, rect, text, color):
        mouse_over = rect.collidepoint(pygame.mouse.get_pos())
        fill = tuple(min(channel + 25, 255) for channel in color) if mouse_over else color
        pygame.draw.rect(self.screen, fill, rect, border_radius=5)
        pygame.draw.rect(self.screen, (220, 220, 255), rect, 1, border_radius=5)
        label = self.font_medium.render(text, True, (255, 255, 255))
        self.screen.blit(label, label.get_rect(center=rect.center))

    @staticmethod
    def _wrap_text(text, font, max_width):
        words = text.split()
        if not words:
            return [""]
        lines = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if font.size(candidate)[0] <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def draw_background(self):
        """Draw the background with a subtle gradient."""
        self.screen.fill(BG_COLOR)
        for i in range(SCREEN_HEIGHT):
            alpha = int(15 + i * 0.02)
            pygame.draw.line(self.screen, (alpha, alpha, alpha + 10),
                             (0, i), (SCREEN_WIDTH, i))
