"""Thin newline-delimited-JSON client for the MCConsole Fabric mod's socket.

Kept deliberately synchronous and blocking for callers: the socket is
loopback-only and round trips are sub-millisecond in practice, so there's
no real need for asyncio here, and it keeps the prompt_toolkit integration
simple.

The wire protocol has no request-ID correlation — it assumes exactly one
*request* (ping/execute/complete/tree) is ever in flight at a time, which
`_lock` enforces. The one exception is `chat`: the mod pushes those
unprompted whenever a chat/log line arrives in-game, so a background
reader thread pulls every line off the socket and routes it — `chat`
messages go straight to `chat_callback`, everything else is handed to
whichever request is currently waiting on it.
"""

from __future__ import annotations

import json
import queue
import socket
import threading
from dataclasses import dataclass
from typing import Any, Callable


class NotConnectedError(RuntimeError):
    """Raised when a request is made without an active game connection."""


@dataclass
class ExecuteResult:
    success: bool
    feedback: str


@dataclass
class Suggestion:
    text: str
    start: int
    end: int


_DISCONNECTED = object()


class GameConnection:
    """A single connection to the mod's socket server.

    One instance == one TCP connection == one attached terminal, matching
    the mod's "single client at a time" behavior.
    """

    def __init__(self, host: str, port: int, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.chat_callback: Callable[[str], None] | None = None
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()
        self._responses: queue.Queue[Any] = queue.Queue()
        self._reader_thread: threading.Thread | None = None

    def connect(self) -> None:
        sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        sock.settimeout(None)  # the reader thread blocks indefinitely; requests use their own queue timeout
        self._sock = sock
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True, name="mcconsole-reader")
        self._reader_thread.start()

    def close(self) -> None:
        sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    @property
    def connected(self) -> bool:
        return self._sock is not None

    def _read_loop(self) -> None:
        sock = self._sock
        buffer = b""
        try:
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    return
                buffer += chunk
                while b"\n" in buffer:
                    line, _, buffer = buffer.partition(b"\n")
                    if not line.strip():
                        continue
                    try:
                        message = json.loads(line.decode("utf-8"))
                    except json.JSONDecodeError:
                        continue

                    if message.get("type") == "chat":
                        callback = self.chat_callback
                        if callback is not None:
                            callback(message.get("text", ""))
                        continue

                    self._responses.put(message)
        except OSError:
            return
        finally:
            self.close()
            self._responses.put(_DISCONNECTED)

    def _send(self, message: dict[str, Any]) -> None:
        if self._sock is None:
            raise NotConnectedError("Not connected to the game.")
        payload = (json.dumps(message) + "\n").encode("utf-8")
        try:
            self._sock.sendall(payload)
        except OSError as exc:
            self.close()
            raise NotConnectedError(str(exc)) from exc

    def _request(self, message: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._send(message)
            try:
                response = self._responses.get(timeout=self.timeout)
            except queue.Empty:
                self.close()
                raise NotConnectedError("Timed out waiting for a response from the game.")
        if response is _DISCONNECTED:
            raise NotConnectedError("Connection closed by game.")
        return response

    def ping(self) -> str:
        response = self._request({"type": "ping"})
        if response.get("type") != "pong":
            raise RuntimeError(f"Unexpected ping response: {response}")
        return response.get("connected_server", "unknown")

    def execute(self, text: str) -> ExecuteResult:
        response = self._request({"type": "execute", "text": text})
        if response.get("type") == "error":
            return ExecuteResult(success=False, feedback=response.get("message", "error"))
        return ExecuteResult(
            success=bool(response.get("success", False)),
            feedback=response.get("feedback", ""),
        )

    def complete(self, text: str) -> list[Suggestion]:
        response = self._request({"type": "complete", "text": text})
        if response.get("type") == "error":
            return []
        return [
            Suggestion(text=s["text"], start=s["start"], end=s["end"])
            for s in response.get("suggestions", [])
        ]

    def tree(self) -> dict[str, Any] | None:
        response = self._request({"type": "tree"})
        if response.get("type") == "error":
            return None
        return response.get("root")
