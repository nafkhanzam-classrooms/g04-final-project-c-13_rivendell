"""
game.py - Main game logic class (TetrisGame) and PieceSequence generator.
Coordinates start menu navigation, single/dual player updates, and rendering.
"""

import ipaddress
import os
import random
import struct
import subprocess
import sys
import pygame
from core.constants import (
    SCREEN_WIDTH, SCREEN_HEIGHT, FPS,
    BOARD_1_X, BOARD_2_X, BOARD_SINGLE_X, BOARD_Y,
    CELL_SIZE, PIECE_COLORS, COLS
)
from core.piece import Piece
from core.player_state import PlayerState
from ui.renderer import Renderer
from ui.effects import Particle, LineClearEffect
from network.network_client import NetworkClient
from network.network_setup import find_available_server_port, get_local_ip
from core.piece_sequence import PieceSequence
from network.protocol import (
    CONTROL_PAUSE, CONTROL_RESUME,
    MSG_CONTROL_COMMIT, MSG_CONTROL_REQUEST, MSG_ERROR, MSG_FORFEIT,
    MSG_MATCH_RESULT,
    MSG_FULL_SNAPSHOT, MSG_MATCH_START, MSG_PEER_STATUS, MSG_STATE_UPDATE,
    MSG_WELCOME, PEER_CONNECTED, PEER_DISCONNECTED, PEER_RECONNECTED,
    PEER_RECONNECTING, ProtocolError, decode_player_snapshot,
    encode_player_snapshot, unpack_error, unpack_welcome,
)

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
STATE_DUO_SETUP = 2


