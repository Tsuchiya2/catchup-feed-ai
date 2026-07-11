# catchup-feed-ai (pulse-ai)

**pulse**(旧 catchup-feed の後継)の Python コンポーネント。pulse は「毎朝10〜15分の音声ラジオ番組をポッドキャストアプリに配信する個人向け学習システム」で、最適化目標は配信量ではなく **理解の定着**。

このリポジトリはその **Phase 2(ソース多モーダル化 + 書籍 PDF RAG)** を担い、M3 Mac 上で夜間バッチ(launchd)/ 手動実行として動く。Pi 上の Go backend とは Postgres 経由でのみ連携する(内部 RPC なし)。

設計の正は親リポジトリの `docs/pulse-phase2-design.md`(特に §5–§7)と `docs/decisions.md`。実装がこれらと食い違う場合は実装が間違っている。

## このリポジトリの役割

pulse における ai は 2 つの入力パイプラインを提供する。

1. **transcribe worker**(`src/pulse_transcribe/`)
   Pi の Postgres の `jobs` テーブル(`kind='transcribe'`)を poll し、YouTube / ポッドキャストを **faster-whisper** で文字起こしして `articles.content` に保存する。以降は backend の既存要約連鎖が処理し、毎朝のラジオに記事と同列で合流する。
2. **書籍 PDF RAG 取り込み**(`src/pulse_books/`)
   DRM フリー PDF を **PyMuPDF** でテキスト抽出 → チャンク化 → **Ollama**(bge-m3)で embedding → Pi の pgvector(`books` / `book_chunks`)に保存。スマホから Open WebUI 経由でローカル LLM と壁打ちして書籍を消化する。

### 設計原則(pulse から継承)

- **単一ユーザー右サイズ**: gRPC / Prometheus / マイクロサービス分割などの過剰な基盤は持たない。プロセス間連携は Postgres 経由のみ(C-4)。
- **ゼロ円運用**: 有料 API・有料 SaaS 禁止。文字起こしはローカル faster-whisper のみ。
- **プライバシー分界(C-12)**: 無料クラウド API に流してよいのは公開動画・公開ポッドキャスト由来のデータのみ。**書籍 PDF とその派生データ(テキスト・embedding)は Mac / Pi(Tailscale)の外に出さない**。書籍まわりのクラウド API 呼び出しはゼロ。

## 技術スタック

`pyproject.toml` を正とする。

