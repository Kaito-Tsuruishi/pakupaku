"""pakupaku の設定値を集約。

実装中に閾値を調整する場合はここを変更する。
"""

from pathlib import Path

# ===== モデル =====

DEFAULT_SLM_MODEL = "mlx-community/gemma-4-e2b-it-4bit"
DEFAULT_STT_MODEL = "mlx-community/whisper-large-v3-mlx-8bit"

# Whisper の文字起こしヒント (エンジニア向け技術用語を保持)
# 「直前の会話」として Whisper が解釈し、同種の語彙を優先する
DEFAULT_STT_INITIAL_PROMPT = (
    "ソフトウェアエンジニアの会話。"
    "Node.js, TypeScript, JavaScript, Python, Rust, Go, Ruby, Java, "
    "React, Vue.js, Next.js, Nuxt.js, Express, Django, Rails, FastAPI, "
    "Docker, Kubernetes, Terraform, Ansible, "
    "AWS, GCP, Azure, EC2, ECS, Lambda, S3, RDS, BigQuery, "
    "GitHub, GitLab, Slack, Notion, Linear, JIRA, Confluence, Zoom, "
    "PostgreSQL, MySQL, Redis, MongoDB, Elasticsearch, "
    "REST, GraphQL, gRPC, OAuth, JWT, "
    "VSCode, Cursor, Vim, Hammerspoon, "
    "Jest, Vitest, Cypress, Playwright, Pytest, "
    "ESLint, Biome, Prettier, "
    "PR, MR, CI, CD, QA, UAT, SIT, E2E, Pull Request, Issue, Merge Request."
)

# モデルキャッシュ先
CACHE_DIR = Path.home() / ".cache" / "pakupaku"

# プロジェクトルート
PROJECT_ROOT = Path(__file__).parent.parent.parent
ADAPTERS_DIR = PROJECT_ROOT / "adapters"
DATA_DIR = PROJECT_ROOT / "data"
RESOURCES_DIR = PROJECT_ROOT / "resources"

# ===== 音声 =====

SAMPLE_RATE = 16000  # silero-vad の制約に合わせて 16kHz 固定
CHANNELS = 1
DTYPE = "float32"

MIN_RECORDING_SECONDS = 0.3  # 誤タップ判定
MAX_RECORDING_SECONDS = 30 * 60  # 30 分上限

# ===== VAD (Phase 6: バックグラウンド STT) =====

VAD_SPEECH_THRESHOLD = 0.5
VAD_MIN_SPEECH_MS = 250
# 0.8s: 話し続け型発話でもチャンク分割が効くよう短めに設定。
# 言い直し「、いや」程度の言いよどみ (~0.5s) では区切らない閾値ではあるが、
# 1.5s よりはチャンク化されやすい。精度劣化が観測されたら 1500 に戻す。
VAD_MIN_SILENCE_MS = 800

# Whisper のチャンク間文脈引き継ぎ (prompt 引数に渡す直前チャンク末尾の文字数)
STT_PROMPT_CARRYOVER_CHARS = 50

# バックグラウンド STT の VAD 監視間隔 (秒)
BG_STT_VAD_POLL_INTERVAL = 1.0

# 話し続け型発話用の時間ベース強制チャンク化。
# 検証で「Whisper が文途中で切られると、存在しない文を生成・同じ内容をループ生成
# するハルシネーションが起きる」ことが分かったため、デフォルト無効。
# 0 で無効、>0 で N 秒経過したら強制カット (検証用、実用時は推奨しない)。
BG_STT_MAX_CHUNK_SEC = 0.0

# ===== ルーター発火条件 (15〜25% SLM 目標版) =====

ROUTER_CONFIG = {
    # 1. マーカーありで類似度がこの値未満なら SLM
    "similarity_threshold": 0.6,
    # 5. 文長がこれ以上 + 係り受け複雑なら SLM
    "long_sentence_token_count": 60,
    "parse_complexity_threshold": 0.7,
    # グローバル無効化
    "global_enable": True,
}

# ===== SLM =====

SLM_MAX_TOKENS = 200
SLM_TEMPERATURE = 0.3

# プロンプトパターン (環境変数 PAKUPAKU_PROMPT で切り替え可)
# 1: simple - シンプルなルール + 少数例
# 2: extract - 削除部分のみを列挙する方式
# 3: fewshot - 多めの例で帰納学習
# 4: strict  - 「言い直しは絶対前を消す」を強調
import os

