import socket

from timetracker.cli import _find_free_port


def test_find_free_port_returns_open_port():
    port = _find_free_port("127.0.0.1", 8765)
    # we can actually bind what it returned
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", port))


def test_find_free_port_skips_busy_port():
    # Occupy a port, then ask starting from it; must get a different one.
    # No SO_REUSEADDR so the port is genuinely unavailable on every OS.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen(1)
        taken = busy.getsockname()[1]
        chosen = _find_free_port("127.0.0.1", taken)
        assert chosen != taken
