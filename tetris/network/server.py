"""Two-player WebSocket server for Tetris Duo."""

import argparse
from dataclasses import dataclass, field
import secrets
import struct
import threading
import time

from websockets.exceptions import ConnectionClosed
from websockets.sync.server import serve

from network.protocol import (
    CONTROL_PAUSE,
    CONTROL_RESUME,
    ERROR_INVALID_STATE,
    ERROR_PROTOCOL,
    ERROR_RECONNECT,
    ERROR_SERVER_FULL,
    HEADER_SIZE,
    MAX_PAYLOAD_SIZE,
    MSG_CONTROL_COMMIT,
    MSG_CONTROL_REQUEST,
    MSG_ERROR,
    MSG_FORFEIT,
    MSG_FULL_SNAPSHOT,
    MSG_HELLO,
    MSG_MATCH_RESULT,
    MSG_MATCH_START,
    MSG_PEER_STATUS,
    MSG_STATE_UPDATE,
    MSG_WELCOME,
    PEER_CONNECTED,
    PEER_DISCONNECTED,
    PEER_RECONNECTED,
    PEER_RECONNECTING,
    ProtocolError,
    decode_player_snapshot,
    pack_error,
    pack_packet,
    pack_welcome,
    unpack_hello,
    unpack_packet,
)


TICK_RATE = 60
RECONNECT_GRACE_SECONDS = 15.0


@dataclass
class ClientSession:
    slot: int
    token: bytes
    connection: object
    send_seq: int = 0
    recv_seq: int = 0
    disconnected_at: float | None = None
    generation: int = 0
    forfeited: bool = False
    send_lock: threading.Lock = field(default_factory=threading.Lock)

    def send(self, message_type, payload=b"", *, tick=0, flags=0):
        with self.send_lock:
            if self.connection is None:
                return False
            self.send_seq = (self.send_seq + 1) & 0xFFFFFFFF
            data = pack_packet(
                message_type,
                payload,
                seq=self.send_seq,
                ack=self.recv_seq,
                tick=tick,
                flags=flags,
            )
            self.connection.send(data)
            return True


