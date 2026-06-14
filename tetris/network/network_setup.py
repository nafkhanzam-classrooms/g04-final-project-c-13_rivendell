"""Network endpoint helpers shared by the Duo setup screen and future server."""

import socket


SERVER_PORT_CANDIDATES = (6578, 6690, 6635)


def get_local_ip():
    """Return the most useful local IPv4 address available on this machine."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        probe.close()


def is_port_available(port):
    """Check whether a TCP port can currently be bound on all interfaces."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        probe.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def find_available_server_port():
    """Select the first free port from the project's fixed fallback order."""
    for port in SERVER_PORT_CANDIDATES:
        if is_port_available(port):
            return port
    return None
