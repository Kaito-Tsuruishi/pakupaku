"""IPC (Unix ソケット) のテスト

Unix ドメインソケットのパス長制限 (約 104 文字) を避けるため、
pytest の tmp_path ではなく短い `/tmp` 直下のソケットパスを使う。
"""

from __future__ import annotations

import os
import socket
import time
import uuid
from pathlib import Path

import pytest

from pakupaku.ipc import UnixSocketServer


@pytest.fixture
def short_socket_path(tmp_path: Path) -> Path:
    """100 文字未満の短いソケットパスを返す"""
    # /tmp/pakupaku-test-<uuid>.sock の形式 (約 40 文字)
    socket_path = Path("/tmp") / f"pakupaku-test-{uuid.uuid4().hex[:8]}.sock"
    yield socket_path
    if socket_path.exists():
        try:
            os.unlink(socket_path)
        except Exception:
            pass


def test_unix_socket_server_receives_message(short_socket_path: Path):
    """サーバーを起動してクライアントから送信したメッセージが handler に届くか"""
    received: list[str] = []
    server = UnixSocketServer(short_socket_path, received.append)
    server.start()
    try:
        for _ in range(20):
            if short_socket_path.exists():
                break
            time.sleep(0.05)

        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(str(short_socket_path))
        client.sendall(b"start\n")
        client.close()

        for _ in range(20):
            if received:
                break
            time.sleep(0.05)

        assert received == ["start"]
    finally:
        server.stop()


def test_unix_socket_server_multiple_messages(short_socket_path: Path):
    received: list[str] = []
    server = UnixSocketServer(short_socket_path, received.append)
    server.start()
    try:
        for _ in range(20):
            if short_socket_path.exists():
                break
            time.sleep(0.05)

        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(str(short_socket_path))
        client.sendall(b"start\nstop\n")
        client.close()

        for _ in range(20):
            if len(received) >= 2:
                break
            time.sleep(0.05)

        assert received == ["start", "stop"]
    finally:
        server.stop()
