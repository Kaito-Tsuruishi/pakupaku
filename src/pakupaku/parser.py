"""係り受け解析のラッパー

GiNZA (spaCy 日本語版) で文節境界・係り受けを取得する。

注: GiNZA 5.2 + spaCy 3.8 + confection 1.3 の `compound_splitter` 型不整合は
`scripts/patch_ginza.py` で解消済み (uv sync 後に必ず実行)。
GiNZA がロードできない場合は Sudachi の形態素列ベースのフォールバックで動作するが、
精度は大幅に下がる。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from pakupaku.types import Sentence

_GINZA_AVAILABLE: bool | None = None


@lru_cache(maxsize=1)
def _get_nlp():
    """GiNZA pipeline を遅延初期化 (失敗時は None)"""
    global _GINZA_AVAILABLE
    try:
        import spacy

        nlp = spacy.load("ja_ginza")
        _GINZA_AVAILABLE = True
        return nlp
    except Exception as e:
        _GINZA_AVAILABLE = False
        import warnings

        warnings.warn(
            f"GiNZA load failed ({e}); falling back to Sudachi-only parser.",
            stacklevel=2,
        )
        return None


@dataclass
class ParsedSentence:
    """係り受け解析の中間表現

    GiNZA 利用時は doc に spaCy Doc が入る。フォールバック時は doc=None で、
    sentence.tokens (Sudachi 結果) を使って近似する。
    """

    doc: Any
    sentence: Sentence
    using_ginza: bool = field(default=False)


def parse_dependency(sentence: Sentence) -> ParsedSentence:
    """係り受け解析。GiNZA があれば使い、なければフォールバック"""
    nlp = _get_nlp()
    if nlp is not None:
        try:
            doc = nlp(sentence.original_text)
            return ParsedSentence(doc=doc, sentence=sentence, using_ginza=True)
        except Exception:
            pass
    return ParsedSentence(doc=None, sentence=sentence, using_ginza=False)


def count_root(parsed: ParsedSentence) -> int:
    """ROOT 数 (≒ 文数)。GiNZA 不在時は Sudachi 補助記号「。」の数で近似"""
    if parsed.using_ginza and parsed.doc is not None:
        return sum(1 for tok in parsed.doc if tok.dep_ == "ROOT")
    # フォールバック: 「。」の数 + 1 を文数の近似値、ただし末尾の「。」を除外
    period_count = sum(1 for t in parsed.sentence.tokens if t.surface in ("。", "！", "？"))
    if period_count == 0:
        return 1  # 句点がなくても 1 文と数える
    return period_count


def has_parse_error(parsed: ParsedSentence) -> bool:
    """解析破綻の検出"""
    if not parsed.sentence.tokens:
        return True
    if parsed.using_ginza and parsed.doc is not None and len(parsed.doc) == 0:
        return True
    return False


# 単独で「あ」「お」のような短い感動詞は接頭辞・名詞と紛らわしいので、
# 感動詞品詞のときだけマーカー扱いに限定する
_AMBIGUOUS_SHORT_MARKERS = {"あ", "お"}


def find_marker_positions(parsed: ParsedSentence, markers: set[str]) -> list[int]:
    """マーカー語の位置 (sentence.tokens の index) を返す

    位置の制約:
    - マーカー位置より前に名詞・動詞・形容詞 (内容語) が 1 つ以上あること
    - 短い曖昧マーカー (「あ」「お」) は感動詞品詞のときのみ採用
      (「お願い」の「お」(接頭辞) と紛らわしいため)
    """
    positions: list[int] = []
    seen_content = False
    for i, tok in enumerate(parsed.sentence.tokens):
        if seen_content and tok.surface in markers:
            # 曖昧マーカーは感動詞のみに限定
            if tok.surface in _AMBIGUOUS_SHORT_MARKERS and tok.pos != "感動詞":
                pass
            else:
                positions.append(i)
        if tok.pos in {"名詞", "動詞", "形容詞"}:
            seen_content = True
    return positions


def get_phrase_before(parsed: ParsedSentence, idx: int, n: int = 5) -> str:
    """idx の前 n トークン分の文字列 (sentence.tokens ベース)"""
    tokens = parsed.sentence.tokens
    start = max(0, idx - n)
    return "".join(t.surface for t in tokens[start:idx])


def get_phrase_after(parsed: ParsedSentence, idx: int, n: int = 5) -> str:
    """idx の後 n トークン分の文字列 (idx 自身は除く)"""
    tokens = parsed.sentence.tokens
    end = min(len(tokens), idx + 1 + n)
    return "".join(t.surface for t in tokens[idx + 1 : end])


def get_bunsetu_before(
    parsed: ParsedSentence, marker_surface: str, n_bunsetu: int = 1
) -> str | None:
    """GiNZA の文節を使って、マーカー直前の n 文節を取得

    `n_bunsetu` 指定で複数文節を結合して取得できる
    (例: 「Redisのコネクション」のように 2 文節にまたがる言い直しに対応)。

    GiNZA が利用できない場合は None を返す (呼び出し側でフォールバック必要)。
    """
    if not parsed.using_ginza or parsed.doc is None:
        return None
    try:
        import ginza

        marker_doc_idx = None
        for i, tok in enumerate(parsed.doc):
            if tok.text == marker_surface:
                marker_doc_idx = i
                break
        if marker_doc_idx is None:
            return None

        spans = list(ginza.bunsetu_spans(parsed.doc))
        prev_spans = [span for span in spans if span.end <= marker_doc_idx]
        if not prev_spans:
            return None
        target = prev_spans[-n_bunsetu:]
        return "".join(s.text for s in target)
    except Exception:
        return None


def get_bunsetu_after(
    parsed: ParsedSentence, marker_surface: str, n_bunsetu: int = 1
) -> str | None:
    """マーカー直後の n 文節を取得"""
    if not parsed.using_ginza or parsed.doc is None:
        return None
    try:
        import ginza

        marker_doc_idx = None
        for i, tok in enumerate(parsed.doc):
            if tok.text == marker_surface:
                marker_doc_idx = i
                break
        if marker_doc_idx is None:
            return None

        spans = list(ginza.bunsetu_spans(parsed.doc))
        next_spans = [span for span in spans if span.start > marker_doc_idx]
        if not next_spans:
            return None
        target = next_spans[:n_bunsetu]
        return "".join(s.text for s in target)
    except Exception:
        return None


def count_bunsetu_after_marker(parsed: ParsedSentence, marker_surface: str) -> int:
    """マーカー後の文節数を返す (前後対称の言い直しレンジ判定用)"""
    if not parsed.using_ginza or parsed.doc is None:
        return 0
    try:
        import ginza

        marker_doc_idx = None
        for i, tok in enumerate(parsed.doc):
            if tok.text == marker_surface:
                marker_doc_idx = i
                break
        if marker_doc_idx is None:
            return 0

        spans = list(ginza.bunsetu_spans(parsed.doc))
        return sum(1 for s in spans if s.start > marker_doc_idx)
    except Exception:
        return 0


def parse_complexity(parsed: ParsedSentence) -> float:
    """係り受けの複雑さを 0.0〜1.0 で返す

    GiNZA 利用時: ROOT 数 + 子の最大数を使う
    フォールバック時: 文長と句読点数を使った近似値
    """
    if parsed.using_ginza and parsed.doc is not None and len(parsed.doc) > 0:
        roots = count_root(parsed)
        max_children = max(
            (len(list(tok.children)) for tok in parsed.doc), default=0
        )
        return min(1.0, (roots * 0.3 + max_children * 0.1) / 2.0 + 0.3)
    # フォールバック: 文長 + 句読点数で近似
    n_tokens = len(parsed.sentence.tokens)
    if n_tokens == 0:
        return 0.0
    n_punct = sum(
        1 for t in parsed.sentence.tokens if t.pos == "補助記号"
    )
    score = min(1.0, n_tokens / 60.0 + n_punct * 0.1)
    return score