_PROMPT_VARIANTS = {
    "1": """日本語の音声認識結果を整形するタスクです。
入力からフィラーと言い直しの古い側を除去し、句読点を整えてください。
それ以外の変更は禁止です。出力は整形後のテキスト 1 行のみ。

# ルール
1. 入力にない語を追加しない
2. 入力の語の置換・要約・敬語化をしない
3. 数字・英字・固有名詞はそのまま保持
4. 「すみません」「ちょっと」「ね」「よ」など意味のある語は残す
5. 連体詞「あの」「その」「この」は残す

# 例
入力: えーと、明日の会議に参加できますね
出力: 明日の会議に参加できますね。

入力: 14時から、あ、15時から会議です
出力: 15時から会議です。

入力: テストはJestで、いやVitestで書いてます
出力: テストはVitestで書いてます。

入力: あの、すみません、明日の会議は中止です
出力: あの、すみません、明日の会議は中止です。

入力: {input}
出力:""",

    "2": """日本語の音声認識結果から、削除すべきフィラー・言い直しの古い側を抽出してください。
削除すべきものがない場合は「なし」とだけ答えてください。
追加・改変は禁止。出力は削除する文字列のリストのみ (カンマ区切り、1 行)。

# 削除対象
- フィラー: えーと、まぁ、うーん、あー
- 言い直しの古い側: 「Aから、いやBから」のとき「Aから」

# 例
入力: えーと、明日の会議に参加できますね
削除: えーと、

入力: 14時から、あ、15時から会議です
削除: 14時から、あ、

入力: テストはJestで、いやVitestで書いてます
削除: Jestで、いや

入力: あの、すみません、明日の会議は中止です
削除: なし

入力: {input}
削除:""",

    "3": """日本語の音声認識結果を整形します。フィラーと言い直しの古い側を除去し、句読点を整えてください。
入力にない語の追加・置換・要約は厳禁です。出力は整形後のテキスト 1 行のみ。

# 削除するもの
- フィラー: 「えーと」「えーっと」「あのー」「まぁ」「うーん」など発話の埋め草
- 言い直しの古い側: 「Aから、いやBから」「A、あ、B」のような訂正表現の前側

# 残すもの (削除してはいけない)
- 「〜なんですけど」「〜なんですが」「〜の件で」のような主題提示・話題導入
- 「ありがとう」「すみません」「ちょっと」「ね」「よ」など意味のある語
- 数字・英字・固有名詞
- 「じゃなくて」「ではなく」は対比表現なので両側を残す

# 例
入力: えーと、明日の会議に参加できますね
出力: 明日の会議に参加できますね。

入力: テストはJestで、いやVitestで書いてます
出力: テストはVitestで書いてます。

入力: Cypressじゃなくて、Playwrightにします
出力: Cypressじゃなくて、Playwrightにします。

入力: {input}
出力:""",

    "4": """日本語の音声認識結果を整形してください。

# 重要なルール
- 「いや」「あ、」のあとに同じ意味の言い直しがある場合、**前側を必ず削除**してください
- 「じゃなくて」は削除しないでください (これは対比表現で、両方残す意味があります)
- フィラー (えーと、まぁ、うーん) は削除してください
- 「ありがとう」「すみません」「ちょっと」「ね」「よ」などは削除しないでください
- 入力にない語を追加してはいけません
- 数字・英字・固有名詞は変えないでください
- 文末に「。」を補ってください

# 言い直しの例 (前側を削除する)
入力: 14時から、あ、15時から会議です
出力: 15時から会議です。

入力: テストはJestで、いやVitestで書いてます
出力: テストはVitestで書いてます。

入力: 監視メトリクスにも、ステージング、いや、preprodで再現できるようにしときます
出力: 監視メトリクスにも、preprodで再現できるようにしときます。

# 対比の例 (両方残す)
入力: Cypressじゃなくて、Playwrightにします
出力: Cypressじゃなくて、Playwrightにします。

# フィラーのみの例
入力: えーと、明日の会議に参加できますね
出力: 明日の会議に参加できますね。

入力: あの、すみません、明日の会議は中止です
出力: あの、すみません、明日の会議は中止です。

# 整形対象
入力: {input}
出力:""",
}

# P3 (多 Few-shot) が最良の評価結果 (eval_meetings_v2 で 90%)
# 元発話 (original_text) を渡す前提
_PROMPT_VARIANT_KEY = os.environ.get("PAKUPAKU_PROMPT", "3")
SLM_PROMPT_TEMPLATE = _PROMPT_VARIANTS.get(_PROMPT_VARIANT_KEY, _PROMPT_VARIANTS["3"])

# ===== IPC =====

SOCKET_PATH = Path.home() / ".pakupaku" / "pakupaku.sock"

# ===== ログ =====

LOG_DIR = Path.home() / "Library" / "Logs" / "pakupaku"

# ===== 辞書ファイル =====

FILLER_DICT_PATH = DATA_DIR / "dictionaries" / "fillers.txt"
REPETITION_MARKERS_PATH = DATA_DIR / "dictionaries" / "repetition_markers.txt"
TECH_TERMS_PATH = DATA_DIR / "dictionaries" / "tech_terms.txt"

# ===== フィードバック =====

START_SOUND_PATH = RESOURCES_DIR / "sounds" / "start.aiff"
STOP_SOUND_PATH = RESOURCES_DIR / "sounds" / "stop.aiff"

# システム同梱音への fallback (リソースファイルが無い場合)
FALLBACK_START_SOUND = "/System/Library/Sounds/Tink.aiff"
FALLBACK_STOP_SOUND = "/System/Library/Sounds/Pop.aiff"
