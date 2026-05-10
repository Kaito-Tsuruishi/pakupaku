"""bg_stt と vad の単体テスト

実音声を扱うので、合成的な無音/正弦波で発話区間検出を再現する。
silero-vad の挙動はモデル依存なので、ここではロジック面のチェックを主にする。
"""

from __future__ import annotations

import queue

import numpy as np
import pytest

from pakupaku.bg_stt import BackgroundSTT, _Chunk
from pakupaku.config import SAMPLE_RATE


def _silence(seconds: float) -> np.ndarray:
    return np.zeros(int(seconds * SAMPLE_RATE), dtype=np.float32)


class _FakeRecorder:
    """Recorder のスナップショット API だけ模倣するスタブ"""

    def __init__(self):
        self.samples = np.zeros(0, dtype=np.float32)

    def snapshot(self) -> np.ndarray:
        return self.samples


def test_emit_remaining_with_no_speech_completes_immediately():
    """音声が空のとき、emit_remaining_as_final は即座に done を立てる"""
    recorder = _FakeRecorder()
    q: queue.Queue = queue.Queue()
    bg = BackgroundSTT(recorder, external_queue=q)
    bg.start()
    bg.emit_remaining_as_final(samples=np.zeros(0, dtype=np.float32))
    assert bg.wait_done(timeout=1.0)
    assert bg.finalize_text() == ""
    bg.stop()


def test_finalize_text_orders_by_index():
    """add_text の順序に関係なく、index 順にテキストが連結される"""
    recorder = _FakeRecorder()
    bg = BackgroundSTT(recorder)
    bg.start()
    bg.add_text(2, "三")
    bg.add_text(0, "一")
    bg.add_text(1, "二")
    assert bg.finalize_text() == "一二三"
    bg.stop()


def test_carryover_truncates_to_configured_length():
    """carryover_for_next は設定文字数で切り詰められる"""
    from pakupaku.config import STT_PROMPT_CARRYOVER_CHARS

    recorder = _FakeRecorder()
    bg = BackgroundSTT(recorder)
    bg.start()
    long_text = "あ" * (STT_PROMPT_CARRYOVER_CHARS + 20)
    bg.add_text(0, long_text)
    carry = bg.carryover_for_next(up_to_index=1)
    assert len(carry) == STT_PROMPT_CARRYOVER_CHARS
    assert carry == "あ" * STT_PROMPT_CARRYOVER_CHARS
    bg.stop()


def test_carryover_excludes_current_index():
    """carryover_for_next(N) は index<N までの結果のみ含める"""
    recorder = _FakeRecorder()
    bg = BackgroundSTT(recorder)
    bg.start()
    bg.add_text(0, "アルファ")
    bg.add_text(1, "ベータ")
    bg.add_text(2, "ガンマ")
    assert bg.carryover_for_next(up_to_index=0) == ""
    # index=0 までを連結すると "アルファ"
    assert bg.carryover_for_next(up_to_index=1).endswith("アルファ")
    # index=2 直前なら "アルファベータ" の末尾
    assert bg.carryover_for_next(up_to_index=2).endswith("ベータ")
    bg.stop()


def test_done_event_after_all_texts_received():
    """全 emit 済みチャンクの STT 結果が揃うと wait_done が True を返す"""
    recorder = _FakeRecorder()
    q: queue.Queue = queue.Queue()
    bg = BackgroundSTT(recorder, external_queue=q)
    bg.start()
    # 1.5 秒の発話相当 + 2 秒の無音 + 1 秒の発話相当 を作る
    speech1 = np.full(int(1.5 * SAMPLE_RATE), 0.05, dtype=np.float32)
    silence = _silence(2.0)
    speech2 = np.full(int(1.0 * SAMPLE_RATE), 0.05, dtype=np.float32)
    samples = np.concatenate([speech1, silence, speech2])
    recorder.samples = samples
    bg.emit_remaining_as_final(samples=samples)

    # 投入されたチャンクをキューから取り出して add_text していく
    while not bg._done_event.is_set():
        try:
            task = q.get(timeout=1.0)
        except queue.Empty:
            break
        kind, chunk, owner = task
        assert kind == "bg_chunk"
        assert owner is bg
        bg.add_text(chunk.index, f"text_{chunk.index}")

    assert bg.wait_done(timeout=1.0)
    text = bg.finalize_text()
    # 少なくとも 1 チャンクは検出されているはず
    assert len(text) > 0
    bg.stop()


def test_chunk_dataclass_carries_index_and_final_flag():
    chunk = _Chunk(index=3, samples=np.zeros(10, dtype=np.float32), is_final=True)
    assert chunk.index == 3
    assert chunk.is_final is True
    assert chunk.samples.size == 10


@pytest.mark.parametrize(
    "env_value,expected",
    [
        ("", False),
        ("0", False),
        ("false", False),
        ("1", True),
        ("true", True),
        ("on", True),
        ("yes", True),
    ],
)
def test_bg_stt_enabled_env_parsing(env_value, expected, monkeypatch):
    from pakupaku.daemon import _bg_stt_enabled

    if env_value == "":
        monkeypatch.delenv("PAKUPAKU_BG_STT", raising=False)
    else:
        monkeypatch.setenv("PAKUPAKU_BG_STT", env_value)
    assert _bg_stt_enabled() is expected
