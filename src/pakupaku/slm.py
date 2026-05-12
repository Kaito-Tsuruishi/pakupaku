"""SLM (Gemma-4-E2B-it-4bit) 呼び出しモジュール

設計原則:
- SLM の出力は「フィラー・言い直しの除去 + 句読点」のみを期待する
- 内容の改変・補完・要約・置換は禁止
- 安全装置: SLM 出力が原文より極端に短い/長い場合、または重要語 (固有名詞・数値) が
  消失した場合は、SLM 結果を破棄して古典 NLP の結果を使う

Note: Gemma 4 はマルチモーダル前提のためロードに mlx-vlm を使う。
"""

from __future__ import annotations

from pakupaku.config import SLM_MAX_TOKENS, SLM_PROMPT_TEMPLATE, SLM_TEMPERATURE
from pakupaku.tokenizer import tokenize
from pakupaku.types import Sentence


class SLMUnsafeOutput(Exception):
    """SLM が原文の内容を改変した疑いがあるとき送出"""


# SLM 出力が原文比でこれ以下になったら異常 (要約・削りすぎ)
_MIN_LENGTH_RATIO = 0.4
# SLM 出力が原文比でこれ以上になったら異常 (補完・水増し)
_MAX_LENGTH_RATIO = 1.5


def slm_repair(sentence: Sentence, model_pair) -> Sentence:
    """SLM に整形を依頼し、結果を再形態素解析して Sentence を返す

    Args:
        sentence: フィラー除去・言い直し検出済みの中間表現
        model_pair: (model, processor) のタプル (mlx_vlm.load の戻り値)

    Returns:
        SLM 出力を形態素解析し直した新しい Sentence
    """
    from mlx_vlm import generate
    from mlx_vlm.prompt_utils import apply_chat_template

    model, processor = model_pair
    # 元発話 (original_text) を渡す。古典で削除済みの結果を渡すと、
    # SLM は「整形済み」と認識してそのまま返してしまう。
    # 古典で消しすぎた語を復元できないので、元発話から SLM が判断すべき。
    input_text = sentence.original_text
    # 安全装置で比較する基準は「古典 NLP の整形結果」
    # (古典が既に削除した語は SLM が出力に含めなくても問題ない)
    classic_baseline = sentence.to_text() or input_text
    prompt = SLM_PROMPT_TEMPLATE.format(input=input_text)

    config = getattr(model, "config", None)
    prompt_str = apply_chat_template(processor, config, prompt, num_images=0)

    response = generate(
        model,
        processor,
        prompt_str,
        max_tokens=SLM_MAX_TOKENS,
        temperature=SLM_TEMPERATURE,
        verbose=False,
    )

    raw_text = response.text if hasattr(response, "text") else str(response)

    # パターン 2 の場合は削除部分のリストとして処理
    import os
    if os.environ.get("PAKUPAKU_PROMPT") == "2":
        output_text = _apply_deletions(input_text, raw_text)
    else:
        output_text = _parse_slm_output(raw_text)
        # 文末に句点を補う
        if output_text and output_text[-1] not in {"。", "、", "!", "?", "！", "？"}:
            output_text += "。"

    # 古典結果を基準に安全装置を回す:
    # - 文字数比は元発話との比較 (極端な要約・水増しを防止)
    # - 重要語保持は古典結果との比較 (古典が消した語は SLM が消してもOK)
    _verify_safe_output(input_text, output_text, baseline=classic_baseline)
    return tokenize(output_text)


