# catchup-feed-ai (pulse-ai)

pulse Phase 2 の Python 実装。M3 Mac 上で夜間バッチ(launchd)として動く。

役割(詳細は `CLAUDE.md` と親リポジトリの `docs/pulse-phase2-design.md` §5–§7):

1. **transcribe worker**(`src/pulse_transcribe/`): Pi の Postgres の `jobs` テーブル
   (kind='transcribe')を poll し、YouTube / ポッドキャストを文字起こしして
   `articles.content` に保存する。以降は backend の既存要約連鎖が処理する
2. **書籍 PDF RAG 取り込み**(実装中): PDF → テキスト抽出 → チャンク化 → embedding(Ollama)
   → Pi の pgvector。現状は旧実装から移植したチャンカー(`src/pulse_books/chunker.py`)のみ

## transcribe worker

```
jobs poll(SKIP LOCKED claim、意味論は backend internal/jobs が正)
 ├─ youtube:  字幕取得(公式→自動生成)→ 取れなければ yt-dlp 音声 + faster-whisper
 └─ podcast:  enclosure ダウンロード + faster-whisper
 → articles.content に UPDATE → MarkDone(失敗は attempts 上限3で failed)
```

- モデルは faster-whisper **large-v3-turbo**(D-11)。初回実行時に自動ダウンロード(無料)
- **D-14**: 1回の実行で文字起こしする音源は合計2時間まで。超過分は翌夜持ち越し
  (メタデータで事前判定できる場合はダウンロード前に翌夜へ回す)
- **実行時間ガード**: `--deadline HH:MM`(既定 04:15)を過ぎたら新規 claim を止めて終了。
  処理途中のジョブは完遂する(radio 04:30 を侵食しない)
- 音声・動画ファイルは一時ディレクトリで完結し、成功・失敗どちらでも削除される

### 実行

```sh
cp .env.example .env   # DATABASE_URL 等を記入(キー一覧とコメントは .env.example 参照)
make run               # = uv run pulse-transcribe(--deadline 04:15)
make run ARGS="--deadline 06:00"
```

環境変数(詳細は `.env.example`):

| 変数 | 既定 | 説明 |
|---|---|---|
| `DATABASE_URL` | (必須) | Pi の PostgreSQL(Tailscale 経由、radio と同じ方式) |
| `WHISPER_MODEL` | `large-v3-turbo` | faster-whisper モデル(D-11) |
| `WHISPER_DEVICE` / `WHISPER_COMPUTE_TYPE` | `auto` / `auto` | CTranslate2 実行設定(CPU 高速化は `int8`) |
| `NIGHTLY_BUDGET_SECONDS` | `7200` | D-14: 1夜の音源合計上限(秒) |
| `POLL_INTERVAL_SECONDS` | `10` | jobs poll 間隔 |
| `LOG_LEVEL` | `INFO` | ログレベル |

## 開発

パッケージ管理は [uv](https://docs.astral.sh/uv/)。

```sh
make dev     # uv sync --all-extras
make test    # pytest
make lint    # ruff + mypy(strict)
make format  # ruff format
```

テストは DB・ネットワーク・Whisper モデルをモックした単体テストが基本。
実 Postgres での jobs 遷移検証(`tests/test_db_integration.py`)は backend と同じ流儀で
`TEST_DATABASE_URL` 設定時のみ実行される(専用スキーマを作るため開発用 DB を指してよい)。

旧 catchup-ai(Cloud Run 上の gRPC AI サービス)のコードは Phase 2 の減量で削除済み。
経緯は親リポジトリの `docs/ai-inventory.md` を、必要なら git 履歴を参照。
