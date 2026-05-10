"""pakupaku 常駐デーモン本体

Hammerspoon からの start/stop/toggle 通知を Unix ソケット経由で受け取り、
録音 → STT → 整形 → 貼り付けの一連の処理を実行する。

スレッド構成:
- メインスレッド: SLM/STT 処理を実行 (MLX モデルがロードされたスレッド)
- IPC スレッド: Unix ソケット listen、コマンドをキューに積む
- 録音は sounddevice のコールバック (専用スレッド) でリングバッファに溜める

MLX はロードしたスレッドからしか推論できないため、処理は必ずメインスレッドで行う。
"""

from __future__ import annotations

import json
import logging
import os
import queue
import signal
import threading
import time
from typing import Any

from pakupaku.clipboard import get_frontmost_app, paste_to_frontmost
from pakupaku.config import (
    DEFAULT_SLM_MODEL,
    DEFAULT_STT_MODEL,
    LOG_DIR,
    SOCKET_PATH,
)
from pakupaku.feedback import notify, play_start_sound, play_stop_sound, show_status
from pakupaku.ipc import UnixSocketServer
from pakupaku.pipeline import process
from pakupaku.recorder import Recorder

logger = logging.getLogger("pakupaku.daemon")


def _setup_logging() -> None:
    """ログ設定。

    PAKUPAKU_LOG_LEVEL 環境変数で出力レベルを制御できる
    (DEBUG / INFO / WARNING / ERROR、デフォルト INFO)。
    プライバシー上、発話内容をログに残したくない場合は WARNING 以上を指定する。
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    level_name = os.environ.get("PAKUPAKU_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_DIR / "daemon.log"),
            logging.StreamHandler(),
        ],
    )


class PakupakuDaemon:
    """pakupaku の常駐デーモン本体"""

    def __init__(self, no_slm: bool = False):
        self.recorder = Recorder()
        self.slm_model: Any | None = None
        self.no_slm = no_slm
        self._lock = threading.Lock()
        self._processing = False  # 処理中フラグ (連続押下防止)
        self.recorder.on_max_duration_callback = self._on_max_duration
        # メインスレッドで処理するためのタスクキュー
        # IPC スレッドからは「録音停止後の音声」を渡し、メインスレッドが消費する
        self._task_queue: queue.Queue = queue.Queue()

    def warm_up(self) -> None:
        """起動時のモデルロード"""
        logger.info("Warming up models ...")
        if not self.no_slm:
            try:
                from pakupaku.model_loader import get_slm

                self.slm_model = get_slm()
                logger.info("SLM loaded")
            except Exception as e:
                logger.warning(f"SLM load failed: {e}. Running without SLM fallback.")
                self.slm_model = None

        try:
            from pakupaku.stt import warm_up as stt_warm_up

            stt_warm_up()
            logger.info("STT model cached")
        except Exception as e:
            logger.warning(f"STT warm-up failed: {e}")

    def handle_command(self, command: str) -> str | None:
        """IPC から受け取ったコマンドを処理

        status コマンドのみ JSON 文字列を返す (CLI の `paku status` が読む)。
        その他のコマンドは None を返す (Hammerspoon は応答を読まない)。
        """
        command = command.strip().lower()
        logger.info(f"Received command: {command}")

        if command == "start":
            self._start_recording()
            return None
        if command == "stop":
            self._stop_recording()
            return None
        if command == "toggle":
            with self._lock:
                if self.recorder.is_recording:
                    self._stop_recording_locked()
                else:
                    self._start_recording_locked()
            return None
        if command == "status":
            return json.dumps(self._build_status())
        logger.warning(f"Unknown command: {command}")
        return None

    def _build_status(self) -> dict[str, Any]:
        return {
            "slm_loaded": self.slm_model is not None,
            "slm_model": DEFAULT_SLM_MODEL if self.slm_model is not None else None,
            "stt_model": DEFAULT_STT_MODEL,
            "recording": self.recorder.is_recording,
        }

    def _start_recording(self) -> None:
        with self._lock:
            self._start_recording_locked()

    def _start_recording_locked(self) -> None:
        if self.recorder.is_recording:
            logger.info("Already recording")
            return
        if self._processing:
            logger.info("Still processing previous recording, ignoring start")
            return
        try:
            self.recorder.start()
            play_start_sound()
            show_status("録音中...")
            logger.info("Recording started")
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            show_status(None)
            notify(f"録音開始失敗: {e}", title="pakupaku")

    def _stop_recording(self) -> None:
        with self._lock:
            self._stop_recording_locked()

    def _stop_recording_locked(self) -> None:
        if not self.recorder.is_recording:
            return
        try:
            audio = self.recorder.stop()
            play_stop_sound()
            show_status("処理中...")
            logger.info(f"Recording stopped: {audio.duration_seconds:.2f}s")
        except Exception as e:
            logger.error(f"Failed to stop recording: {e}")
            show_status(None)
            notify(f"録音停止失敗: {e}", title="pakupaku")
            return

        if audio.is_too_short:
            logger.info("Recording too short, ignoring")
            show_status(None)
            return

        # 貼り付け時のフォーカス先アプリを録音停止時点で固定する
        # (STT 中にユーザーがアプリを切り替えると別アプリへ誤貼り付けする事故を防ぐ)
        expected_app = get_frontmost_app()
        logger.debug(f"Frontmost app at stop: {expected_app}")

        # メインスレッドで処理させるためタスクキューに積む
        # (MLX はロードしたスレッドからしか推論できないため別スレッドでは動かない)
        self._processing = True
        self._task_queue.put((audio, expected_app))

    def _process_audio(self, audio, expected_app: str | None = None) -> None:
        try:
            from pakupaku.stt import transcribe

            t0 = time.perf_counter()
            stt_text = transcribe(audio)
            t1 = time.perf_counter()
            logger.info(f"STT: {(t1 - t0) * 1000:.0f}ms, text='{stt_text[:80]}'")

            if not stt_text:
                logger.info("STT result empty, skipping")
                return

            result = process(stt_text, slm_model=self.slm_model)
            t2 = time.perf_counter()
            logger.info(
                f"Pipeline: {(t2 - t1) * 1000:.0f}ms, used_slm={result.used_slm}, "
                f"reason={result.trigger_reason}, output='{result.output_text[:80]}'"
            )

            ok, status = paste_to_frontmost(result.output_text, expected_app=expected_app)
            logger.info(f"Paste: ok={ok}, status={status}")

            if not ok:
                if status == "paste_failed_text_in_clipboard":
                    notify("⌘V で貼り付けてください", title="pakupaku")
                elif status == "frontmost_app_changed_text_in_clipboard":
                    notify(
                        "貼り付け先のアプリが変わりました。⌘V で貼り付けてください",
                        title="pakupaku",
                    )
                else:
                    notify(f"貼り付け失敗: {status}", title="pakupaku")
        except Exception as e:
            logger.exception(f"Processing failed: {e}")
            notify(f"処理失敗: {e}", title="pakupaku")
        finally:
            show_status(None)
            self._processing = False

    def _on_max_duration(self) -> None:
        logger.warning("Max recording duration reached, auto-stopping")
        notify("録音時間が上限 (30 分) に達しました", title="pakupaku")
        self._stop_recording()


def main(no_slm: bool = False) -> None:
    """エントリポイント"""
    _setup_logging()
    logger.info(f"Starting pakupaku daemon (no_slm={no_slm})")

    daemon = PakupakuDaemon(no_slm=no_slm)
    daemon.warm_up()

    server = UnixSocketServer(SOCKET_PATH, daemon.handle_command)
    server.start()
    logger.info(f"Listening on {SOCKET_PATH}")

    # シグナルでクリーンに終了
    stop_event = threading.Event()

    def _shutdown(signum, _frame):
        logger.info(f"Received signal {signum}, shutting down")
        stop_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        # メインスレッドで処理キューを消費
        # IPC スレッドが録音停止時に (audio, expected_app) をキューに積む
        while not stop_event.is_set():
            try:
                task = daemon._task_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            try:
                audio, expected_app = task
                daemon._process_audio(audio, expected_app=expected_app)
            except Exception as e:
                logger.exception(f"Process failed in main loop: {e}")
            finally:
                daemon._task_queue.task_done()
    finally:
        server.stop()
        logger.info("Daemon stopped")


if __name__ == "__main__":
    main()
