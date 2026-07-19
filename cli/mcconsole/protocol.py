"""Thin newline-delimited-JSON client for the MCConsole Fabric mod's socket.

Kept deliberately synchronous and blocking: the socket is loopback-only
and round trips are sub-millisecond in practice, so there's no real need
for asyncio here, and it keeps the prompt_toolkit integration simple.
"""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from typing import Any


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


class GameConnection:
    """A single connection to the mod's socket server.

    One instance == one TCP connection == one attached terminal, matching
    the mod's "single client at a time" behavior.
    """

    def __init__(self, host: str, port: int, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._buffer = b""

    def connect(self) -> None:
        sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        sock.settimeout(self.timeout)
        self._sock = sock

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    @property
    def connected(self) -> bool:
        return self._sock is not None

    def _send(self, message: dict[str, Any]) -> None:
        if self._sock is None:
            raise NotConnectedError("Not connected to the game.")
        payload = (json.dumps(message) + "\n").encode("utf-8")
        try:
            self._sock.sendall(payload)
        except OSError as exc:
            self.close()
            raise NotConnectedError(str(exc)) from exc

    def _recv_line(self) -> dict[str, Any]:
        if self._sock is None:
            raise NotConnectedError("Not connected to the game.")

        while b"\n" not in self._buffer:
            try:
                chunk = self._sock.recv(65536)
            except OSError as exc:
                self.close()
                raise NotConnectedError(str(exc)) from exc
            if not chunk:
                self.close()
                raise NotConnectedError("Connection closed by game.")
            self._buffer += chunk

        line, _, rest = self._buffer.partition(b"\n")
        self._buffer = rest
        return json.loads(line.decode("utf-8"))

    def ping(self) -> str:
        self._send({"type": "ping"})
        response = self._recv_line()
        if response.get("type") != "pong":
            raise RuntimeError(f"Unexpected ping response: {response}")
        return response.get("connected_server", "unknown")

    def execute(self, text: str) -> ExecuteResult:
        self._send({"type": "execute", "text": text})
        response = self._recv_line()
        if response.get("type") == "error":
            return ExecuteResult(success=False, feedback=response.get("message", "error"))
        return ExecuteResult(
            success=bool(response.get("success", False)),
            feedback=response.get("feedback", ""),
        )

    def complete(self, text: str) -> list[Suggestion]:
        self._send({"type": "complete", "text": text})
        response = self._recv_line()
        if response.get("type") == "error":
            return []
        return [
            Suggestion(text=s["text"], start=s["start"], end=s["end"])
            for s in response.get("suggestions", [])
        ]

    def tree(self) -> dict[str, Any] | None:
        self._send({"type": "tree"})
        response = self._recv_line()
        if response.get("type") == "error":
            return None
        return response.get("root")
