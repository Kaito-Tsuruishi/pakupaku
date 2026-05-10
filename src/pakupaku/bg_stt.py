"""バックグラウンド STT オーケストレーション (Phase 6、案 C)

設計概要:
- 録音中に VAD 監視スレッドが定期的に Recorder.snapshot() を取り、無音 1.5s で
  確定したチャンクを発見すると _audio_chunk_queue に積む。
- daemon のメインスレッドはこのキューから取り出して mlx-whisper で STT を実行し、
  結果を _text_buffer に時系列順に追記する。
- 録音停止時は finalize() で:
    1. VAD 監視を止める
    2. 残りの未 emit な音声を全て最終チャンクとして積む
    3. 全チャンクの STT 完了を待ち、連結テキストを返す
- 整形 (フィラー除去・言い直し検出・SLM)・貼り付けは呼び出し側 (daemon._process_audio
  相当) が連結テキストに対して 1 回だけ行う。整形ロジックは現状のまま。

MLX のスレッド制約:
- mlx-whisper は MLX モデルがロードされたスレッドからしか推論できない。
- このため STT 実行は呼び出し元 (daemon メインスレッド) に任せる設計とし、
  本モジュールはチャンク切り出しと結果バッファの管理だけを担う。

オプトイン:
- daemon は環境変数 PAKUPAKU_BG_STT が真のときだけ BackgroundSTT を有効化する。
- 無効時は録音停止後にまとめて transcribe する従来の一括処理を使う。
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass

import numpy as np

from pakupaku.config import (
    BG_STT_MAX_CHUNK_SEC,
    BG_STT_VAD_POLL_INTERVAL,
    SAMPLE_RATE,
    STT_PROMPT_CARRYOVER_CHARS,
)
from pakupaku.recorder import Recorder
from pakupaku.vad import detect_all_chunks_final, detect_completed_chunks

logger = logging.getLogger("pakupaku.bg_stt")


@dataclass
class _Chunk:
    """STT 待ちチャンク。順序保証のためインデックスを持つ"""

    index: int
    samples: np.ndarray  # mono float32
    is_final: bool  # 録音停止時の最終チャンクかどうか


class BackgroundSTT:
    """録音中に VAD で発話区間を検出し、メインスレッドに STT タスクを投入する

    使い方:
        bg = BackgroundSTT(recorder)
        bg.start()  # 録音開始時に呼ぶ
        # ... メインスレッドでループ:
        while True:
            chunk = bg.poll_chunk(timeout=0.5)
            if chunk is None:
                continue
            text = transcribe_samples(chunk.samples, carryover_text=...)
            bg.add_text(chunk.index, text)
            if chunk.is_final:
                break
        full_text = bg.finalize_text()
        bg.stop()
    """

    def __init__(
        self,
        recorder: Recorder,
        external_queue: queue.Queue | None = None,
        samplerate: int = SAMPLE_RATE,
    ):
        """
        Args:
            recorder: 録音中の Recorder インスタンス
            external_queue: チャンクを積むキュー。daemon の _task_queue を共有する想定。
                           None なら内部キューを使う (主にテスト用)。
            samplerate: サンプリングレート
        """
        self._recorder = recorder
        self._samplerate = samplerate
        self._chunk_queue: queue.Queue = external_queue if external_queue is not None else queue.Queue()
        self._vad_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_emit_offset = 0
        self._next_index = 0
        self._chunk_lock = threading.Lock()
        # STT 結果テキストをチャンクインデックス順に保持
        self._texts: dict[int, str] = {}
        self._texts_lock = threading.Lock()
        self._final_emitted = False
        # 完了 (最終チャンク含む全 STT 終了) を待つためのイベント
        self._done_event = threading.Event()
        self._expected_count = 0  # emit 済みチャンク数

    def start(self) -> None:
        """VAD 監視スレッドを起動 (録音開始済みである前提)"""
        if self._vad_thread is not None:
            logger.warning("BackgroundSTT.start called twice")
            return
        self._stop_event.clear()
        self._last_emit_offset = 0
        self._next_index = 0
        self._final_emitted = False
        with self._texts_lock:
            self._texts.clear()
        # キューを空にする
        while not self._chunk_queue.empty():
            try:
                self._chunk_queue.get_nowait()
            except queue.Empty:
                break
        self._vad_thread = threading.Thread(
            target=self._vad_loop, daemon=True, name="pakupaku-vad"
        )
        self._vad_thread.start()
        logger.info("BackgroundSTT started")

    def stop(self) -> None:
        """VAD 監視スレッドを停止 (finalize 完了後に呼ぶ想定)"""
        self._stop_event.set()
        if self._vad_thread is not None:
            self._vad_thread.join(timeout=2.0)
            self._vad_thread = None
        logger.info("BackgroundSTT stopped")

    def _vad_loop(self) -> None:
        """録音中、定期的に VAD でチャンク検出してキューに積む

        VAD で発話区間が確定しない場合 (= ずっと喋り続けて無音が来ない場合)、
        BG_STT_MAX_CHUNK_SEC 経過した時点で強制的にチャンクを切る。
        Whisper は文の途中で切れても prompt 引数で前チャンクの末尾文脈を
        引き継ぐので、大きな精度劣化はない想定。
        """
        max_chunk_samples = int(BG_STT_MAX_CHUNK_SEC * self._samplerate)
        while not self._stop_event.is_set():
            try:
                samples = self._recorder.snapshot()
                if samples.size > self._last_emit_offset:
                    completed = detect_completed_chunks(
                        samples,
                        self._last_emit_offset,
                        samplerate=self._samplerate,
                    )
                    for start, end in completed:
                        self._enqueue_chunk(samples, start, end, is_final=False)
                        self._last_emit_offset = end

                    # VAD で確定しなかった場合の強制カット判定。
                    # 前回 emit からの未処理サンプルが MAX を超えていたら時間カット。
                    if BG_STT_MAX_CHUNK_SEC > 0:
                        unprocessed = samples.size - self._last_emit_offset
                        if unprocessed >= max_chunk_samples:
                            cut_end = self._last_emit_offset + max_chunk_samples
                            logger.info(
                                f"forced cut at {cut_end / self._samplerate:.1f}s "
                                f"(no VAD boundary within {BG_STT_MAX_CHUNK_SEC}s)"
                            )
                            self._enqueue_chunk(
                                samples,
                                self._last_emit_offset,
                                cut_end,
                                is_final=False,
                            )
                            self._last_emit_offset = cut_end
            except Exception:
                logger.exception("VAD loop error")
            self._stop_event.wait(BG_STT_VAD_POLL_INTERVAL)

    def _enqueue_chunk(
        self,
        all_samples: np.ndarray,
        start: int,
        end: int,
        is_final: bool,
    ) -> None:
        """確定したチャンクをキューに積む

        外部キュー (daemon の _task_queue) を共有している場合、
        ("bg_chunk", _Chunk, self) の形で積む。daemon 側がディスパッチする。
        """
        with self._chunk_lock:
            chunk_samples = all_samples[start:end].copy()
            index = self._next_index
            self._next_index += 1
            self._expected_count = max(self._expected_count, index + 1)
        chunk = _Chunk(index=index, samples=chunk_samples, is_final=is_final)
        self._chunk_queue.put(("bg_chunk", chunk, self))
        logger.info(
            f"chunk enqueued: index={index}, "
            f"duration={chunk_samples.size / self._samplerate:.2f}s, "
            f"final={is_final}"
        )

    def emit_remaining_as_final(self, samples: np.ndarray | None = None) -> None:
        """録音停止時、残りの未 emit な音声を最終チャンク群としてキューに積む

        VAD 監視スレッドと VAD モデル (torch) のアクセスが競合して
        ネイティブクラッシュを起こすことがあるため、まず VAD 監視スレッドを
        確実に停止してから VAD を呼び直す。

        Args:
            samples: 録音停止後の全サンプル。None の場合は recorder.snapshot() を使う
                    (Recorder.stop() が呼ばれる前提なら最終 buffer が入っている)
        """
        if self._final_emitted:
            logger.warning("emit_remaining_as_final called twice")
            return

        # VAD 監視スレッドを停止して、torch モデルへの同時アクセスを避ける
        self._stop_event.set()
        if self._vad_thread is not None:
            self._vad_thread.join(timeout=3.0)
            self._vad_thread = None

        if samples is None:
            samples = self._recorder.snapshot()

        chunks = detect_all_chunks_final(
            samples,
            self._last_emit_offset,
            samplerate=self._samplerate,
        )

        if not chunks:
            # 残り音声が無かった場合は、追加の chunk なしで完了扱いにする
            self._final_emitted = True
            with self._texts_lock:
                if len(self._texts) >= self._expected_count:
                    self._done_event.set()
            return

        for i, (start, end) in enumerate(chunks):
            is_final = i == len(chunks) - 1
            self._enqueue_chunk(samples, start, end, is_final=is_final)
            self._last_emit_offset = end
        self._final_emitted = True

    def poll_chunk(self, timeout: float | None = None) -> _Chunk | None:
        """STT 待ちチャンクを 1 つ取り出す (メインスレッドで使う)"""
        try:
            return self._chunk_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def add_text(self, index: int, text: str) -> None:
        """STT 結果を順序付きで保存。全チャンク受領済みなら _done_event を立てる"""
        with self._texts_lock:
            self._texts[index] = text
            if (
                self._final_emitted
                and len(self._texts) >= self._expected_count
            ):
                self._done_event.set()

    def wait_done(self, timeout: float | None = None) -> bool:
        """全チャンクの STT 完了を待つ。タイムアウト時は False"""
        return self._done_event.wait(timeout=timeout)

    def finalize_text(self) -> str:
        """全チャンクの STT 結果を順番通りに連結して返す"""
        with self._texts_lock:
            ordered = [self._texts[i] for i in sorted(self._texts.keys())]
        return "".join(ordered)

    def carryover_for_next(self, up_to_index: int) -> str:
        """指定 index までの末尾文字を Whisper の prompt に渡す用に返す"""
        with self._texts_lock:
            ordered = [self._texts[i] for i in sorted(self._texts.keys()) if i < up_to_index]
        joined = "".join(ordered)
        if not joined:
            return ""
        return joined[-STT_PROMPT_CARRYOVER_CHARS:]
