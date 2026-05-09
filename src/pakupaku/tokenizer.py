"""Sudachi 形態素解析のラッパー"""

from __future__ import annotations

from functools import lru_cache

from pakupaku.config import TECH_TERMS_PATH
from pakupaku.types import Sentence, Token


@lru_cache(maxsize=1)
def _get_tokenizer():
    """Sudachi tokenizer を遅延初期化してキャッシュする"""
    from sudachipy import dictionary, tokenizer

    tokenizer_obj = dictionary.Dictionary().create()
    mode = tokenizer.Tokenizer.SplitMode.C  # 長単位
    return tokenizer_obj, mode


@lru_cache(maxsize=1)
def _load_tech_terms() -> tuple[str, ...]:
    """専門用語辞書を読み込んで、長いものから順にタプルで返す

    長いものから先にマッチさせる必要がある (Vue.js を Vue より先にマッチさせるため)。
    """
    if not TECH_TERMS_PATH.exists():
        return ()
    terms: set[str] = set()
    with open(TECH_TERMS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                terms.add(line)
    return tuple(sorted(terms, key=len, reverse=True))


def _merge_tech_terms(tokens: list[Token]) -> list[Token]:
    """形態素解析結果を専門用語で結合する後処理

    例: ['Node', '.', 'js'] → ['Node.js'] (1 トークンに結合、品詞は名詞)
        ['VS', ' ', 'Code'] → ['VS Code'] (空白含む)

    アルゴリズム:
    1. トークン列を表層連結した文字列を構築
    2. 各専門用語について、表層連結文字列内の出現位置を検索
    3. 該当範囲のトークンを 1 つに結合
    """
    terms = _load_tech_terms()
    if not terms or not tokens:
        return tokens

    # 各トークンの開始位置を計算
    surfaces = [t.surface for t in tokens]
    concat = "".join(surfaces)
    # 各トークンが concat 内のどの範囲にあるか
    token_starts: list[int] = []
    pos = 0
    for s in surfaces:
        token_starts.append(pos)
        pos += len(s)

    # トークン index → 結合後のグループ index (初期は自分自身)
    group_id = list(range(len(tokens)))

    used_ranges: list[tuple[int, int]] = []  # (start_char, end_char) 既に結合済み範囲

    for term in terms:
        start = 0
        while True:
            idx = concat.find(term, start)
            if idx == -1:
                break
            end = idx + len(term)
            # 既に結合済み範囲と重なるならスキップ
            overlaps = any(not (end <= s or idx >= e) for s, e in used_ranges)
            if overlaps:
                start = idx + 1
                continue
            # idx〜end をカバーするトークン範囲を求める
            tstart: int | None = None
            tend: int | None = None
            for ti, (ts, ts_end) in enumerate(zip(token_starts, token_starts[1:] + [len(concat)])):
                if ts == idx:
                    tstart = ti
                if ts_end == end:
                    tend = ti  # tend は inclusive
                if tstart is not None and tend is not None:
                    break
            if tstart is None or tend is None:
                # トークン境界と一致しない場合はスキップ
                start = idx + 1
                continue
            # tstart..tend を 1 グループに
            for ti in range(tstart, tend + 1):
                group_id[ti] = tstart
            used_ranges.append((idx, end))
            start = end

    # group_id ごとにトークンを結合
    merged: list[Token] = []
    i = 0
    while i < len(tokens):
        gid = group_id[i]
        # 同じグループに属する連続トークンを集める
        j = i
        while j < len(tokens) and group_id[j] == gid:
            j += 1
        if j - i == 1:
            merged.append(tokens[i])
        else:
            # 結合: surface を連結、品詞は「名詞」(固有名詞扱い)、reading は連結
            combined_surface = "".join(t.surface for t in tokens[i:j])
            combined_reading = "".join(t.reading for t in tokens[i:j])
            merged.append(
                Token(
                    surface=combined_surface,
                    pos="名詞",
                    pos_detail=["固有名詞", "一般"],
                    reading=combined_reading,
                )
            )
        i = j

    return merged


def tokenize(text: str) -> Sentence:
    """テキストを形態素解析して Sentence に変換する

    後処理で専門用語 (Node.js, Vue.js 等) を 1 トークンに結合する。
    """
    tokenizer_obj, mode = _get_tokenizer()
    tokens: list[Token] = []
    for m in tokenizer_obj.tokenize(text, mode):
        pos_tuple = m.part_of_speech()
        # Sudachi の品詞は (主分類, 副分類1, 副分類2, 副分類3, 活用型, 活用形) の 6 要素
        pos = pos_tuple[0] if pos_tuple else ""
        pos_detail = list(pos_tuple[1:]) if len(pos_tuple) > 1 else []
        tokens.append(
            Token(
                surface=m.surface(),
                pos=pos,
                pos_detail=pos_detail,
                reading=m.reading_form(),
            )
        )
    # 専門用語を結合
    tokens = _merge_tech_terms(tokens)
    return Sentence(tokens=tokens, original_text=text)
