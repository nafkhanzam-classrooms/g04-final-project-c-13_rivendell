"""Threaded WebSocket client transport for the Pygame main loop."""

from queue import Empty, Queue
import secrets
import threading
import time

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from network.protocol import (
    HEADER_SIZE,
    MAX_PAYLOAD_SIZE,
    MSG_HELLO,
    MSG_WELCOME,
    ProtocolError,
    pack_hello,
    pack_packet,
    unpack_packet,
    unpack_welcome,
)


class NetworkClient:
    """Moves WebSocket I/O off the Pygame thread and exposes queue-based events."""

    def __init__(self, host, port, connect_timeout=5.0, reconnect_timeout=15.0):
        self.host = host
        self.port = port
        self.connect_timeout = connect_timeout
        self.reconnect_timeout = reconnect_timeout
        self.incoming = Queue()
        self.outgoing = Queue(maxsize=256)
        self.stop_event = threading.Event()
        self.send_lock = threading.Lock()
        self.thread = None
        self.connection = None
        self.send_seq = 0
        self.recv_seq = 0
        # Client-owned identity is available before the first WELCOME. This
        # prevents a transport drop during handshake from turning a reconnect
        # into an anonymous third-player connection.
        self.session_token = secrets.token_bytes(16)
        self.handshake_complete = False

    @property
    def uri(self):
        host = f"[{self.host}]" if ":" in self.host and not self.host.startswith("[") else self.host
        return f"ws://{host}:{self.port}"

    def start(self):
        if self.thread is not None:
            return
        self.thread = threading.Thread(target=self._run, name="tetris-websocket", daemon=True)
        self.thread.start()

    def send(self, message_type, payload=b"", flags=0):
        try:
            self.outgoing.put_nowait((message_type, payload, flags))
            return True
        except Exception:
            return False

    def send_immediate(self, message_type, payload=b"", flags=0):
        """Send a final control packet before the caller closes the connection."""
        connection = self.connection
        if connection is None:
            return False
        try:
            self._send_packet(connection, message_type, payload, flags)
            return True
        except Exception:
            return False

    def set_session_token(self, session_token):
        """Store the server-issued token used by future reconnect attempts."""
        self.session_token = session_token

    def poll(self):
        events = []
        while True:
            try:
                events.append(self.incoming.get_nowait())
            except Empty:
                return events

    def close(self):
        self.stop_event.set()
        connection = self.connection
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
        if self.thread is not None:
            self.thread.join(timeout=1.0)
        self.thread = None
        self.connection = None

    def _send_packet(self, connection, message_type, payload=b"", flags=0):
        with self.send_lock:
            self.send_seq = (self.send_seq + 1) & 0xFFFFFFFF
            connection.send(pack_packet(
                message_type,
                payload,
                seq=self.send_seq,
                ack=self.recv_seq,
                flags=flags,
            ))

    def _connect_before(self, deadline):
        last_error = None
        while not self.stop_event.is_set() and time.monotonic() < deadline:
            try:
                return connect(
                    self.uri,
                    compression=None,
                    open_timeout=1,
                    close_timeout=1,
                    ping_interval=1,
                    ping_timeout=5,
                    max_size=HEADER_SIZE + MAX_PAYLOAD_SIZE,
                )
            except Exception as exc:
                last_error = exc
                time.sleep(0.1)
        if last_error is None:
            raise ConnectionError("connection cancelled")
        raise last_error

    def _clear_outgoing(self):
        while True:
            try:
                self.outgoing.get_nowait()
            except Empty:
                return

    def _run_connection(self, connection):
        next_latency_update = time.monotonic()
        while not self.stop_event.is_set():
            while True:
                try:
                    message_type, payload, flags = self.outgoing.get_nowait()
                except Empty:
                    break
                self._send_packet(connection, message_type, payload, flags)

            now = time.monotonic()
            if now >= next_latency_update:
                latency = connection.latency
                if latency > 0:
                    self.incoming.put(("latency", latency * 1000.0))
                next_latency_update = now + 0.5

            try:
                message = connection.recv(timeout=0.02)
            except TimeoutError:
                continue
            packet = unpack_packet(message)
            self.recv_seq = packet.seq
            if packet.message_type == MSG_WELCOME:
                _, _, session_token, _ = unpack_welcome(packet.payload)
                self.session_token = session_token
                self.handshake_complete = True
            self.incoming.put(("packet", packet))

    def _run(self):
        reconnecting = False
        reconnect_deadline = None
        try:
            while not self.stop_event.is_set():
                try:
                    if reconnecting:
                        deadline = reconnect_deadline
                    else:
                        deadline = time.monotonic() + self.connect_timeout
                    connection = self._connect_before(deadline)
                except Exception as exc:
                    if self.stop_event.is_set():
                        break
                    if reconnecting:
                        self.incoming.put(("reconnect_failed", str(exc)))
                    else:
                        self.incoming.put(("error", f"Connection failed: {exc}"))
                    break

                self.connection = connection
                self.handshake_complete = False
                # Once a session token exists, every new transport connection is
                # a reconnect attempt even if local status flags were reset.
                hello_payload = pack_hello(self.session_token)
                self._send_packet(connection, MSG_HELLO, hello_payload)
                if not reconnecting:
                    self.incoming.put(("status", f"Connected to {self.uri}"))

                try:
                    self._run_connection(connection)
                except ProtocolError as exc:
                    if not self.stop_event.is_set():
                        self.incoming.put(("error", f"Invalid server packet: {exc}"))
                    break
                except (ConnectionClosed, OSError) as exc:
                    if self.stop_event.is_set():
                        break
                    if self.session_token is None:
                        self.incoming.put(("error", f"Connection closed: {exc}"))
                        break
                finally:
                    connection_was_established = self.handshake_complete
                    if self.connection is connection:
                        self.connection = None
                    try:
                        connection.close()
                    except Exception:
                        pass
                    self.incoming.put(("latency", None))

                if self.stop_event.is_set():
                    break
                if connection_was_established:
                    reconnecting = False
                    reconnect_deadline = None
                if not reconnecting:
                    reconnecting = True
                    reconnect_deadline = time.monotonic() + self.reconnect_timeout
                    self._clear_outgoing()
                    self.incoming.put(("reconnecting", self.reconnect_timeout))
                elif time.monotonic() >= reconnect_deadline:
                    self.incoming.put(("reconnect_failed", "Reconnect grace period expired."))
                    break
        finally:
            self.connection = None
            self.incoming.put(("closed", None))
