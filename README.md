# pakupaku

Mac のどこでも **`Ctrl + Shift + Space`** で日本語を音声入力できるツール。録音 → Whisper で文字起こし → フィラーや言い直しを自動で整形 → カーソル位置に貼り付け、までをすべてローカルで完結します。外部 API は一切使いません。

## 動作環境

- **macOS Sonoma 以降を推奨** (Apple Silicon 専用、M1 以降)
- Python 3.12 (uv が管理)
- 依存ツール: Homebrew, Hammerspoon, ffmpeg, Xcode Command Line Tools (`xcode-select --install`)
- ディスク: 約 5GB (Whisper 1.6GB + Gemma 3.4GB のモデルキャッシュ)
- **メモリ: 約 5〜6GB を常時占有** (Whisper + SLM をロードしっぱなしにする設計。詳細は [常時メモリを消費します](#常時メモリを消費します) を参照)

## 使い方 (UX)

1. 入力したい場面で **`Ctrl + Shift + Space`** を押す
2. 録音開始音 + 「録音中」通知
3. 話す (短文〜30 分連続まで対応)
4. もう一度 **`Ctrl + Shift + Space`** を押す
5. 数秒で、フォーカス中のテキスト欄に整形済みテキストが貼り付く

### 起動について (手動操作は不要)

セットアップ後は、**Mac を起動した時点で自動的に使える状態**になります。手動でアプリを起動する必要はありません。

- daemon 本体は launchd に登録され、Mac 起動時に自動起動
- Hammerspoon (ホットキー検知) はセットアップ時に「Launch Hammerspoon at login」を有効化することで自動起動 (詳細はセットアップ手順 4 を参照)
- いずれも常にバックグラウンドで動いており、`Ctrl + Shift + Space` を押すだけで録音が始まります

動いているか確認したい場合:

```bash
paku status        # daemon・Hammerspoon・モデルロード状態をまとめて表示
```

その他の保守用コマンド:

```bash
paku start     # daemon を起動
paku stop      # daemon を停止 (メモリを解放したいとき)
paku restart   # daemon を再起動
paku slm-off   # SLM を無効化してメモリ約 3.4GB を節約
paku slm-on    # SLM を有効化 (通常モードに戻す)
```

うまく動かないときは [トラブルシューティング](#トラブルシューティング) を参照。

### 常時メモリを消費します

pakupaku は使用していない時間も**常に約 5〜6GB のメモリを占有します** (Whisper 音声認識モデル + SLM 言語モデルが常駐)。これは起動のたびにモデルをロードすると数秒〜十数秒かかってしまうため、初回ロード後はメモリ上に保持し続ける設計になっているからです (`paku status` の `memory` 行で実測値を確認できます)。

- メモリに余裕のある Mac (16GB 以上推奨) で使うことを想定しています
- 一時的に使わない・他の作業に全メモリを割きたい場合は `paku stop` で daemon を停止できます (再開は `paku start`)
- **SLM だけ切ってメモリを節約 (約 3.4GB 削減)**: `paku slm-off` (戻すには `paku slm-on`)
  - SLM オフ時は古典 NLP のみで動作。フィラー除去・基本的な句読点整形は機能しますが、複雑な言い直し (「14時から、いや15時から」など) は救済されません
  - 設定は plist に永続化されるので Mac 再起動後も維持されます
- 完全に使わなくなった場合は `bash uninstall.sh` でアンインストールしてください

### プライバシー (ログに発話内容が残ります)

daemon のログ `~/Library/Logs/pakupaku/daemon.log` には、デバッグ用に**音声認識結果と整形後テキストの先頭 80 文字が平文で記録されます**。すべての処理はローカルで完結し外部送信はありませんが、Time Machine バックアップやクラウド同期の対象になっている場合は注意してください。

発話内容を記録したくない場合は、ログレベルを WARNING 以上に上げてください:

```bash
launchctl setenv PAKUPAKU_LOG_LEVEL WARNING
paku restart
```

(`launchctl setenv` した値は launchd 配下のプロセスに引き継がれます。Mac 再起動で消えるので、永続化したい場合は `~/Library/LaunchAgents/com.pakupaku.daemon.plist` の `EnvironmentVariables` に追加してください)

## セットアップ (5〜10 分)

### 前提条件

[Homebrew](https://brew.sh/) がインストール済みであること。なければ:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 1. インストール

任意の場所に pakupaku を配置して、`setup.sh` を実行します:

```bash
git clone https://github.com/Kaito-Tsuruishi/pakupaku.git ~/pakupaku
cd ~/pakupaku
bash setup.sh
```

`setup.sh` が以下を自動で行います:

- uv のインストール (なければ)
- Hammerspoon と ffmpeg のインストール (なければ)
- Python 依存パッケージのインストール (uv sync)
- GiNZA 互換パッチ適用
- Hammerspoon 設定の配置 (`~/.hammerspoon/pakupaku.lua`)
- launchd への daemon 登録 (Mac 起動時に自動起動)

完了すると、ターミナルに以降のステップ (権限取得・動作確認・Hammerspoon 起動・テスト) の案内が表示されます。以下の手順と内容は同じです。

### 2. macOS 権限の取得 (5 分の GUI 操作)

```bash
bash scripts/open_permissions.sh
```

このスクリプトが Python パスをクリップボードにコピーした上で、設定画面を順に開きます:

| 権限 | 必要な対象 | 用途 |
|---|---|---|
| アクセシビリティ | Python (venv) と Hammerspoon | ホットキー検知・自動貼り付け |
| 入力監視 | Hammerspoon | グローバルホットキー |
| マイク | Python (venv) | 録音 (初回録音時にダイアログで許可) |

各画面で:
1. `+` ボタン (アクセシビリティ・入力監視のみ)
2. `⌘+⇧+G` で直接パス入力
3. `⌘+V` で貼り付け、Enter
4. 表示された Python or Hammerspoon を選択 → 開く
5. 追加されたトグルを **オン**

(マイクは事前追加できないバージョンの macOS では、初回録音時にダイアログが出ます)

### 3. 権限の動作確認

```bash
uv run python scripts/check_permissions.py
```

3 つすべて `✓` なら次へ。

### 4. Hammerspoon を起動 + 自動起動を設定

1. Spotlight で「Hammerspoon」検索 → 起動
2. メニューバーアイコン → **Preferences...** → **General** タブ
3. **「Launch Hammerspoon at login」にチェックを入れる** (Mac 起動時に自動起動するため)
4. メニューバーアイコン → **Reload Config**
5. メニューバーアイコン → **Console...** を開き、`pakupaku: hotkey loaded (ctrl+shift+space)` と表示されていれば OK

なお、ステップ 2 (権限付与) を Hammerspoon 起動後にやり直した場合は、**Hammerspoon を一度 Quit → 再起動**してください (Reload Config だけでは権限変更が反映されないことがあります)。

### 5. 初回テスト (モデルダウンロードあり)

任意のテキストエディタを開いて:

1. `Ctrl + Shift + Space` を押す
2. 「えーと、明日の会議に参加します」と話す
3. `Ctrl + Shift + Space` をもう一度押す
4. 数秒後、エディタに「明日の会議に参加します。」が貼り付く

> **初回は時間がかかります**: 最初の `Ctrl + Shift + Space` を押した時点で Hugging Face Hub から **約 5GB のモデル (Whisper + Gemma) のダウンロード**が走ります。回線にもよりますが 5〜15 分程度かかります。`paku status` の `SLM: ✓ loaded` 表示まで待ってから話し始めると確実です。
>
> Gemma は Hugging Face で利用規約への同意 (gated repository) が必要な場合があります。ダウンロードが `401 Unauthorized` で失敗したら、`huggingface-cli login` でアカウント認証 → Hugging Face のモデルページで利用規約に同意 → もう一度試してください。

完了です。

## トラブルシューティング

### ホットキーが効かない

まず `paku status` で全体状況を確認:

```bash
paku status
```

`daemon` / `socket` / `hammerspoon` がすべて緑なら通信路は OK。Hammerspoon の Console (メニューバーアイコン → Console) でエラーを確認してください。

### 録音はされるが貼り付かない

- アクセシビリティ権限を再確認 (Python に対して)
- ターゲットアプリがフォーカスされているか
- 録音停止までにアプリを切り替えていないか (切り替えると誤貼り付け防止のためクリップボードに残置されます。`⌘V` で手動貼り付けできます)
- ログ確認: `tail -50 ~/Library/Logs/pakupaku/daemon.log`

### 通知が出ない

System Settings → Notifications で **Script Editor** (もしくは osascript を実行する経路) の通知を許可してください。

### 権限が突然外れた (Sonoma 以降の不具合)

```bash
tccutil reset Accessibility
tccutil reset Microphone
tccutil reset ListenEvent   # macOS バージョンによっては失敗します (下記参照)
bash scripts/open_permissions.sh
```

`tccutil reset ListenEvent` が失敗する macOS バージョンでは、System Settings → Privacy & Security → Input Monitoring から Hammerspoon を一旦削除して、再度追加してください。

### daemon を再起動

```bash
paku restart
```

### 完全アンインストール

```bash
bash uninstall.sh
```

## CLI コマンド一覧

日常運用は `Ctrl + Shift + Space` (Hammerspoon) で完結します。CLI はセットアップ・保守・デバッグ用です。

| コマンド | 用途 |
|---|---|
| `paku status` | 動作状態を表示 (daemon / Hammerspoon / モデルロード / メモリ) |
| `paku start` | daemon を起動 (停止していた場合) |
| `paku stop` | daemon を停止 (メモリを解放したいとき) |
| `paku restart` | daemon を再起動 |
| `paku slm-off` | SLM を無効化してメモリを約 3.4GB 節約 (古典 NLP のみで動作) |
| `paku slm-on` | SLM を有効化 (通常モードに戻す) |
| `paku text -i "..."` | テキスト整形のみ実行 (デバッグ用) |

`uv sync` 済みなら `paku` がそのまま使えます (`pakupaku` も互換エイリアスとして利用可)。

### テキスト整形だけ試したい

音声入力なしで、テキスト整形のロジックだけ試せます:

```bash
# 古典 NLP のみ (高速、約 24ms)
paku text -i "えーと、明日の会議に参加します" -v

# SLM 込み (古典で取れない言い直しを救済、約 200ms)
paku text -i "明日の、いや明後日の会議" -v --always-slm

# SLM 無効化
paku text -i "..." --no-slm
```

## ファイル構成

```
pakupaku/
├── README.md                       # このファイル
├── LICENSE / NOTICE                # ライセンス情報
├── setup.sh                        # ワンコマンド・セットアップ
├── uninstall.sh                    # クリーンアップ
├── pyproject.toml                  # 依存定義
├── src/pakupaku/                   # 本体ソース (整形パイプライン、daemon、CLI)
├── scripts/
│   ├── install_launchd.sh          # launchd 登録 (setup.sh から呼ばれる)
│   ├── patch_ginza.py              # GiNZA 互換パッチ (setup.sh から呼ばれる)
│   ├── open_permissions.sh         # macOS 権限設定画面を開く (手動実行)
│   ├── check_permissions.py        # 権限の動作確認 (手動実行)
│   ├── com.pakupaku.daemon.plist   # launchd plist テンプレート
│   └── hammerspoon/pakupaku.lua    # Hammerspoon ホットキー設定
├── data/dictionaries/              # フィラー辞書、言い直しマーカー、専門用語辞書
└── tests/                          # ユニットテスト
```

## ライセンス

MIT License (詳細は [LICENSE](LICENSE)、依存ライブラリのライセンスは [NOTICE](NOTICE) を参照)
