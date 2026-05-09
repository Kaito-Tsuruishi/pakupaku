"""パイプライン (古典 NLP only) の統合テスト

Sudachi + GiNZA に依存するため、依存解決後に動作する。
朝のレビューで `uv run pytest tests/test_pipeline.py` で確認する想定。
"""

from __future__ import annotations

import pytest


def _try_import_pipeline():
    try:
        from pakupaku.pipeline import process

        return process
    except ImportError as e:
        pytest.skip(f"pakupaku dependencies not installed: {e}")


def test_pipeline_basic_filler_removal():
    process = _try_import_pipeline()
    result = process("えーと、お疲れ様です", slm_model=None)
    # フィラーが除去されているはず
    assert "えーと" not in result.output_text
    assert "お疲れ様です" in result.output_text
    assert result.used_slm is False


def test_pipeline_polite_sentence_unchanged():
    process = _try_import_pipeline()
    result = process("今日は天気が良いですね", slm_model=None)
    # フィラーがないので大きな変化はない
    assert "天気" in result.output_text
    assert result.used_slm is False


def test_pipeline_records_latency():
    process = _try_import_pipeline()
    result = process("テスト発話です", slm_model=None)
    assert result.latency_ms >= 0
    assert isinstance(result.latency_ms, float)
