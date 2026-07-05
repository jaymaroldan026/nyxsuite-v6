"""Single-instance runner lock shared by the Nyx/Nyxify runners and the bridge.

Extracted verbatim from the previously-duplicated ``_RunnerLock`` in ``main.py``
and ``nyxify_runner.py`` so the runner processes and the new bridge supervisor
all share one implementation. Behaviour is unchanged: bind an exclusive TCP
socket on ``(host, port)``; if the bind fails, another runner already holds it.
"""

import socket


class RunnerLock:
    def __init__(self, host: str, port: int):
        self.host = str(host or "127.0.0.1").strip() or "127.0.0.1"
        self.port = int(port)
        self._socket = None

    def acquire(self) -> bool:
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            self._socket.bind((self.host, self.port))
            self._socket.listen(1)
            return True
        except OSError:
            self.release()
            return False

    def release(self) -> None:
        sock = self._socket
        self._socket = None
        if sock is None:
            return
        try:
            sock.close()
        except Exception:
            pass