| 項目 | 内容 |
|---|---|
| 言語 | Python **3.14**(`.python-version` / `requires-python >=3.14`) |
| パッケージ管理 | [uv](https://docs.astral.sh/uv/) |
| 文字起こし | faster-whisper `>=1.2.1`(モデル: large-v3-turbo, D-11) |
| メディア取得 | yt-dlp `>=2026.7.4`(YouTube 字幕 + 音声ダウンロード) |
| DB ドライバ | psycopg[binary] `>=3.3.4`(Pi PostgreSQL / pgvector) |
| PDF 抽出 | PyMuPDF `>=1.28.0`(AGPL-3.0) |
| 設定 | pydantic-settings `>=2.14.2` |
| ロギング | structlog `>=26.1.0` |
| embedding | Ollama(bge-m3, 1024次元, D-12)※外部プロセス |
| Lint / 型 | ruff `>=0.15.21` / mypy `>=2.2.0`(strict) |
| テスト | pytest `>=9.1.1` + pytest-cov |
| CI | GitHub Actions(uv + ruff + mypy strict + pytest) |

## セットアップ

```sh
make dev     # uv sync --all-extras(dev 依存込み)
```

環境変数はプロセス環境変数、またはカレントディレクトリの `.env` から `pydantic-settings` が読み込む(`.env` は gitignore 済み)。

```sh
cp .env.example .env   # DATABASE_URL 等を記入(キー一覧とコメントは .env.example 参照)
```

> 注意: 旧 catchup-feed 時代の `.env`(gRPC/OpenAI 系の変数入り)が残っていると
> それが読まれて `database_url Field required` で落ちる。心当たりがあれば退避・削除する。

## 実行

### transcribe worker

```
jobs poll(SKIP LOCKED claim、意味論は backend internal/jobs が正)
 ├─ youtube:  字幕取得(公式→自動生成)→ 取れなければ yt-dlp 音声 + faster-whisper
 └─ podcast:  enclosure ダウンロード + faster-whisper
 → articles.content に UPDATE → MarkDone(失敗は attempts 上限3で failed)
```

**運用・手動検証の正は deploy 資材のラッパー**(catchup-feed-backend の `deploy/ai.md` 5章):
`~/pulse/bin/transcribe-run.sh --deadline <近い時刻>` — `~/pulse/.env` を読み込むのでこのリポジトリ側に `.env` を置く必要はない。

`make run` は **開発用ショートカット**で、設定はカレントディレクトリの `.env`(なければ環境変数)から読む。

```sh
make run                        # = uv run pulse-transcribe(--deadline 04:15)
make run ARGS="--deadline 06:00"
```

- モデルは faster-whisper **large-v3-turbo**(D-11)。初回実行時に自動ダウンロード(無料)
- **D-14**: 1回の実行で文字起こしする音源は合計2時間まで(`NIGHTLY_BUDGET_SECONDS`)。残予算に収まらないジョブは **attempts を消費せず** pending に戻し、その夜は以降 claim せず正常終了(翌夜は先頭からフル予算で処理)。単体で2時間を超える長尺は足切りで failed(§5.3)
- **実行時間ガード**: `--deadline HH:MM`(既定 04:15)を過ぎたら新規 claim を止めて終了。処理途中のジョブは完遂する(radio 04:30 を侵食しない)
- 音声・動画ファイルは一時ディレクトリで完結し、成功・失敗どちらでも削除される

### 書籍 RAG 取り込み(pulse-books)

夜間バッチではなく、書籍を買ったときに Mac 上で手動実行する。

```sh
uv run pulse-books ingest ~/books/learning-go.pdf --title "Learning Go"
uv run pulse-books search "goroutine とチャネルの違い" --top-k 5
```

- テキスト抽出は **PyMuPDF**。実書籍検証で pypdf は埋め込みフォントの CID→Unicode を解決できず日本語書籍の 80〜98% のページが文字化けしたため全面切替。**PyMuPDF は AGPL-3.0** — pulse は個人利用・非配布のため許容(親裁定。再配布・サービス化する場合は要再検討)
- 暗号化 PDF(C-15 の精緻化): まず空パスワードで復号を試み、開けたら取り込む。市販の DRM フリー PDF に多いオーナーパスワードのみの暗号化(閲覧は自由)は正当な対象。実パスワードが必要な PDF(実質 DRM)のみ拒否
- 抽出品質のヒューリスティクス警告: CJK 比率が異常に低い/置換不能文字が多いページは「garbled」として warning ログに出る(エラーにはしない)
- 同じ PDF の再取り込みは既存 book の置き換え(chunks 削除→再投入。冪等)。同一性キーは **PDF の絶対パス**(`books.file_path`)なので、同じ本を別パスから取り込むと別 book として重複する点に注意
- embedding は Ollama の **bge-m3**(D-12、1024次元)。次元が違うモデルを誤設定した場合は書き込み前に即エラー(`book_chunks` は `vector(1024)`)
- `books` / `book_chunks` テーブルの作成は **backend のマイグレーションの責務**。未適用ならその旨のエラーで止まる
- `search` は取り込みの動作確認用。壁打ち UI(Open WebUI)は同じ SQL(`pulse_books.db.SEARCH_SQL`)を再利用する

## 環境変数

詳細とコメントは `.env.example` が正。

| 変数 | 既定 | 説明 |
|---|---|---|
| `DATABASE_URL` | (必須) | Pi の PostgreSQL(Tailscale 経由、radio と同じ方式) |
| `WHISPER_MODEL` | `large-v3-turbo` | faster-whisper モデル(D-11) |
| `WHISPER_DEVICE` / `WHISPER_COMPUTE_TYPE` | `auto` / `auto` | CTranslate2 実行設定(CPU 高速化は `int8`) |
| `NIGHTLY_BUDGET_SECONDS` | `7200` | D-14: 1夜の音源合計上限(秒) |
| `POLL_INTERVAL_SECONDS` | `10` | jobs poll 間隔 |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama エンドポイント(pulse-books) |
| `EMBEDDING_MODEL` | `bge-m3` | embedding モデル(D-12、1024次元必須) |
| `LOG_LEVEL` | `INFO` | ログレベル |
| `TEST_DATABASE_URL` | (未設定で skip) | 実 Postgres 統合テストのゲート |

`--deadline HH:MM`(既定 04:15)は環境変数ではなく CLI 引数。

## Open WebUI への Tool 登録(書籍壁打ち、A-23)

壁打ち中の LLM が `book_chunks` を検索できるようにする Open WebUI Tool が `openwebui/book_search_tool.py`。単一ファイル自己完結(サンドボックスに貼り付けるため `pulse_books` を import できない)で、SQL・1024次元ガードは `pulse_books.db.SEARCH_SQL` / `pulse_books.embedding` と同じ意味論を複製している(一致は `tests/test_openwebui_tool.py` のパリティテストが担保)。

登録手順・Valves 設定・動作確認の詳細は本ファイル末尾の履歴と `docs/pulse-phase2-design.md` を参照。要点:

1. **Tool 登録**: 管理者でログイン → Workspace → Tools → `+`(New Tool)→ `book_search_tool.py` を丸ごと貼り付けて Save(フロントマターの `requirements: psycopg[binary]>=3.2` により依存が自動インストール)
2. **Valves 設定**: `DATABASE_URL`(必須、Mac の `~/pulse/.env` と同値)/ `OLLAMA_HOST`(既定 `http://host.docker.internal:11434`)/ `EMBEDDING_MODEL`(既定 `bge-m3`)/ `TOP_K`(既定 5)
3. **モデルへの有効化**: チャット入力欄の `+` → Tools、または Admin Panel → Settings → Models で常時有効化
4. **動作確認**: 書籍内容を問う質問で Tool 呼び出し(`search_books`)が走り、書名つき回答が返ることを確認

C-12: この Tool の通信先は Ollama(Mac ローカル)と Pi の Postgres(Tailscale)のみ。書籍データ・クエリはクラウドに出ない。

## 開発

```sh
make dev     # uv sync --all-extras
make test    # pytest -v --cov=src
make lint    # ruff check + mypy(strict)
make format  # ruff check --fix + ruff format
```

テストは DB・ネットワーク・Whisper モデル・Ollama をモックした単体テストが基本(テスト用 PDF は pymupdf でテスト内生成。暗号化ケースも合成 PDF で再現)。実 Postgres での検証(`tests/test_db_integration.py` / `tests/test_books_db_integration.py`)は backend と同じ流儀で `TEST_DATABASE_URL` 設定時のみ実行される(専用スキーマを作るため開発用 DB を指してよい。書籍 RAG 側は pgvector 拡張が必要 — `pgvector/pgvector:pg18` コンテナ推奨)。

CI(`.github/workflows/ci.yml`)は uv で依存を同期し、ruff + mypy(strict)+ pytest を実行する。DB 統合テストは `TEST_DATABASE_URL` 未設定のため CI では graceful skip される。

## ライセンス

本リポジトリは pulse の個人利用・非配布コンポーネントであり、再配布を前提としない。依存の **PyMuPDF は AGPL-3.0** である点に注意(個人利用・非配布のため許容。再配布・サービス化する場合は要再検討)。

旧 catchup-ai(Cloud Run 上の gRPC AI サービス)のコードは Phase 2 の減量で削除済み。経緯は親リポジトリの `docs/ai-inventory.md` を、必要なら git 履歴を参照。
</content>
</invoke>
