"""mlx-whisper による文字起こしのラッパー"""

from __future__ import annotations

from typing import TYPE_CHECKING

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

    import mlx_whisper

    # mlx-whisper は path_or_hf_repo を受け取る (HF repo id を直接渡せる)
    # initial_prompt で技術用語を Whisper に教え、固有名詞を保持させる
    result = mlx_whisper.transcribe(
        audio.samples,
        path_or_hf_repo=DEFAULT_STT_MODEL,
        language="ja",
        initial_prompt=DEFAULT_STT_INITIAL_PROMPT,
        # word_timestamps=True は使わない (メモリリーク)
        # clip_timestamps も使わない
        verbose=False,
    )
    text = result.get("text", "").strip() if isinstance(result, dict) else ""
    return text


def warm_up() -> None:
    """モデルキャッシュを確保 (起動時に呼ぶ想定)"""
    get_whisper_path()
