"""Unix ソケット IPC (Hammerspoon ↔ daemon)"""

from __future__ import annotations

import logging
import os
import socket
import threading
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger("pakupaku.ipc")


class UnixSocketServer:
    """シンプルな改行区切りメッセージ受信サーバー

    クライアント (Hammerspoon) は "start\\n" / "stop\\n" / "toggle\\n" を送る。
    handler が文字列を返した場合、その内容を改行付きで返信する (status などの応答用)。

    セキュリティ:
    - ~/.pakupaku/ ディレクトリを 0700 で作成 (オーナーのみアクセス可)
    - ソケットファイルを 0600 で作成 (オーナーのみ接続可)
    """

    def __init__(self, socket_path: Path, handler: Callable[[str], str | None]):
        self.socket_path = socket_path
        self.handler = handler
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        """サーバー起動 (別スレッド)"""
        # 親ディレクトリをオーナーのみアクセス可能で作成
        parent = self.socket_path.parent
        parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(parent, 0o700)
        except OSError:
            pass

        # 既存ソケットを削除 (前回終了時の残骸)
        if self.socket_path.exists():
            os.unlink(self.socket_path)

        # umask を一時的に絞ってからソケットを bind すると、
        # ソケットファイルがオーナーのみ接続可で生成される
        old_umask = os.umask(0o077)
        try:
            self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._server.bind(str(self.socket_path))
        finally:
            os.umask(old_umask)
        try:
            os.chmod(self.socket_path, 0o600)
        except OSError:
            pass
        self._server.listen(5)
        self._running = True

        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def _accept_loop(self) -> None:
        assert self._server is not None
        while self._running:
            try:
                client, _ = self._server.accept()
            except OSError:
                break
            try:
                data = client.recv(1024).decode("utf-8", errors="replace").strip()
                if data:
                    for line in data.splitlines():
                        line = line.strip()
                        if line:
                            response = self.handler(line)
                            if response is not None:
                                try:
                                    client.sendall((response + "\n").encode("utf-8"))
                                except Exception:
                                    logger.exception("Failed to send response")
            except Exception:
                logger.exception("Error handling client connection")
            finally:
                client.close()

    def stop(self) -> None:
        """サーバー停止"""
        self._running = False
        if self._server is not None:
            try:
                self._server.close()
            except Exception:
                pass
            self._server = None
        if self.socket_path.exists():
            try:
                os.unlink(self.socket_path)
            except Exception:
                pass