def _apply_deletions(input_text: str, raw_response: str) -> str:
    """パターン 2 用: 削除部分を input_text から取り除く"""
    # 「削除:」以降を抽出
    text = raw_response.strip()
    for prefix in ("削除:", "削除:", "削除 :"):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    # 改行で切る
    if "\n" in text:
        text = text.split("\n", 1)[0].strip()

    # 「なし」なら何もしない
    if text in ("なし", "無し", "none", "None", ""):
        result = input_text
    else:
        # カンマ区切りで削除文字列を取得
        deletions = [d.strip().strip("「」『』\"' ") for d in text.split(",")]
        deletions = [d for d in deletions if d and d in input_text]
        # 長いものから削除 (短いものが先に消えると長い方がマッチしなくなるため)
        deletions.sort(key=len, reverse=True)
        result = input_text
        for d in deletions:
            result = result.replace(d, "", 1)

    # 連続読点を 1 つに
    while "、、" in result:
        result = result.replace("、、", "、")
    # 行頭読点を除去
    while result and result[0] in "、 ":
        result = result[1:]
    # 文末に句点
    if result and result[-1] not in {"。", "、", "!", "?", "！", "？"}:
        result += "。"
    return result


def _verify_safe_output(
    input_text: str, output_text: str, baseline: str | None = None
) -> None:
    """SLM 出力が安全な範囲か検証する

    Args:
        input_text: SLM に渡した元発話
        output_text: SLM が返した出力
        baseline: 重要語保持の比較基準 (デフォルトは input_text)
                  古典 NLP が言い直しの古い側を消した結果を渡すと、
                  「古典が消した語は SLM が消しても OK」と判定できる。

    以下のいずれかに該当すれば SLMUnsafeOutput を送出:
    - 出力が空
    - 文字数が input_text の 40% 未満 (削りすぎ)
    - 文字数が input_text の 150% 超 (水増し・補完)
    - baseline に存在する数値・英字が output_text で消失 (固有値の改変)
    """
    if not output_text.strip():
        raise SLMUnsafeOutput("empty output")

    in_len = len(input_text)
    out_len = len(output_text)
    if in_len > 0:
        ratio = out_len / in_len
        if ratio < _MIN_LENGTH_RATIO:
            raise SLMUnsafeOutput(f"output too short (ratio={ratio:.2f})")
        if ratio > _MAX_LENGTH_RATIO:
            raise SLMUnsafeOutput(f"output too long (ratio={ratio:.2f})")

    # 重要語 (英数字) 保持チェック: baseline (古典結果) を基準にする
    compare_against = baseline if baseline is not None else input_text
    baseline_alnum = _extract_alnum_tokens(compare_against)
    out_alnum = _extract_alnum_tokens(output_text)
    missing = baseline_alnum - out_alnum
    if missing:
        raise SLMUnsafeOutput(f"important tokens missing: {missing}")


def _extract_alnum_tokens(text: str) -> set[str]:
    """テキストから連続した英数字トークンを抽出して集合で返す"""
    result: set[str] = set()
    current: list[str] = []
    for ch in text:
        if ch.isascii() and (ch.isalnum() or ch == "_"):
            current.append(ch)
        elif ch.isdigit():  # 全角数字も拾う
            current.append(ch)
        else:
            if current:
                result.add("".join(current))
                current = []
    if current:
        result.add("".join(current))
    return result


def _parse_slm_output(raw: str) -> str:
    """SLM 出力からテキスト部分を抽出する

    モデルが付ける各種前置きを除去:
    - 「整形後:」「整形後のテキスト:」「結果:」など
    - Markdown の引用記号 (「」『』" ')
    """
    text = raw.strip()

    # 前置きを除去 (繰り返し: モデルがネストすることがある)
    _PREFIXES = [
        "整形後のテキスト:",
        "整形後のテキスト：",
        "整形後:",
        "整形後:",
        "整形後 :",
        "結果:",
        "結果:",
        "出力:",
        "出力:",
        "出力 :",
        "Output:",
        "Result:",
        "# 出力",
        "# 整形後",
    ]
    for _ in range(5):
        original = text
        for prefix in _PREFIXES:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                break
        if text == original:
            break

    # 改行で切る (1 行のみ採用)
    if "\n" in text:
        text = text.split("\n", 1)[0].strip()

    # 終端の余分な記号
    text = text.strip("「」『』\"' \t")

    # Gemma 系の特殊トークンを除去
    for token in ("<end_of_turn>", "<eos>", "<pad>", "<bos>", "<start_of_turn>"):
        text = text.replace(token, "")

    return text.strip()
