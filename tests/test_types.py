"""Sentence/Token/ProcessingResult のテスト"""

from pakupaku.types import ProcessingResult, Sentence, Token


def test_sentence_to_text_skips_filler_and_repetition():
    tokens = [
        Token(surface="えーと", pos="感動詞", is_filler=True),
        Token(surface="明日", pos="名詞"),
        Token(surface="の", pos="助詞"),
        Token(surface="会議", pos="名詞"),
        Token(surface="です", pos="助動詞"),
    ]
    s = Sentence(tokens=tokens, original_text="えーと、明日の会議です")
    assert s.to_text() == "明日の会議です"


def test_visible_tokens_excludes_marked():
    tokens = [
        Token(surface="A", pos="名詞", is_filler=True),
        Token(surface="B", pos="名詞"),
        Token(surface="C", pos="名詞", is_repetition=True),
        Token(surface="D", pos="名詞"),
    ]
    s = Sentence(tokens=tokens, original_text="ABCD")
    visible = s.visible_tokens()
    assert [t.surface for t in visible] == ["B", "D"]


def test_processing_result_dataclass():
    s = Sentence(tokens=[], original_text="")
    r = ProcessingResult(
        input_text="x",
        output_text="y",
        intermediate=s,
        used_slm=False,
        trigger_reason=None,
        latency_ms=12.3,
    )
    assert r.input_text == "x"
    assert r.output_text == "y"
    assert r.used_slm is False
    assert r.trigger_reason is None
