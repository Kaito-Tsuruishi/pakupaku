"""マイク録音 (sounddevice ベース)

トグル方式 (start/stop) で動作し、最大 30 分まで録音可能。
スリープ復帰時のデバイスインデックスのずれに対応するため、start のたびにデバイスを再列挙する。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import numpy as np

from pakupaku.config import (
    CHANNELS,
    DTYPE,
    MAX_RECORDING_SECONDS,
    MIN_RECORDING_SECONDS,
    SAMPLE_RATE,
)


@dataclass
class RecordedAudio:
    """録音結果"""

    samples: np.ndarray  # shape: (n_samples,) または (n_samples, channels)
    samplerate: int
    duration_seconds: float

    @property
    def is_too_short(self) -> bool:
        return self.duration_seconds < MIN_RECORDING_SECONDS


class Recorder:
    """マイクから録音するクラス (トグル方式)"""

    def __init__(
        self,
        samplerate: int = SAMPLE_RATE,
        channels: int = CHANNELS,
        dtype: str = DTYPE,
    ):
        self.samplerate = samplerate
        self.channels = channels
        self.dtype = dtype
        self._stream = None
        self._buffer: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._is_recording = False
        self._start_time: float | None = None
        self._max_duration_timer: threading.Timer | None = None

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    def _audio_callback(self, indata, frames, _time, _status):
        """sounddevice からのコールバック"""
        with self._lock:
            self._buffer.append(indata.copy())

    def start(self) -> None:
        """録音開始"""
        if self._is_recording:
            return

        import sounddevice as sd

        # スリープ復帰対策: 毎回デバイスリストを再列挙してデフォルトを使用させる
        # (sounddevice は内部で PortAudio をラップしており、明示的な reinit API はない。
        #  代わりにデフォルトデバイスを None にして OS に任せる)
        try:
            sd.default.device = None
            # query_devices() を呼ぶことで内部状態を最新化
            _ = sd.query_devices()
        except Exception:
            pass

        self._buffer.clear()
        self._stream = sd.InputStream(
            samplerate=self.samplerate,
            channels=self.channels,
            dtype=self.dtype,
            callback=self._audio_callback,
        )
        self._stream.start()
        self._start_time = time.perf_counter()
        self._is_recording = True

        # 最大録音時間タイマー
        self._max_duration_timer = threading.Timer(
            MAX_RECORDING_SECONDS, self._on_max_duration
        )
        self._max_duration_timer.daemon = True
        self._max_duration_timer.start()

    def _on_max_duration(self) -> None:
        """30 分経過で自動停止 (発火されたら on_max_duration_callback を呼ぶ)"""
        self.on_max_duration_callback()

    def on_max_duration_callback(self) -> None:
        """サブクラス・呼び出し元でオーバーライドして通知等を行う"""
        pass

    def stop(self) -> RecordedAudio:
        """録音停止して RecordedAudio を返す"""
        if not self._is_recording:
            return RecordedAudio(
                samples=np.zeros(0, dtype=np.float32),
                samplerate=self.samplerate,
                duration_seconds=0.0,
            )

        if self._max_duration_timer is not None:
            self._max_duration_timer.cancel()
            self._max_duration_timer = None

        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        duration = (
            time.perf_counter() - self._start_time if self._start_time else 0.0
        )
        self._is_recording = False
        self._start_time = None

        with self._lock:
            if not self._buffer:
                samples = np.zeros(0, dtype=np.float32)
            else:
                samples = np.concatenate(self._buffer, axis=0)
                # mono にする
                if samples.ndim > 1 and samples.shape[1] == 1:
                    samples = samples.flatten()
            self._buffer.clear()

        return RecordedAudio(
            samples=samples,
            samplerate=self.samplerate,
            duration_seconds=duration,
        )