class TetrisServer:
    """Owns lobby state, pause decisions, and the latest state of both players."""

    def __init__(self):
        self.lock = threading.RLock()
        self.sessions = {}
        self.sessions_by_token = {}
        self.snapshots = {}
        self.snapshot_payloads = {}
        self.started_at = time.monotonic()
        self.match_seed = None
        self.paused = False
        self.match_finished = False
        self.match_result_payload = None

    def tick(self):
        return int((time.monotonic() - self.started_at) * TICK_RATE) & 0xFFFFFFFF

    def _allocate_slot(self, connection, requested_token=None):
        with self.lock:
            if requested_token is not None and requested_token in self.sessions_by_token:
                return None
            for slot in (0, 1):
                if slot not in self.sessions:
                    token = requested_token
                    if token is None:
                        token = secrets.token_bytes(16)
                        while token in self.sessions_by_token:
                            token = secrets.token_bytes(16)
                    session = ClientSession(slot, token, connection)
                    self.sessions[slot] = session
                    self.sessions_by_token[token] = session
                    return session
        return None

    def _resume_session(self, token, connection):
        previous_connection = None
        with self.lock:
            session = self.sessions_by_token.get(token)
            if session is None:
                return None
            if (session.disconnected_at is not None
                    and time.monotonic() - session.disconnected_at
                    > RECONNECT_GRACE_SECONDS):
                return None

            # A reconnect can arrive before the old handler observes its dead
            # socket. The authenticated token is allowed to atomically replace
            # that stale transport; the old handler will then ignore cleanup.
            previous_connection = session.connection
            session.connection = connection
            session.disconnected_at = None
            session.generation += 1

        if previous_connection is not None and previous_connection is not connection:
            try:
                previous_connection.close(
                    code=1012,
                    reason="session transport replaced",
                )
            except Exception:
                pass
        return session

    def _claim_disconnected_session(self, new_token, connection):
        """Let a restarted client reclaim the only disconnected match slot."""
        with self.lock:
            if new_token in self.sessions_by_token:
                return None

            now = time.monotonic()
            candidates = [
                session for session in self.sessions.values()
                if (session.connection is None
                    and session.disconnected_at is not None
                    and now - session.disconnected_at <= RECONNECT_GRACE_SECONDS
                    and not session.forfeited)
            ]
            if len(candidates) != 1:
                return None

            session = candidates[0]
            old_token = session.token
            self.sessions_by_token.pop(old_token, None)
            session.token = new_token
            session.connection = connection
            session.disconnected_at = None
            session.generation += 1
            self.sessions_by_token[new_token] = session
            return session

    def _connected_count(self):
        with self.lock:
            return sum(session.connection is not None
                       for session in self.sessions.values())

    def _session_list(self):
        with self.lock:
            return list(self.sessions.values())

    def broadcast(self, message_type, payload=b"", *, tick=None, exclude=None):
        if tick is None:
            tick = self.tick()
        for session in self._session_list():
            if session.slot == exclude:
                continue
            try:
                session.send(message_type, payload, tick=tick)
            except ConnectionClosed:
                pass

    def send_error(self, session, code, message):
        try:
            session.send(MSG_ERROR, pack_error(code, message), tick=self.tick())
        except ConnectionClosed:
            pass

    def maybe_start_match(self):
        with self.lock:
            if (len(self.sessions) != 2
                    or any(session.connection is None for session in self.sessions.values())
                    or self.match_seed is not None):
                return
            self.match_seed = secrets.randbits(32)
            self.snapshots.clear()
            self.snapshot_payloads.clear()
            self.paused = False
            self.match_finished = False
            self.match_result_payload = None
            seed = self.match_seed
        self.broadcast(MSG_MATCH_START, struct.pack("!I", seed))
        print(f"[server] match started with seed {seed}", flush=True)

    def handle_state_update(self, session, payload):
        snapshot = decode_player_snapshot(payload)
        if snapshot["slot"] != session.slot:
            raise ProtocolError("snapshot slot doesn't match connection slot")

        with self.lock:
            previous = self.snapshots.get(session.slot)
            if previous is not None:
                if snapshot["score"] < previous["score"]:
                    raise ProtocolError("score cannot decrease during a match")
                if snapshot["lines_cleared"] < previous["lines_cleared"]:
                    raise ProtocolError("line count cannot decrease during a match")
                if snapshot["piece_index"] < previous["piece_index"]:
                    raise ProtocolError("piece index cannot decrease during a match")
            self.snapshots[session.slot] = snapshot
            self.snapshot_payloads[session.slot] = payload
            finish_now = snapshot["game_over"] and not self.match_finished
            if finish_now:
                self.match_finished = True

        self.broadcast(MSG_STATE_UPDATE, payload, exclude=session.slot)
        if finish_now:
            winner = 1 - session.slot
            result = bytes((winner, 0))
            with self.lock:
                self.match_result_payload = result
            self.broadcast(MSG_MATCH_RESULT, result)
            print(f"[server] player {session.slot} topped out; player {winner} wins", flush=True)

    def handle_control_request(self, session, payload):
        if len(payload) != 1 or payload[0] not in (CONTROL_PAUSE, CONTROL_RESUME):
            raise ProtocolError("invalid control request")
        requested_pause = payload[0] == CONTROL_PAUSE
        with self.lock:
            if self.match_seed is None or self.match_finished:
                return
            self.paused = requested_pause
        self.broadcast(MSG_CONTROL_COMMIT, bytes((int(requested_pause),)))
        action = "paused" if requested_pause else "resumed"
        print(f"[server] match {action} by player {session.slot}", flush=True)

    def handle_forfeit(self, session, payload):
        if payload:
            raise ProtocolError("FORFEIT payload must be empty")
        with self.lock:
            if self.match_seed is None or self.match_finished:
                raise ProtocolError("cannot forfeit an inactive match")
            winner = 1 - session.slot
            result = bytes((winner, 2))
            session.forfeited = True
            self.match_finished = True
            self.match_result_payload = result
            self.paused = False
        self.broadcast(MSG_MATCH_RESULT, result)
        print(
            f"[server] player {session.slot} forfeited; player {winner} wins",
            flush=True,
        )

    def handle_packet(self, session, packet):
        if packet.seq <= session.recv_seq and session.recv_seq - packet.seq < 0x80000000:
            return
        session.recv_seq = packet.seq
        if packet.message_type == MSG_HELLO:
            return
        if packet.message_type == MSG_STATE_UPDATE:
            self.handle_state_update(session, packet.payload)
            return
        if packet.message_type == MSG_CONTROL_REQUEST:
            self.handle_control_request(session, packet.payload)
            return
        if packet.message_type == MSG_FORFEIT:
            self.handle_forfeit(session, packet.payload)
            return
        raise ProtocolError(f"unsupported client message type: {packet.message_type:#x}")

    def broadcast_recovery_state(self, reconnected_slot):
        """Restore both clients from the last server-observed state before resuming."""
        with self.lock:
            payloads = [self.snapshot_payloads[slot]
                        for slot in sorted(self.snapshot_payloads)]
            paused = self.paused
            result = self.match_result_payload
            seed = self.match_seed
        if seed is not None:
            with self.lock:
                reconnected_session = self.sessions.get(reconnected_slot)
            if reconnected_session is not None:
                reconnected_session.send(
                    MSG_MATCH_START,
                    struct.pack("!I", seed),
                    tick=self.tick(),
                )
        for payload in payloads:
            self.broadcast(MSG_FULL_SNAPSHOT, payload)
        self.broadcast(MSG_CONTROL_COMMIT, bytes((int(paused),)))
        if result is not None:
            self.broadcast(MSG_MATCH_RESULT, result)
        self.broadcast(
            MSG_PEER_STATUS,
            bytes((reconnected_slot, PEER_RECONNECTED)),
        )

    def reject_connection(self, connection, code, message):
        try:
            connection.send(pack_packet(
                MSG_ERROR,
                pack_error(code, message),
                seq=1,
                tick=self.tick(),
            ))
        finally:
            connection.close(code=1008, reason=message[:120])

    def handler(self, connection):
        session = None
        try:
            first_message = connection.recv(timeout=5)
            hello = unpack_packet(first_message)
            if hello.message_type != MSG_HELLO:
                raise ProtocolError("first packet must be HELLO")
            reconnect_token = unpack_hello(hello.payload)

            if reconnect_token is None:
                session = self._allocate_slot(connection)
                if session is None:
                    self.reject_connection(
                        connection,
                        ERROR_SERVER_FULL,
                        "Server already has two player sessions.",
                    )
                    return
                reconnected = False
            else:
                session = self._resume_session(reconnect_token, connection)
                if session is None:
                    session = self._claim_disconnected_session(
                        reconnect_token,
                        connection,
                    )
                if session is None:
                    # A client-generated token is also used for first contact.
                    # If it isn't registered yet, create a fresh session when a
                    # slot is available. Registered tokens are resumed above.
                    session = self._allocate_slot(connection, reconnect_token)
                    if session is None:
                        self.reject_connection(
                            connection,
                            ERROR_SERVER_FULL,
                            "Server already has two player sessions.",
                        )
                        return
                    reconnected = False
                else:
                    reconnected = True

            session.recv_seq = hello.seq
            connected_count = self._connected_count()
            session.send(
                MSG_WELCOME,
                pack_welcome(
                    session.slot,
                    connected_count,
                    session.token,
                    reconnected,
                ),
                tick=self.tick(),
            )

            if reconnected:
                print(f"[server] player {session.slot} reconnected", flush=True)
                self.broadcast_recovery_state(session.slot)
            else:
                print(f"[server] player {session.slot} connected", flush=True)
                self.broadcast(
                    MSG_PEER_STATUS,
                    bytes((session.slot, PEER_CONNECTED)),
                    exclude=session.slot,
                )
                self.maybe_start_match()

            for message in connection:
                try:
                    packet = unpack_packet(message)
                    self.handle_packet(session, packet)
                except ProtocolError as exc:
                    self.send_error(session, ERROR_PROTOCOL, str(exc))
        except TimeoutError:
            if session is None:
                self.reject_connection(connection, ERROR_PROTOCOL, "HELLO timed out.")
        except ProtocolError as exc:
            if session is None:
                self.reject_connection(connection, ERROR_PROTOCOL, str(exc))
            else:
                self.send_error(session, ERROR_PROTOCOL, str(exc))
        except ConnectionClosed:
            pass
        finally:
            if session is not None:
                self.disconnect(session, connection)

    def disconnect(self, session, connection):
        with self.lock:
            if (self.sessions.get(session.slot) is not session
                    or session.connection is not connection):
                return
            session.connection = None
            if session.forfeited:
                del self.sessions[session.slot]
                self.sessions_by_token.pop(session.token, None)
                self.snapshots.pop(session.slot, None)
                self.snapshot_payloads.pop(session.slot, None)
                forfeited = True
            else:
                forfeited = False
            if forfeited:
                session.disconnected_at = None
            else:
                session.disconnected_at = time.monotonic()
                session.generation += 1
                generation = session.generation

        if forfeited:
            print(f"[server] forfeiting player {session.slot} disconnected", flush=True)
            self.broadcast(
                MSG_PEER_STATUS,
                bytes((session.slot, PEER_DISCONNECTED)),
            )
            return

        print(
            f"[server] player {session.slot} disconnected; "
            f"waiting {RECONNECT_GRACE_SECONDS:.0f}s for reconnection",
            flush=True,
        )
        self.broadcast(
            MSG_PEER_STATUS,
            bytes((session.slot, PEER_RECONNECTING)),
        )
        timer = threading.Timer(
            RECONNECT_GRACE_SECONDS,
            self.expire_disconnected_session,
            args=(session.slot, session.token, generation),
        )
        timer.daemon = True
        timer.start()

    def expire_disconnected_session(self, slot, token, generation):
        with self.lock:
            session = self.sessions.get(slot)
            if (session is None or session.token != token
                    or session.generation != generation
                    or session.connection is not None):
                return

            del self.sessions[slot]
            self.sessions_by_token.pop(token, None)
            self.snapshots.pop(slot, None)
            self.snapshot_payloads.pop(slot, None)
            remaining = [candidate for candidate in self.sessions.values()
                         if candidate.connection is not None]
            match_was_running = self.match_seed is not None and not self.match_finished
            self.match_finished = match_was_running or self.match_finished
            self.match_seed = None
            self.paused = False

        print(f"[server] player {slot} reconnect grace period expired", flush=True)
        self.broadcast(MSG_PEER_STATUS, bytes((slot, PEER_DISCONNECTED)))
        if match_was_running and remaining:
            self.broadcast(MSG_MATCH_RESULT, bytes((remaining[0].slot, 1)))


def parse_args():
    parser = argparse.ArgumentParser(description="Tetris Duo WebSocket server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=6578)
    return parser.parse_args()


def main():
    args = parse_args()
    game_server = TetrisServer()
    print(f"[server] listening on ws://{args.host}:{args.port}", flush=True)
    with serve(
        game_server.handler,
        args.host,
        args.port,
        compression=None,
        ping_interval=5,
        ping_timeout=10,
        max_size=HEADER_SIZE + MAX_PAYLOAD_SIZE,
    ) as websocket_server:
        websocket_server.serve_forever()


if __name__ == "__main__":
    main()
