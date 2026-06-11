"""TITAN OPS daemon.

Listens on Unix domain socket (or localhost TCP fallback) for JSON-line
instructions. One line per request, one JSON line per response.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any

_IS_WINDOWS = sys.platform == "win32"

from pradyos.titan_ops.executor import TitanExecutor  # noqa: E402
from pradyos.titan_ops.instruction import parse_instruction  # noqa: E402

log = logging.getLogger("pradyos.titan_ops")

DEFAULT_SOCKET = os.environ.get(
    "PRADYOS_TITAN_SOCKET",
    str(Path(__file__).resolve().parents[2] / "var" / "state" / "titan.sock"),
)
DEFAULT_TCP_HOST = os.environ.get("PRADYOS_TITAN_TCP_HOST", "127.0.0.1")
DEFAULT_TCP_PORT = int(os.environ.get("PRADYOS_TITAN_TCP_PORT", "9700"))

_UNIX_PATH_MAX = 104  # conservative — Linux 108, macOS 104.


def _use_unix_socket(path: str | None = None) -> bool:
    if not hasattr(socket, "AF_UNIX"):
        return False
    if os.environ.get("PRADYOS_TITAN_FORCE_TCP"):
        return False
    if path is not None and len(str(path)) > _UNIX_PATH_MAX:
        return False
    return True


class TitanDaemon:
    def __init__(
        self,
        socket_path: str = DEFAULT_SOCKET,
        tcp_host: str = DEFAULT_TCP_HOST,
        tcp_port: int = DEFAULT_TCP_PORT,
        executor: TitanExecutor | None = None,
    ) -> None:
        self.socket_path = socket_path
        self.tcp_host = tcp_host
        self.tcp_port = tcp_port
        self.executor = executor or TitanExecutor()
        self._server: socket.socket | None = None
        self._shutdown = threading.Event()
        self._threads: list[threading.Thread] = []
        self._using_unix = False

    def serve_forever(self) -> None:
        self._server = self._bind()
        log.info("TITAN OPS daemon listening (%s)", self._endpoint_name())
        try:
            while not self._shutdown.is_set():
                try:
                    conn, _addr = self._server.accept()
                except OSError:
                    if self._shutdown.is_set():
                        break
                    continue
                t = threading.Thread(target=self._handle, args=(conn,), daemon=True)
                t.start()
                self._threads.append(t)
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        self._shutdown.set()
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                pass
            self._server = None
        if self._using_unix:
            try:
                os.unlink(self.socket_path)
            except (FileNotFoundError, OSError):
                pass

    def _bind(self) -> socket.socket:
        if _use_unix_socket(self.socket_path):
            Path(self.socket_path).parent.mkdir(parents=True, exist_ok=True)
            try:
                os.unlink(self.socket_path)
            except FileNotFoundError:
                pass
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.bind(self.socket_path)
            if not _IS_WINDOWS:  # chmod semantics differ on Windows
                try:
                    os.chmod(self.socket_path, 0o660)
                except OSError:
                    pass
            s.listen(64)
            self._using_unix = True
            return s
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((self.tcp_host, self.tcp_port))
        s.listen(64)
        self._using_unix = False
        self.tcp_port = s.getsockname()[1]
        return s

    def _endpoint_name(self) -> str:
        if self._using_unix:
            return f"unix://{self.socket_path}"
        return f"tcp://{self.tcp_host}:{self.tcp_port}"

    def _handle(self, conn: socket.socket) -> None:
        """Handle a client connection using raw recv/sendall.

        Uses recv/sendall directly — the alternative (socket file wrapper in
        read-write binary mode) is not supported on Windows.  Direct socket
        I/O works identically on POSIX and Windows.
        """
        with conn:
            buf = b""
            while True:
                try:
                    chunk = conn.recv(65536)
                except OSError:
                    break
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    response = self._dispatch(line)
                    try:
                        conn.sendall(
                            (json.dumps(response, separators=(",", ":")) + "\n").encode("utf-8")
                        )
                    except OSError:
                        return

    def _dispatch(self, raw: bytes) -> dict[str, Any]:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            return {"ok": False, "error": f"json decode: {e}"}
        try:
            instr = parse_instruction(payload)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        result = self.executor.execute(instr)
        return {"ok": True, "result": result.to_dict()}


class TitanClient:
    """Synchronous TITAN client used by IMPERIUM and tests."""

    def __init__(
        self,
        socket_path: str = DEFAULT_SOCKET,
        tcp_host: str = DEFAULT_TCP_HOST,
        tcp_port: int = DEFAULT_TCP_PORT,
    ) -> None:
        self.socket_path = socket_path
        self.tcp_host = tcp_host
        self.tcp_port = tcp_port

    def wait_ready(self, timeout: float = 3.0) -> bool:
        """Block until the daemon is accepting connections (or timeout expires).

        On POSIX: waits for the Unix socket file to appear.
        On Windows / TCP fallback: polls the TCP port with retries.
        Returns True if ready, False on timeout.
        """
        deadline = time.monotonic() + timeout
        use_unix = _use_unix_socket(self.socket_path)
        while time.monotonic() < deadline:
            if use_unix:
                if Path(self.socket_path).exists():
                    return True
            else:
                try:
                    s = socket.create_connection((self.tcp_host, self.tcp_port), timeout=0.1)
                    s.close()
                    return True
                except OSError:
                    pass
            time.sleep(0.02)
        return False

    def _connect(self) -> socket.socket:
        if _use_unix_socket(self.socket_path) and Path(self.socket_path).exists():
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(self.socket_path)
            return s
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.tcp_host, self.tcp_port))
        return s

    def send(self, payload: dict[str, Any], timeout: float = 90.0) -> dict[str, Any]:
        """Send one JSON request and receive one JSON response.

        Uses sendall + recv loop instead of makefile("rwb") which is not
        supported on Windows sockets.
        """
        s = self._connect()
        s.settimeout(timeout)
        try:
            s.sendall((json.dumps(payload) + "\n").encode("utf-8"))
            # Read until newline — response is a single JSON line.
            buf = b""
            while b"\n" not in buf:
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
            line = buf.split(b"\n", 1)[0].strip()
            if not line:
                return {"ok": False, "error": "empty response"}
            return json.loads(line)
        except json.JSONDecodeError as e:
            return {"ok": False, "error": f"response decode: {e}"}
        except OSError as e:
            return {"ok": False, "error": f"socket error: {e}"}
        finally:
            try:
                s.close()
            except OSError:
                pass


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("PRADYOS_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    daemon = TitanDaemon()
    try:
        daemon.serve_forever()
    except KeyboardInterrupt:
        log.info("TITAN OPS shutting down by signal")
        daemon.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
