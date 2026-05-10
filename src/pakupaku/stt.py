"""mlx-whisper による文字起こしのラッパー"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from pakupaku.config import DEFAULT_STT_INITIAL_PROMPT, DEFAULT_STT_MODEL
from pakupaku.model_loader import get_whisper_path

if TYPE_CHECKING:
    from pakupaku.recorder import RecordedAudio


def transcribe(audio: "RecordedAudio") -> str:
    """音声サンプルを文字起こしして文字列を返す

    Args:
        audio: RecordedAudio (samples + samplerate)

    Returns:
        文字起こし結果の文字列。失敗時または空音声時は ""。

    Note:
        word_timestamps はメモリリーク (Issue #1254) のため使用しない。
        clip_timestamps は処理時間 10 倍化 (Issue #1285) のため使用しない。
    """
    if audio.samples.size == 0:
        return ""

    return transcribe_samples(audio.samples)


def transcribe_samples(samples: np.ndarray, carryover_text: str = "") -> str:
    """生サンプル配列を文字起こしする (Phase 6 バックグラウンド STT 用)

    Args:
        samples: 音声サンプル (mono float32, 16kHz)
        carryover_text: 直前のチャンク末尾テキスト。Whisper の initial_prompt に
                       追記してチャンク境界を跨いだ文脈を引き継ぐ。

    Returns:
        文字起こし結果の文字列。空音声時は ""。
    """
    if samples.size == 0:
        return ""

    import mlx_whisper

    initial_prompt = DEFAULT_STT_INITIAL_PROMPT
    if carryover_text:
        # 既存の技術用語ヒントに、直前チャンクの実発話末尾を続けて
        # 文脈として渡す。Whisper は initial_prompt の最後を「直前の発話」と
        # 解釈する傾向があるため。
        initial_prompt = f"{initial_prompt}\n\n{carryover_text}"

    result = mlx_whisper.transcribe(
        samples,
        path_or_hf_repo=DEFAULT_STT_MODEL,
        language="ja",
        initial_prompt=initial_prompt,
        verbose=False,
    )
    text = result.get("text", "").strip() if isinstance(result, dict) else ""
    return text


def warm_up() -> None:
    """モデルキャッシュを確保 (起動時に呼ぶ想定)"""
    get_whisper_path()
