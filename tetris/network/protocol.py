"""Binary protocol shared by the Tetris WebSocket server and clients."""

from dataclasses import dataclass
import struct


MAGIC = b"\xAA\x55"
PROTOCOL_VERSION = 2
MAX_PAYLOAD_SIZE = 4096
SESSION_TOKEN_SIZE = 16

HEADER_STRUCT = struct.Struct("!2sBBBHIII")
HEADER_SIZE = HEADER_STRUCT.size

MSG_HELLO = 0x01
MSG_WELCOME = 0x02
MSG_READY = 0x03
MSG_MATCH_START = 0x04
MSG_PEER_STATUS = 0x05
MSG_INPUT = 0x10
MSG_CONTROL_REQUEST = 0x11
MSG_CONTROL_COMMIT = 0x12
MSG_FORFEIT = 0x13
MSG_STATE_UPDATE = 0x20
MSG_FULL_SNAPSHOT = 0x21
MSG_MATCH_RESULT = 0x22
MSG_ERROR = 0x30

CONTROL_PAUSE = 1
CONTROL_RESUME = 2

PEER_DISCONNECTED = 0
PEER_CONNECTED = 1
PEER_RECONNECTING = 2
PEER_RECONNECTED = 3

ERROR_SERVER_FULL = 1
ERROR_PROTOCOL = 2
ERROR_INVALID_STATE = 3
ERROR_RECONNECT = 4

WELCOME_STRUCT = struct.Struct(f"!BB{SESSION_TOKEN_SIZE}sB")

PIECE_TYPES = ("I", "O", "T", "S", "Z", "J", "L")
PIECE_TO_CODE = {piece_type: index + 1
                 for index, piece_type in enumerate(PIECE_TYPES)}
CODE_TO_PIECE = {code: piece_type for piece_type, code in PIECE_TO_CODE.items()}

SNAPSHOT_META_STRUCT = struct.Struct("!BBbbB3BBBIHHhBIBHHHbBB")
BOARD_BYTES = 100
SNAPSHOT_SIZE = SNAPSHOT_META_STRUCT.size + BOARD_BYTES


class ProtocolError(ValueError):
    """Raised when an application packet doesn't match the protocol."""


@dataclass(frozen=True)
class Packet:
    message_type: int
    flags: int
    seq: int
    ack: int
    tick: int
    payload: bytes


def pack_packet(message_type, payload=b"", *, seq=0, ack=0, tick=0, flags=0):
    """Pack one application packet for one WebSocket binary message."""
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    if len(payload) > MAX_PAYLOAD_SIZE:
        raise ProtocolError("payload exceeds protocol limit")
    header = HEADER_STRUCT.pack(
        MAGIC,
        PROTOCOL_VERSION,
        message_type,
        flags,
        len(payload),
        seq & 0xFFFFFFFF,
        ack & 0xFFFFFFFF,
        tick & 0xFFFFFFFF,
    )
    return header + payload


def unpack_packet(data):
    """Validate and unpack one application packet."""
    if not isinstance(data, bytes):
        raise ProtocolError("WebSocket message must be binary")
    if len(data) < HEADER_SIZE:
        raise ProtocolError("packet is shorter than the fixed header")

    magic, version, message_type, flags, size, seq, ack, tick = (
        HEADER_STRUCT.unpack_from(data)
    )
    if magic != MAGIC:
        raise ProtocolError("invalid packet magic")
    if version != PROTOCOL_VERSION:
        raise ProtocolError(f"unsupported protocol version: {version}")
    if size > MAX_PAYLOAD_SIZE:
        raise ProtocolError("declared payload exceeds protocol limit")
    if len(data) != HEADER_SIZE + size:
        raise ProtocolError("packet length doesn't match payload size")

    return Packet(message_type, flags, seq, ack, tick, data[HEADER_SIZE:])


def pack_hello(session_token=None):
    """Encode an initial HELLO or a reconnect HELLO with a session token."""
    if session_token is None:
        return b""
    if not isinstance(session_token, bytes) or len(session_token) != SESSION_TOKEN_SIZE:
        raise ProtocolError("session token has an invalid size")
    return session_token


def unpack_hello(payload):
    """Return the optional session token carried by HELLO."""
    if payload == b"":
        return None
    if len(payload) != SESSION_TOKEN_SIZE:
        raise ProtocolError("invalid HELLO payload")
    return payload


def pack_welcome(slot, connected_count, session_token, reconnected=False):
    """Encode the assigned slot, lobby count, session token, and reconnect flag."""
    if slot not in (0, 1):
        raise ProtocolError("invalid player slot")
    if connected_count not in (1, 2):
        raise ProtocolError("invalid connected player count")
    if not isinstance(session_token, bytes) or len(session_token) != SESSION_TOKEN_SIZE:
        raise ProtocolError("session token has an invalid size")
    return WELCOME_STRUCT.pack(slot, connected_count, session_token, int(reconnected))


def unpack_welcome(payload):
    """Decode and validate a WELCOME payload."""
    if len(payload) != WELCOME_STRUCT.size:
        raise ProtocolError("invalid WELCOME payload")
    slot, connected_count, session_token, reconnected = WELCOME_STRUCT.unpack(payload)
    if slot not in (0, 1):
        raise ProtocolError("invalid player slot")
    if connected_count not in (1, 2):
        raise ProtocolError("invalid connected player count")
    if reconnected not in (0, 1):
        raise ProtocolError("invalid reconnect flag")
    return slot, connected_count, session_token, bool(reconnected)


