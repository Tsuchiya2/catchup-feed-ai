# catchup-feed-ai (pulse-ai)

pulse Phase 2 の Python 実装。M3 Mac 上で夜間バッチ(launchd)として動く。

役割(詳細は `CLAUDE.md` と親リポジトリの `docs/pulse-phase2-design.md` §5–§7):

1. **transcribe worker**(`src/pulse_transcribe/`): Pi の Postgres の `jobs` テーブル
   (kind='transcribe')を poll し、YouTube / ポッドキャストを文字起こしして
   `articles.content` に保存する。以降は backend の既存要約連鎖が処理する
2. **書籍 PDF RAG 取り込み**(`src/pulse_books/`): DRM フリー PDF → テキスト抽出(pypdf)
   → チャンク化 → embedding(Ollama bge-m3、ローカル限定 C-12)→ Pi の pgvector
   (`books` / `book_chunks`)

## transcribe worker

```
jobs poll(SKIP LOCKED claim、意味論は backend internal/jobs が正)
 ├─ youtube:  字幕取得(公式→自動生成)→ 取れなければ yt-dlp 音声 + faster-whisper
 └─ podcast:  enclosure ダウンロード + faster-whisper
 → articles.content に UPDATE → MarkDone(失敗は attempts 上限3で failed)
```

- モデルは faster-whisper **large-v3-turbo**(D-11)。初回実行時に自動ダウンロード(無料)
- **D-14**: 1回の実行で文字起こしする音源は合計2時間まで。残予算に収まらないジョブは
  **attempts を消費せず** pending に戻し(claim 分の加算を巻き戻す)、その夜は以降
  claim せず正常終了(翌夜は先頭からフル予算で処理)。単体で2時間を超える長尺は
  足切りで failed(§5.3)
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

## 書籍 RAG 取り込み(pulse-books)

夜間バッチではなく、書籍を買ったときに Mac 上で手動実行する。

```sh
uv run pulse-books ingest ~/books/learning-go.pdf --title "Learning Go"
uv run pulse-books search "goroutine とチャネルの違い" --top-k 5
```

- 同じ PDF の再取り込みは既存 book の置き換え(chunks 削除→再投入。冪等)
- embedding は Ollama の **bge-m3**(D-12、1024次元)。次元が違うモデルを
  誤設定した場合は書き込み前に即エラー(`book_chunks` は `vector(1024)`)
- `books` / `book_chunks` テーブルの作成は **backend のマイグレーションの責務**。
  未適用ならその旨のエラーで止まる
- `search` は取り込みの動作確認用。壁打ち UI(Open WebUI)との接続は次タスクで、
  同じ SQL(`pulse_books.db.SEARCH_SQL`)を再利用する
- C-12: 書籍データとその embedding は Mac / Pi(Tailscale)の外に出ない。
  クラウド API 呼び出しはゼロ

環境変数は transcribe worker と共通の `.env`(`DATABASE_URL` 共用、
`OLLAMA_HOST` / `EMBEDDING_MODEL` は既定値あり。詳細は `.env.example`)。

## 開発

パッケージ管理は [uv](https://docs.astral.sh/uv/)。

```sh
make dev     # uv sync --all-extras
make test    # pytest
make lint    # ruff + mypy(strict)
make format  # ruff format
```

テストは DB・ネットワーク・Whisper モデル・Ollama をモックした単体テストが基本
(テスト用 PDF は pypdf でテスト内生成)。実 Postgres での検証
(`tests/test_db_integration.py` / `tests/test_books_db_integration.py`)は backend と
同じ流儀で `TEST_DATABASE_URL` 設定時のみ実行される(専用スキーマを作るため開発用 DB を
指してよい。書籍 RAG 側は pgvector 拡張が必要 — `pgvector/pgvector:pg18` コンテナ推奨)。

旧 catchup-ai(Cloud Run 上の gRPC AI サービス)のコードは Phase 2 の減量で削除済み。
経緯は親リポジトリの `docs/ai-inventory.md` を、必要なら git 履歴を参照。