class PlayerUI:
    """Decorates PlayerState with UI-specific visual states and configuration metrics."""

    def __init__(self, name, board_x, board_y, controls, state=None):
        self.name = name
        self.board_x = board_x
        self.board_y = board_y
        self.controls = controls
        self.state = state if state is not None else PlayerState(name)
        self.particles = []
        self.line_effects = []
        self.flash_timer = 0.0

    def reset(self):
        self.state.reset()
        self.particles.clear()
        self.line_effects.clear()
        self.flash_timer = 0.0

    def process_events(self):
        """Process simulation events (particles, line clear, flash, etc.) since the last check."""
        while self.state.events:
            event = self.state.events.pop(0)
            if event["type"] == "piece_locked":
                cleared = event["cleared_rows"]
                piece_type = event["piece_type"]
                for row in cleared:
                    self.line_effects.append(LineClearEffect(row, self.board_x, self.board_y))
                    for col in range(COLS):
                        px = self.board_x + col * CELL_SIZE + CELL_SIZE // 2
                        py = self.board_y + row * CELL_SIZE + CELL_SIZE // 2
                        color = PIECE_COLORS.get(piece_type, (255, 255, 255))
                        for _ in range(5):
                            self.particles.append(Particle(px, py, color))
                if len(cleared) > 0:
                    self.flash_timer = 0.2

    def update_visuals(self, dt):
        self.particles = [p for p in self.particles if p.update(dt)]
        self.line_effects = [e for e in self.line_effects if e.update(dt)]
        if self.flash_timer > 0:
            self.flash_timer -= dt


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
        self.network_client = None
        self.server_process = None
        self.network_mode = False
        self.network_origin = None
        self.network_slot = None
        self.network_status = "Offline"
        self.network_snapshot_timer = 0
        self.network_match_finished = False
        self.network_winner_slot = None
        self.network_latency_ms = None
        self.network_waiting_reconnect = False
        self.network_reconnect_remaining = 0.0
        self.disconnect_escape_hold = 0.0
        self.network_escape_context = None
        self.network_recovery_bootstrap = False
        self.pause_pending = False
        self.tick_accumulator = 0.0

        # Main Menu Options
        self.menu_options = ["Solo Player", "Duo Player", "Exit"]
        self.reset_game_to_menu()

    def reset_game_to_menu(self):
        """Clean all playing state and open the start menu page."""
        self.shutdown_network()
        self.state = STATE_MENU
        self.menu_selection = 0
        self.menu_particles = []
        self.p1 = None
        self.p2 = None
        self.single_player_mode = False
        self.paused = False
        self.total_time = 0
        self.network_mode = False
        self.network_match_finished = False
        self.network_winner_slot = None
        self.network_latency_ms = None
        self.network_waiting_reconnect = False
        self.network_reconnect_remaining = 0.0
        self.disconnect_escape_hold = 0.0
        self.network_escape_context = None
        self.network_recovery_bootstrap = False
        self.pause_pending = False
        self.tick_accumulator = 0.0

    def open_duo_setup(self):
        """Open the placeholder screen for joining or creating a server."""
        self.state = STATE_DUO_SETUP
        self.duo_ip = get_local_ip()
        self.duo_port = "6578"
        self.duo_active_input = "ip"
        self.duo_join_log = "Enter the server IP address and port."
        self.duo_create_log = ["No server endpoint prepared yet."]
        self.duo_ui = {
            "ip": pygame.Rect(75, 275, 380, 48),
            "port": pygame.Rect(75, 375, 380, 48),
            "join": pygame.Rect(75, 465, 380, 52),
            "create": pygame.Rect(565, 295, 380, 56),
        }
        pygame.key.start_text_input()

    def close_duo_setup(self):
        """Return from the Duo setup screen to the main menu."""
        pygame.key.stop_text_input()
        self.reset_game_to_menu()

    def prepare_server_placeholder(self):
        """Start server.py and connect this game as the creating client."""
        if self.network_client is not None:
            return
        local_ip = get_local_ip()
        port = find_available_server_port()
        if port is None:
            self.duo_create_log = [
                "Unable to prepare server endpoint.",
                "Ports 6578, 6690, and 6635 are already assigned.",
            ]
            return

        server_path = os.path.join(os.path.dirname(__file__), "network", "server.py")
        creation_flags = 0
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            creation_flags = subprocess.CREATE_NO_WINDOW
        tetris_dir = os.path.dirname(__file__)
        env = {**os.environ, "PYTHONPATH": tetris_dir}
        try:
            self.server_process = subprocess.Popen(
                [sys.executable, server_path, "--host", "0.0.0.0", "--port", str(port)],
                cwd=tetris_dir,
                env=env,
                creationflags=creation_flags,
            )
        except OSError as exc:
            self.duo_create_log = ["Unable to start server.py.", str(exc)]
            return

        self.network_origin = "create"
        self.duo_create_log = [
            "Starting server.py...",
            f"Local IP: {local_ip}",
            f"Port: {port}",
            "Connecting local player...",
        ]
        self.start_network_client("127.0.0.1", port)

    def join_server_placeholder(self):
        """Validate the endpoint and connect as a joining client."""
        if self.network_client is not None:
            return
        try:
            ipaddress.ip_address(self.duo_ip.strip())
        except ValueError:
            self.duo_join_log = "Invalid IP address."
            return

        try:
            port = int(self.duo_port)
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            self.duo_join_log = "Port must be between 1 and 65535."
            return

        self.network_origin = "join"
        self.duo_join_log = f"Connecting to {self.duo_ip.strip()}:{port}..."
        self.start_network_client(self.duo_ip.strip(), port)

    def start_network_client(self, host, port):
        self.network_status = f"Connecting to {host}:{port}"
        self.network_client = NetworkClient(host, port)
        self.network_client.start()

    def shutdown_network(self):
        if self.network_client is not None:
            self.network_client.close()
            self.network_client = None
        if self.server_process is not None:
            if self.server_process.poll() is None:
                self.server_process.terminate()
                try:
                    self.server_process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self.server_process.kill()
            self.server_process = None
        self.network_slot = None
        self.network_origin = None
        self.network_latency_ms = None
        self.network_waiting_reconnect = False
        self.network_reconnect_remaining = 0.0
        self.disconnect_escape_hold = 0.0
        self.network_escape_context = None
        self.network_recovery_bootstrap = False

    def handle_duo_text_input(self, text):
        """Append filtered text to the active Duo setup field."""
        if self.duo_active_input == "ip":
            allowed = "0123456789abcdefABCDEF.:"
            filtered = "".join(char for char in text if char in allowed)
            self.duo_ip = (self.duo_ip + filtered)[:45]
        elif self.duo_active_input == "port":
            filtered = "".join(char for char in text if char.isdigit())
            self.duo_port = (self.duo_port + filtered)[:5]

    def set_connection_log(self, message, is_error=False):
        """Show transport progress in the panel that initiated the connection."""
        self.network_status = message
        if self.network_origin == "create":
            prefix = "Error: " if is_error else ""
            current_endpoint = self.duo_create_log[1:3] if len(self.duo_create_log) >= 3 else []
            self.duo_create_log = [prefix + message, *current_endpoint]
        else:
            self.duo_join_log = ("Error: " if is_error else "") + message

    def poll_network(self):
        """Apply queued WebSocket events on the Pygame main thread."""
        if self.network_client is None:
            return
        for event_type, data in self.network_client.poll():
            if event_type == "status":
                self.set_connection_log(data)
            elif event_type == "error":
                self.set_connection_log(data, is_error=True)
            elif event_type == "latency":
                self.network_latency_ms = data
            elif event_type == "reconnecting":
                self.network_waiting_reconnect = True
                self.network_reconnect_remaining = float(data)
                self.disconnect_escape_hold = 0.0
                self.network_escape_context = None
                self.network_status = "Client disconnected - waiting for reconnection"
            elif event_type == "transport_reconnected":
                self.network_status = "Connection restored - synchronizing game state"
            elif event_type == "reconnect_failed":
                self.network_latency_ms = None
                self.network_status = f"Reconnect failed: {data}"
            elif event_type == "closed":
                if self.state == STATE_PLAYING and not self.network_match_finished:
                    self.network_waiting_reconnect = True
                    self.network_status = "Client disconnected - waiting for reconnection"
            elif event_type == "packet":
                try:
                    self.handle_network_packet(data)
                except (ProtocolError, struct.error, ValueError) as exc:
                    self.set_connection_log(f"Invalid server packet: {exc}", is_error=True)

    def handle_network_packet(self, packet):
        if packet.message_type == MSG_WELCOME:
            slot, connected_count, session_token, reconnected = unpack_welcome(
                packet.payload
            )
            self.network_slot = slot
            self.network_client.set_session_token(session_token)
            if reconnected:
                self.network_recovery_bootstrap = not (
                    self.network_mode and self.state == STATE_PLAYING
                    and self.p1 is not None and self.p2 is not None
                )
                self.network_waiting_reconnect = True
                self.network_status = "Session restored - synchronizing game state"
            else:
                self.set_connection_log(
                    f"Connected as player {self.network_slot + 1}. "
                    f"Waiting for opponent ({connected_count}/2)..."
                )
            return

        if packet.message_type == MSG_MATCH_START:
            if len(packet.payload) != 4 or self.network_slot is None:
                raise ProtocolError("invalid MATCH_START payload")
            if (self.network_mode and self.state == STATE_PLAYING
                    and self.p1 is not None and self.p2 is not None):
                return
            seed = struct.unpack("!I", packet.payload)[0]
            self.start_network_game(seed)
            return

        if packet.message_type == MSG_STATE_UPDATE:
            snapshot = decode_player_snapshot(packet.payload)
            if snapshot["slot"] != self.network_slot:
                self.apply_remote_snapshot(snapshot)
            return

        if packet.message_type == MSG_FULL_SNAPSHOT:
            snapshot = decode_player_snapshot(packet.payload)
            self.apply_player_snapshot(snapshot)
            return

        if packet.message_type == MSG_CONTROL_COMMIT:
            if len(packet.payload) != 1 or packet.payload[0] not in (0, 1):
                raise ProtocolError("invalid CONTROL_COMMIT payload")
            self.paused = bool(packet.payload[0])
            self.pause_pending = False
            if not self.paused:
                self.disconnect_escape_hold = 0.0
                self.network_escape_context = None
            self.network_status = "Match paused" if self.paused else "Match resumed"
            return

        if packet.message_type == MSG_MATCH_RESULT:
            if len(packet.payload) != 2:
                raise ProtocolError("invalid MATCH_RESULT payload")
            self.network_winner_slot = packet.payload[0]
            self.network_match_finished = True
            self.paused = False
            self.pause_pending = False
            self.network_status = "Match finished"
            return

        if packet.message_type == MSG_PEER_STATUS:
            if len(packet.payload) != 2:
                raise ProtocolError("invalid PEER_STATUS payload")
            peer_slot, status = packet.payload
            if status not in (
                    PEER_CONNECTED, PEER_DISCONNECTED,
                    PEER_RECONNECTING, PEER_RECONNECTED):
                raise ProtocolError("invalid peer status")
            if status == PEER_RECONNECTED:
                self.network_waiting_reconnect = False
                self.network_reconnect_remaining = 0.0
                self.disconnect_escape_hold = 0.0
                self.network_escape_context = None
                self.network_status = "Reconnected - match resumed"
                self.network_snapshot_timer = 0.0
                self.send_local_snapshot()
                self.network_recovery_bootstrap = False
            elif peer_slot != self.network_slot:
                if status == PEER_CONNECTED:
                    self.set_connection_log("Opponent connected. Starting match...")
                elif status == PEER_RECONNECTING:
                    self.network_waiting_reconnect = True
                    self.network_reconnect_remaining = 15.0
                    self.disconnect_escape_hold = 0.0
                    self.network_escape_context = None
                    self.network_status = "Client disconnected - waiting for reconnection"
                elif status == PEER_DISCONNECTED:
                    self.network_waiting_reconnect = False
                    self.network_status = "Opponent disconnected"
            return

        if packet.message_type == MSG_ERROR:
            _, message = unpack_error(packet.payload)
            self.set_connection_log(message, is_error=True)
            return

    def start_network_game(self, seed):
        """Start one local-left player and one server-fed remote-right player."""
        pygame.key.stop_text_input()
        self.state = STATE_PLAYING
        self.single_player_mode = False
        self.network_mode = True
        self.shared_sequence = PieceSequence(seed)
        self.p1 = PlayerUI("You", BOARD_1_X, BOARD_Y, self.p1_keys)
        self.p2 = PlayerUI("Opponent", BOARD_2_X, BOARD_Y, {})
        self.p1.state.init_pieces(self.shared_sequence, index_offset=0)
        self.p2.state.init_pieces(self.shared_sequence, index_offset=0)
        self.paused = False
        self.pause_pending = False
        self.network_match_finished = False
        self.network_winner_slot = None
        self.network_snapshot_timer = 0
        self.network_latency_ms = None
        self.network_waiting_reconnect = self.network_recovery_bootstrap
        self.network_reconnect_remaining = (
            15.0 if self.network_recovery_bootstrap else 0.0
        )
        self.disconnect_escape_hold = 0.0
        self.network_escape_context = None
        self.total_time = 0
        if self.network_recovery_bootstrap:
            self.network_status = "Restoring previous match state"
        else:
            self.network_status = "Match connected"
            self.send_local_snapshot()

    def send_local_snapshot(self):
        if self.network_client is None or self.network_slot is None or self.p1 is None:
            return
        try:
            payload = encode_player_snapshot(self.p1.state, self.network_slot)
        except (ProtocolError, struct.error, OverflowError):
            return
        self.network_client.send(MSG_STATE_UPDATE, payload)

    def apply_remote_snapshot(self, snapshot):
        """Replace only the right-hand opponent state with server-provided data."""
        if self.p2 is None:
            return
        self.apply_snapshot_to_player(snapshot, self.p2)

    def apply_player_snapshot(self, snapshot):
        """Recover remote state without rolling back the frozen local player."""
        if (snapshot["slot"] == self.network_slot
                and self.network_recovery_bootstrap and self.p1 is not None):
            self.apply_snapshot_to_player(snapshot, self.p1)
        elif snapshot["slot"] != self.network_slot and self.p2 is not None:
            self.apply_snapshot_to_player(snapshot, self.p2)

    @staticmethod
    def apply_snapshot_to_player(snapshot, player):
        state = player.state
        state.board.grid = [row[:] for row in snapshot["board"]]
        current = Piece(snapshot["current_piece"])
        current.x = snapshot["x"]
        current.y = snapshot["y"]
        current.rotation = snapshot["rotation"]
        state.current_piece = current
        state.next_pieces = [Piece(piece_type)
                             for piece_type in snapshot["next_pieces"]]
        held_type = snapshot["held_piece"]
        state.held_piece = None if held_type is None else Piece(held_type)
        state.can_hold = snapshot["can_hold"]
        state.score = snapshot["score"]
        state.lines_cleared = snapshot["lines_cleared"]
        state.level = snapshot["level"]
        state.combo = snapshot["combo"]
        state.back_to_back = snapshot["back_to_back"]
        state.piece_index = snapshot["piece_index"]
        state.game_over = snapshot["game_over"]
        state.fall_timer = snapshot["fall_timer"]
        state.lock_timer = snapshot["lock_timer"]
        state.das_timer = snapshot["das_timer"]
        state.das_direction = snapshot["das_direction"]
        state.das_charged = snapshot["das_charged"]
        state.soft_drop = snapshot["soft_drop"]

    def request_network_pause(self):
        if self.network_client is None or self.pause_pending or self.network_match_finished:
            return
        action = CONTROL_RESUME if self.paused else CONTROL_PAUSE
        self.pause_pending = True
        self.network_status = "Pause request pending..." if not self.paused else "Resume request pending..."
        self.network_client.send(MSG_CONTROL_REQUEST, bytes((action,)))

    def forfeit_network_match(self):
        """Notify the server before leaving so the opponent wins immediately."""
        if self.network_client is not None:
            self.network_client.send_immediate(MSG_FORFEIT)
        self.reset_game_to_menu()

    def start_game(self, single_player=False):
        """Launch the game in either Single or Duo player mode."""
        self.state = STATE_PLAYING
        self.single_player_mode = single_player
        self.network_mode = False
        self.shared_sequence = PieceSequence()

        if self.single_player_mode:
            # Create a single player centered on screen
            self.p1 = PlayerUI("Player 1", BOARD_SINGLE_X, BOARD_Y, self.p1_keys)
            self.p2 = None
            self.p1.state.init_pieces(self.shared_sequence, index_offset=0)
        else:
            # Create two players side-by-side
            self.p1 = PlayerUI("Player 1", BOARD_1_X, BOARD_Y, self.p1_keys)
            self.p2 = PlayerUI("Player 2", BOARD_2_X, BOARD_Y, self.p2_keys)
            self.p1.state.init_pieces(self.shared_sequence, index_offset=0)
            self.p2.state.init_pieces(self.shared_sequence, index_offset=0)

        self.paused = False
        self.total_time = 0

    def restart_match(self):
        """Restart the active game mode using a fresh piece sequence."""
        if self.state == STATE_PLAYING and not self.network_mode:
            self.start_game(self.single_player_mode)

    @property
    def is_game_over(self):
        """Returns True if the active players are game over."""
        if self.state != STATE_PLAYING:
            return False
        if self.network_mode:
            return self.network_match_finished
        if self.single_player_mode:
            return self.p1.state.game_over
        return self.p1.state.game_over and self.p2.state.game_over

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
        self.poll_network()
        if self.state == STATE_MENU:
            self.update_menu_particles(dt)
        elif self.state == STATE_DUO_SETUP:
            self.update_menu_particles(dt)
        elif self.state == STATE_PLAYING:
            if self.network_mode and (self.network_waiting_reconnect or self.paused):
                if self.network_waiting_reconnect:
                    self.network_reconnect_remaining = max(
                        0.0, self.network_reconnect_remaining - dt
                    )
                can_hold_to_exit = (
                    self.network_waiting_reconnect
                    or self.network_escape_context == "paused"
                )
                if (can_hold_to_exit
                        and pygame.key.get_pressed()[pygame.K_ESCAPE]):
                    self.disconnect_escape_hold += dt
                    if self.disconnect_escape_hold >= 2.0:
                        self.forfeit_network_match()
                else:
                    self.disconnect_escape_hold = 0.0
                return
            if self.is_game_over or self.paused:
                return
            self.total_time += dt

            # Update visuals (particles, flashes, visual timers)
            self.p1.update_visuals(dt)
            if not self.single_player_mode:
                self.p2.update_visuals(dt)

            # Step physics core with tick accumulator (60Hz fixed logic)
            self.tick_accumulator += dt
            ticked = False
            while self.tick_accumulator >= 1.0 / 60.0:
                self.p1.state.update(1, self.shared_sequence)
                if not self.single_player_mode and not self.network_mode:
                    self.p2.state.update(1, self.shared_sequence)
                self.tick_accumulator -= 1.0 / 60.0
                ticked = True

            if ticked:
                self.p1.process_events()
                if not self.single_player_mode and not self.network_mode:
                    self.p2.process_events()

            if self.network_mode:
                self.network_snapshot_timer += dt
                if self.network_snapshot_timer >= 0.05:
                    self.network_snapshot_timer = 0
                    self.send_local_snapshot()

    def draw(self):
        """Render either the main menu or the playing boards."""
        r = self.renderer
        if self.state == STATE_MENU:
            r.draw_menu(self.menu_options, self.menu_selection, self.menu_particles)
        elif self.state == STATE_DUO_SETUP:
            r.draw_duo_setup(
                self.duo_ip, self.duo_port, self.duo_active_input,
                self.duo_join_log, self.duo_create_log, self.duo_ui,
                self.menu_particles,
            )
        elif self.state == STATE_PLAYING:
            r.draw_background()
            r.draw_title_bar(self.total_time)
            if self.network_mode:
                r.draw_network_labels()
                r.draw_network_latency(
                    self.network_latency_ms,
                    self.network_waiting_reconnect,
                )

            # Draw Player 1
            r.draw_board(self.p1.state.board, self.p1.state.current_piece, self.p1.state.get_ghost_y(),
                         self.p1.board_x, self.p1.board_y)
            r.draw_sidebar(self.p1.state.held_piece, self.p1.state.next_pieces, self.p1.state.score,
                           self.p1.state.level, self.p1.state.lines_cleared, self.p1.state.combo,
                           self.p1.board_x, self.p1.board_y)
            r.draw_flash(self.p1.flash_timer, self.p1.board_x, self.p1.board_y)

            for effect in self.p1.line_effects:
                effect.draw(self.screen)
            for particle in self.p1.particles:
                particle.draw(self.screen)

            if self.p1.state.game_over:
                r.draw_player_game_over(self.p1.board_x, self.p1.board_y)

            # Draw Player 2 (If playing Duo)
            if not self.single_player_mode:
                r.draw_board(self.p2.state.board, self.p2.state.current_piece, self.p2.state.get_ghost_y(),
                             self.p2.board_x, self.p2.board_y)
                r.draw_sidebar(self.p2.state.held_piece, self.p2.state.next_pieces, self.p2.state.score,
                               self.p2.state.level, self.p2.state.lines_cleared, self.p2.state.combo,
                               self.p2.board_x, self.p2.board_y)
                r.draw_flash(self.p2.flash_timer, self.p2.board_x, self.p2.board_y)

                for effect in self.p2.line_effects:
                    effect.draw(self.screen)
                for particle in self.p2.particles:
                    particle.draw(self.screen)

                if self.p2.state.game_over:
                    r.draw_player_game_over(self.p2.board_x, self.p2.board_y)

            # Global display guidelines
            if self.network_mode:
                r.draw_network_controls_hint(self.network_status)
            else:
                r.draw_controls_hint()

            # Global overlays
            if self.network_mode and self.network_waiting_reconnect:
                r.draw_reconnect_overlay(
                    self.network_reconnect_remaining,
                    self.disconnect_escape_hold,
                )
            elif self.is_game_over:
                score_p2 = 0 if self.single_player_mode else self.p2.state.score
                p2_over = True if self.single_player_mode else self.p2.state.game_over
                r.draw_game_over(self.p1.state.score, score_p2, self.p1.state.game_over, p2_over,
                                 self.single_player_mode)
            elif self.paused:
                r.draw_pause(
                    self.disconnect_escape_hold if self.network_mode else None
                )
            elif self.pause_pending:
                r.draw_pause_pending()

        pygame.display.flip()

    def handle_events(self):
        """Process start menu selectors and active gameplay keystrokes."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            if event.type == pygame.TEXTINPUT and self.state == STATE_DUO_SETUP:
                self.handle_duo_text_input(event.text)
                continue

            if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                    and self.state == STATE_DUO_SETUP):
                if self.duo_ui["ip"].collidepoint(event.pos):
                    self.duo_active_input = "ip"
                elif self.duo_ui["port"].collidepoint(event.pos):
                    self.duo_active_input = "port"
                elif self.duo_ui["join"].collidepoint(event.pos):
                    self.join_server_placeholder()
                elif self.duo_ui["create"].collidepoint(event.pos):
                    self.prepare_server_placeholder()
                else:
                    self.duo_active_input = None
                continue

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
                            self.open_duo_setup()
                        elif self.menu_selection == 2:  # Exit
                            return False
                    continue

                if self.state == STATE_DUO_SETUP:
                    if event.key == pygame.K_ESCAPE:
                        self.close_duo_setup()
                    elif event.key == pygame.K_TAB:
                        self.duo_active_input = (
                            "port" if self.duo_active_input == "ip" else "ip"
                        )
                    elif event.key == pygame.K_BACKSPACE:
                        if self.duo_active_input == "ip":
                            self.duo_ip = self.duo_ip[:-1]
                        elif self.duo_active_input == "port":
                            self.duo_port = self.duo_port[:-1]
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        self.join_server_placeholder()
                    continue

                # ─── PLAYING STATE INPUTS ───────────────────────────────────
                if self.state == STATE_PLAYING:
                    if self.network_mode and self.network_waiting_reconnect:
                        continue
                    # Escape or M behavior
                    if self.is_game_over:
                        if event.key == pygame.K_r and not self.network_mode:
                            self.restart_match()
                        elif event.key in (pygame.K_m, pygame.K_ESCAPE):
                            self.reset_game_to_menu()
                        elif event.key == pygame.K_q:
                            return False
                        continue

                    if self.network_mode and event.key == pygame.K_p:
                        self.request_network_pause()
                        continue

                    if self.network_mode and event.key == pygame.K_ESCAPE:
                        if not self.paused:
                            if self.network_escape_context is None:
                                self.network_escape_context = "pause_request"
                                self.request_network_pause()
                        elif self.network_escape_context is None:
                            self.network_escape_context = "paused"
                            self.disconnect_escape_hold = 0.0
                        continue

                    # Pause/Resume toggle for local games
                    if not self.network_mode and event.key in (pygame.K_ESCAPE, pygame.K_p):
                        self.paused = not self.paused
                        continue

                    # If paused, check if Escape is pressed again to exit to menu
                    if self.paused:
                        if event.key == pygame.K_m:
                            self.reset_game_to_menu()
                        continue

                    # Local Reset hotkey
                    if event.key == pygame.K_r and not self.network_mode:
                        self.restart_match()
                        continue

                    # Route Inputs to Player 1 (Active in both modes)
                    p1_ctrl = self.p1.controls
                    if not self.p1.state.game_over:
                        if event.key == p1_ctrl['left']:
                            self.p1.state.move(-1)
                            self.p1.state.das_direction = -1
                            self.p1.state.das_timer = 0
                            self.p1.state.das_charged = False
                        elif event.key == p1_ctrl['right']:
                            self.p1.state.move(1)
                            self.p1.state.das_direction = 1
                            self.p1.state.das_timer = 0
                            self.p1.state.das_charged = False
                        elif event.key == p1_ctrl['rotate_cw']:
                            self.p1.state.rotate(1)
                        elif event.key == p1_ctrl['rotate_ccw']:
                            self.p1.state.rotate(-1)
                        elif event.key == p1_ctrl['soft_drop']:
                            self.p1.state.soft_drop = True
                        elif event.key == p1_ctrl['hard_drop']:
                            self.p1.state.hard_drop(self.shared_sequence)
                        elif event.key == p1_ctrl['hold']:
                            self.p1.state.hold_piece(self.shared_sequence)
                        self.p1.process_events()

                    # Route Inputs to Player 2 (Only in Duo mode)
                    if not self.single_player_mode and not self.network_mode:
                        p2_ctrl = self.p2.controls
                        if not self.p2.state.game_over:
                            if event.key == p2_ctrl['left']:
                                self.p2.state.move(-1)
                                self.p2.state.das_direction = -1
                                self.p2.state.das_timer = 0
                                self.p2.state.das_charged = False
                            elif event.key == p2_ctrl['right']:
                                self.p2.state.move(1)
                                self.p2.state.das_direction = 1
                                self.p2.state.das_timer = 0
                                self.p2.state.das_charged = False
                            elif event.key == p2_ctrl['rotate_cw']:
                                self.p2.state.rotate(1)
                            elif event.key == p2_ctrl['rotate_ccw']:
                                self.p2.state.rotate(-1)
                            elif event.key == p2_ctrl['soft_drop']:
                                self.p2.state.soft_drop = True
                            elif event.key == p2_ctrl['hard_drop']:
                                self.p2.state.hard_drop(self.shared_sequence)
                            elif event.key == p2_ctrl['hold']:
                                self.p2.state.hold_piece(self.shared_sequence)
                            self.p2.process_events()

            if (event.type == pygame.KEYUP and self.state == STATE_PLAYING
                    and not self.paused and not self.network_waiting_reconnect):
                # P1 Key Release
                p1_ctrl = self.p1.controls
                if event.key == p1_ctrl['left']:
                    if self.p1.state.das_direction == -1:
                        self.p1.state.das_direction = 0
                elif event.key == p1_ctrl['right']:
                    if self.p1.state.das_direction == 1:
                        self.p1.state.das_direction = 0
                elif event.key == p1_ctrl['soft_drop']:
                    self.p1.state.soft_drop = False
                self.p1.process_events()

                # P2 Key Release (Only in Duo Mode)
                if not self.single_player_mode and not self.network_mode:
                    p2_ctrl = self.p2.controls
                    if event.key == p2_ctrl['left'] and self.p2.state.das_direction == -1:
                        self.p2.state.das_direction = 0
                    elif event.key == p2_ctrl['right'] and self.p2.state.das_direction == 1:
                        self.p2.state.das_direction = 0
                    elif event.key == p2_ctrl['soft_drop']:
                        self.p2.state.soft_drop = False
                    self.p2.process_events()

            if (event.type == pygame.KEYUP and event.key == pygame.K_ESCAPE
                    and self.state == STATE_PLAYING and self.network_mode):
                escape_context = self.network_escape_context
                self.network_escape_context = None
                if (escape_context == "paused" and self.paused
                        and not self.network_waiting_reconnect
                        and self.disconnect_escape_hold < 2.0):
                    self.request_network_pause()
                self.disconnect_escape_hold = 0.0

        return True

    def run(self):
        """Main game loop."""
        try:
            running = True
            while running:
                dt = self.clock.tick(FPS) / 1000.0
                running = self.handle_events()
                self.update(dt)
                self.draw()
        finally:
            self.shutdown_network()
            pygame.quit()
