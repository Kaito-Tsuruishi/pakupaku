"""silero-vad ラッパー (バックグラウンド STT 用、Phase 6)

録音中の音声バッファに対して発話区間を検出し、無音区間で区切れたチャンクを返す。
silero-vad は 16kHz 固定なので、Recorder 側のサンプリングレートと合わせる前提。

設計:
- detect_completed_chunks(samples, last_emit_offset) → list[(start, end)]
  サンプル全体を毎回読み直して発話区間を計算するシンプル方式。
  最後に確定済みとして emit したサンプルオフセット以降の chunk のうち、
  「末尾に十分な無音があるもの」だけ返す (= もう発話が継続していないと判断できるもの)。
- 末尾に無音が足りないチャンクは未確定として保留 (発話継続中の可能性)
- 録音停止時は強制的に末尾までを最終チャンクとして emit する別 API がある
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import numpy as np

from pakupaku.config import (
    SAMPLE_RATE,
    VAD_MIN_SILENCE_MS,
    VAD_MIN_SPEECH_MS,
    VAD_SPEECH_THRESHOLD,
)

if TYPE_CHECKING:
    pass


_model = None
_model_lock = threading.Lock()


def _get_model():
    """silero-vad モデルを遅延ロード (プロセス内シングルトン)"""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from silero_vad import load_silero_vad

                _model = load_silero_vad()
    return _model


def detect_completed_chunks(
    samples: np.ndarray,
    last_emit_offset: int,
    samplerate: int = SAMPLE_RATE,
) -> list[tuple[int, int]]:
    """確定済みチャンク (発話の終端まで無音が続いているもの) を返す

    Args:
        samples: 録音開始からの全サンプル (mono, float32)
        last_emit_offset: 前回までに emit 済みのサンプルオフセット
                         (これ以降に新しく確定したチャンクだけ返す)
        samplerate: サンプリングレート (silero-vad は 16kHz 固定推奨)

    Returns:
        [(start_sample, end_sample), ...] のリスト。samples の絶対オフセット。
        無ければ空リスト。
    """
    if samples.size == 0 or samples.size <= last_emit_offset:
        return []

    from silero_vad import get_speech_timestamps

    model = _get_model()

    # silero-vad は 16kHz 想定。RecordedAudio が 16kHz なら samples をそのまま渡せる。
    timestamps = get_speech_timestamps(
        samples,
        model,
        sampling_rate=samplerate,
        threshold=VAD_SPEECH_THRESHOLD,
        min_speech_duration_ms=VAD_MIN_SPEECH_MS,
        min_silence_duration_ms=VAD_MIN_SILENCE_MS,
        return_seconds=False,  # サンプル単位で受け取る
    )

    if not timestamps:
        return []

    # 「末尾に min_silence 以上の無音が続いていれば確定」と判断する。
    # silero-vad の get_speech_timestamps は「発話区間のリスト」を返すので、
    # 最後の区間の end が「現在の samples の長さ」より min_silence 分以上離れていれば、
    # その区間以前は確定とみなせる。
    min_silence_samples = int(VAD_MIN_SILENCE_MS * samplerate / 1000)
    total_samples = samples.size

    completed: list[tuple[int, int]] = []
    for ts in timestamps:
        start = int(ts["start"])
        end = int(ts["end"])
        if end <= last_emit_offset:
            # 既に emit 済み
            continue
        if total_samples - end < min_silence_samples:
            # この区間の後ろにまだ十分な無音がない → 発話継続中の可能性、保留
            break
        completed.append((start, end))

    return completed


def detect_all_chunks_final(
    samples: np.ndarray,
    last_emit_offset: int,
    samplerate: int = SAMPLE_RATE,
) -> list[tuple[int, int]]:
    """録音停止時用: 末尾の無音条件を無視して、未 emit な発話区間を全て返す

    録音中は detect_completed_chunks で「無音が続いている確定済みチャンク」だけ
    取り出すが、停止時は「発話継続中で保留していたチャンク」も最終チャンクとして
    出力する必要があるため、こちらを使う。

    無音区間が無い (= 全部1チャンク) ケースもこの関数でカバーされる。
    """
    if samples.size == 0:
        return []

    from silero_vad import get_speech_timestamps

    model = _get_model()
    timestamps = get_speech_timestamps(
        samples,
        model,
        sampling_rate=samplerate,
        threshold=VAD_SPEECH_THRESHOLD,
        min_speech_duration_ms=VAD_MIN_SPEECH_MS,
        min_silence_duration_ms=VAD_MIN_SILENCE_MS,
        return_seconds=False,
    )

    if not timestamps:
        # 発話無しと判定されても、念のため samples 全体を 1 チャンクとして返す
        # (VAD の閾値で誤って全部無音扱いされた場合の救済)
        if samples.size > last_emit_offset:
            return [(last_emit_offset, samples.size)]
        return []

    chunks: list[tuple[int, int]] = []
    for ts in timestamps:
        start = int(ts["start"])
        end = int(ts["end"])
        if end <= last_emit_offset:
            continue
        chunks.append((start, end))
    return chunks


def warm_up() -> None:
    """モデルをプリロード (daemon 起動時の warm-up で呼ぶ用)"""
    _get_model()