def pack_board(grid):
    """Pack a 10 x 20 board into 100 bytes using four bits per cell."""
    flat = []
    if len(grid) != 20 or any(len(row) != 10 for row in grid):
        raise ProtocolError("board must be a 10 x 20 grid")
    for row in grid:
        for cell in row:
            if cell is None:
                flat.append(0)
            else:
                try:
                    flat.append(PIECE_TO_CODE[cell])
                except KeyError as exc:
                    raise ProtocolError(f"invalid board cell: {cell}") from exc

    return bytes((flat[index] << 4) | flat[index + 1]
                 for index in range(0, len(flat), 2))


def unpack_board(data):
    """Unpack a 100-byte board into a 10 x 20 grid."""
    if len(data) != BOARD_BYTES:
        raise ProtocolError("packed board must contain 100 bytes")
    cells = []
    for value in data:
        for code in (value >> 4, value & 0x0F):
            if code > len(PIECE_TYPES):
                raise ProtocolError("packed board contains an invalid piece code")
            cells.append(CODE_TO_PIECE.get(code))
    return [cells[index:index + 10] for index in range(0, 200, 10)]


def encode_player_snapshot(player, slot):
    """Serialize the gameplay state needed to draw and judge one player."""
    current = player.current_piece
    if current is None:
        raise ProtocolError("player has no active piece")

    next_codes = [PIECE_TO_CODE[piece.type] for piece in player.next_pieces[:3]]
    if len(next_codes) != 3:
        raise ProtocolError("player must have exactly three preview pieces")

    held_code = 0 if player.held_piece is None else PIECE_TO_CODE[player.held_piece.type]
    metadata = SNAPSHOT_META_STRUCT.pack(
        slot,
        PIECE_TO_CODE[current.type],
        current.x,
        current.y,
        current.rotation,
        *next_codes,
        held_code,
        int(player.can_hold),
        max(0, player.score),
        max(0, player.lines_cleared),
        max(1, player.level),
        player.combo,
        int(player.back_to_back),
        max(0, player.piece_index),
        int(player.game_over),
        max(0, player.fall_timer),
        max(0, player.lock_timer),
        max(0, player.das_timer),
        player.das_direction,
        int(player.das_charged),
        int(player.soft_drop),
    )
    return metadata + pack_board(player.board.grid)


def decode_player_snapshot(payload):
    """Validate and deserialize one player snapshot into primitive values."""
    if len(payload) != SNAPSHOT_SIZE:
        raise ProtocolError(f"snapshot must contain {SNAPSHOT_SIZE} bytes")

    values = SNAPSHOT_META_STRUCT.unpack_from(payload)
    (slot, current_code, x, y, rotation, next_0, next_1, next_2,
     held_code, can_hold, score, lines, level, combo, back_to_back,
     piece_index, game_over, fall_timer, lock_timer, das_timer,
     das_direction, das_charged, soft_drop) = values

    if slot not in (0, 1):
        raise ProtocolError("invalid player slot")
    if current_code not in CODE_TO_PIECE:
        raise ProtocolError("invalid active piece")
    if rotation > 3:
        raise ProtocolError("invalid piece rotation")
    if not -4 <= x <= 10 or not -4 <= y <= 24:
        raise ProtocolError("active piece position is outside protocol bounds")
    if any(code not in CODE_TO_PIECE for code in (next_0, next_1, next_2)):
        raise ProtocolError("invalid next-piece queue")
    if held_code not in (0, *CODE_TO_PIECE.keys()):
        raise ProtocolError("invalid held piece")
    if level < 1:
        raise ProtocolError("invalid player level")
    if das_direction not in (-1, 0, 1):
        raise ProtocolError("invalid DAS direction")
    if (can_hold not in (0, 1) or back_to_back not in (0, 1)
            or game_over not in (0, 1) or das_charged not in (0, 1)
            or soft_drop not in (0, 1)):
        raise ProtocolError("invalid boolean field in snapshot")

    return {
        "slot": slot,
        "current_piece": CODE_TO_PIECE[current_code],
        "x": x,
        "y": y,
        "rotation": rotation,
        "next_pieces": [CODE_TO_PIECE[next_0], CODE_TO_PIECE[next_1],
                        CODE_TO_PIECE[next_2]],
        "held_piece": CODE_TO_PIECE.get(held_code),
        "can_hold": bool(can_hold),
        "score": score,
        "lines_cleared": lines,
        "level": level,
        "combo": combo,
        "back_to_back": bool(back_to_back),
        "piece_index": piece_index,
        "game_over": bool(game_over),
        "fall_timer": fall_timer,
        "lock_timer": lock_timer,
        "das_timer": das_timer,
        "das_direction": das_direction,
        "das_charged": bool(das_charged),
        "soft_drop": bool(soft_drop),
        "board": unpack_board(payload[SNAPSHOT_META_STRUCT.size:]),
    }


def pack_error(code, message):
    encoded = message.encode("utf-8")[:240]
    return bytes((code, len(encoded))) + encoded


def unpack_error(payload):
    if len(payload) < 2 or len(payload) != 2 + payload[1]:
        raise ProtocolError("invalid error payload")
    return payload[0], payload[2:].decode("utf-8", errors="replace")
