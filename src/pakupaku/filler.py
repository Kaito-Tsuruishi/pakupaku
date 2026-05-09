"""フィラー除去 (古典 NLP)

設計原則: **言っていないことは補わず、意味が変わる語は消さない**

検出方針:
- 辞書マッチ (純粋なフィラー語のみ登録)
- Sudachi の品詞「感動詞」のトークン
- 「あー」「えー」など Sudachi が分割した連結フィラーの救済
  (「えー」「と」のように分割されたとき、フィラー直後の「と」を連結扱い)

意図的にやらないこと:
- 「あの/その/この」を一律フィラー扱いしない (連体詞として意味あり)
- 「ちょっと」「だから」「それで」は副詞・接続詞として意味があるので消さない
- 「すみません」「失礼」は呼びかけ・謝罪として意味があるので消さない
- 文末の「ね」「よ」は意思表示として残す
"""

from __future__ import annotations

from functools import lru_cache

from pakupaku.config import FILLER_DICT_PATH
from pakupaku.types import Sentence


@lru_cache(maxsize=1)
def load_filler_dict() -> frozenset[str]:
    """フィラー辞書をディスクから読み込んでセットで返す"""
    fillers: set[str] = set()
    if not FILLER_DICT_PATH.exists():
        return frozenset()
    with open(FILLER_DICT_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                fillers.add(line)
    return frozenset(fillers)


# 感動詞だがフィラーではない語 (挨拶・呼びかけ・応答・お礼など、意味のある発話)
# Sudachi は「ありがとう」「はい」「おはようございます」も感動詞と判定するが、
# これらは消してはいけない。
_INTERJECTION_NOT_FILLER = frozenset(
    {
        # 挨拶
        "おはよう", "おはようございます", "こんにちは", "こんばんは",
        "おやすみ", "おやすみなさい", "さようなら", "さよなら",
        "お疲れ", "おつかれ", "お疲れ様", "おつかれさま",
        "失礼します", "失礼", "失礼しました",
        # お礼・謝罪
        "ありがとう", "ありがとうございます", "ありがとうございました",
        "すみません", "すいません", "ごめんなさい", "ごめん",
        "申し訳ありません", "申し訳ない",
        # 応答 (Yes/No)
        "はい", "いいえ", "ええ", "うん", "いえ", "ううん",
        "はーい", "へい",
        # 同意・相槌 (これらは意味あり)
        "そう", "そうそう", "そうですね", "なるほど",
        "了解", "承知", "わかりました",
        # 呼びかけ
        "よろしく", "よろしくお願いします",
        # 賛美・驚き (意味的に重要)
        "やった", "よかった", "よし",
    }
)


def _is_filler_token(surface: str, pos: str, fillers: frozenset[str]) -> bool:
    """単一トークンがフィラーか判定する"""
    # 1. 辞書マッチ
    if surface in fillers:
        return True
    # 2. 感動詞でもフィラーでない語 (挨拶・お礼・応答等) は除外
    if surface in _INTERJECTION_NOT_FILLER:
        return False
    # 3. 感動詞は原則フィラー (Sudachi の品詞判定を信頼)
    if pos == "感動詞":
        return True
    return False


def remove_fillers(sentence: Sentence) -> Sentence:
    """形態素解析結果からフィラーをマークする (削除はしない、整形時に除外)

    挙動:
    1. 辞書マッチ・感動詞品詞のトークンを is_filler = True
    2. フィラーの直後に続く特定の助詞だけ連結除去対象に
       (「えー」(感動詞) + 「と」(助詞) のような分割を救済)
    3. 文頭の連続フィラーの直後にある浮いた読点を除去 (整形上のノイズ除去)

    注意:
    - 連体詞「あの/その/この」は除去しない (「あの本」「この件」のように意味あり)
    - 「ちょっと」「だから」等の接続詞・副詞は辞書に入っていないので残す
    """
    fillers = load_filler_dict()
    tokens = sentence.tokens

    # Pass 1: 単発判定 (辞書 + 感動詞のみ)
    for tok in tokens:
        if _is_filler_token(tok.surface, tok.pos, fillers):
            tok.is_filler = True

    # Pass 2: フィラー直後の連結ヘルパー助詞をフィラー扱い
    # 「えー」(感動詞) + 「と」(助詞) のような Sudachi 分割を救済
    # 限定的なヘルパー助詞のみ対象
    _CONNECTING_HELPERS = {"と", "ー", "っ"}
    for i in range(1, len(tokens)):
        prev = tokens[i - 1]
        curr = tokens[i]
        if (
            prev.is_filler
            and curr.pos == "助詞"
            and not curr.is_filler
            and curr.surface in _CONNECTING_HELPERS
        ):
            curr.is_filler = True

    # Pass 3: 文頭の連続フィラー後の浮いた読点を除去
    # (「えーと、明日」→ 「明日」 のため「、」もフィラー扱いに)
    leading_done = False
    for tok in tokens:
        if leading_done:
            break
        if tok.is_filler:
            continue
        if tok.pos == "補助記号" and tok.surface == "、":
            # 文頭で続いていた読点はフィラーの一部とみなす
            tok.is_filler = True
            continue
        leading_done = True

    return sentence


def collapse_consecutive_punctuation(text: str) -> str:
    """連続する読点・句点を 1 つに、行頭の句読点を除去 (整形最終段で使用)"""
    if not text:
        return text
    while "、、" in text:
        text = text.replace("、、", "、")
    while "。。" in text:
        text = text.replace("。。", "。")
    while "、。" in text:
        text = text.replace("、。", "。")
    while text and text[0] in {"、", "。"}:
        text = text[1:]
    return text
