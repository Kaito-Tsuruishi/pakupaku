"""パイプライン中間表現のデータクラス定義"""

from dataclasses import dataclass, field


@dataclass
class Token:
    """形態素解析結果の 1 トークン"""

    surface: str
    pos: str
    pos_detail: list[str] = field(default_factory=list)
    reading: str = ""
    is_filler: bool = False
    is_repetition: bool = False


@dataclass
class Sentence:
    """1 発話分の形態素列"""

    tokens: list[Token]
    original_text: str

    def to_text(self) -> str:
        """フィラー・言い直しを除いた表層文字列を返す"""
        return "".join(
            t.surface for t in self.tokens if not t.is_filler and not t.is_repetition
        )

    def visible_tokens(self) -> list[Token]:
        """表示対象のトークン (フィラー・言い直しを除外)"""
        return [t for t in self.tokens if not t.is_filler and not t.is_repetition]


@dataclass
class ProcessingResult:
    """整形処理の結果

    Attributes:
        used_slm: SLM 出力を最終的に採用したか
        slm_invoked: SLM が呼ばれたか (採用されなくても True)
        slm_unsafe: SLM が呼ばれたが安全装置で破棄されたか
    """

    input_text: str
    output_text: str
    intermediate: Sentence
    used_slm: bool
    trigger_reason: str | None
    latency_ms: float
    slm_invoked: bool = False
    slm_unsafe: bool = False
