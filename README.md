# catchup-feed-ai (pulse-ai)

pulse Phase 2 の Python 実装。M3 Mac 上で夜間バッチ(launchd)として動く。

役割(詳細は `CLAUDE.md` と親リポジトリの `docs/pulse-phase2-design.md` §5–§7):

1. **transcribe worker**(`src/pulse_transcribe/`): Pi の Postgres の `jobs` テーブル
   (kind='transcribe')を poll し、YouTube / ポッドキャストを文字起こしして
   `articles.content` に保存する。以降は backend の既存要約連鎖が処理する
2. **書籍 PDF RAG 取り込み**(`src/pulse_books/`): DRM フリー PDF → テキスト抽出(PyMuPDF)
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

**運用・手動検証の正は deploy 資材のラッパー**(catchup-feed-backend の `deploy/ai.md` 5章):
`~/pulse/bin/transcribe-run.sh --deadline <近い時刻>` — `~/pulse/.env` を読み込むので
このリポジトリ側に `.env` を置く必要はない。

`make run` は**開発用ショートカット**で、設定はカレントディレクトリの `.env`
(なければ環境変数)から読む。使う場合は先に用意する:

```sh
cp .env.example .env   # DATABASE_URL 等を記入(キー一覧とコメントは .env.example 参照)
make run               # = uv run pulse-transcribe(--deadline 04:15。昼間の実行は翌朝解決に注意)
make run ARGS="--deadline 06:00"
```

注意: 旧 catchup-feed 時代の `.env`(gRPC/OpenAI 系の変数入り)が残っていると
それが読まれて `database_url Field required` で落ちる。心当たりがあれば退避・削除する。

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

- テキスト抽出は **PyMuPDF**。実書籍での検証で pypdf は埋め込みフォントの
  CID→Unicode を解決できず日本語書籍の 80〜98% のページが文字化けしたため全面切替。
  **PyMuPDF は AGPL-3.0** — pulse は個人利用・非配布のため許容(親裁定。
  再配布・サービス化する場合は要再検討)
- 暗号化 PDF の扱い(C-15 の精緻化): まず**空パスワードで復号を試み、開けたら取り込む**。
  市販の DRM フリー PDF にはオーナーパスワードのみの暗号化(閲覧は自由)が多く、
  これは正当な対象。実パスワードが必要な PDF(実質 DRM)のみ C-15 で拒否する
- 抽出品質のヒューリスティクス警告: 日本語書籍なのに CJK 比率が異常に低い/
  置換不能文字が多いページは「garbled」として warning ログに出る。取り込み時に
  操作者が抽出品質の劣化に気づくための仕組みで、エラーにはしない
- 同じ PDF の再取り込みは既存 book の置き換え(chunks 削除→再投入。冪等)。
  同一性キーは **PDF の絶対パス**(`books.file_path`)なので、同じ本をコピー・
  リネームした別パスから取り込むと別 book として重複する点に注意
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

## Open WebUI への Tool 登録手順(書籍壁打ち、A-23)

壁打ち中の LLM(gemma4:12b)が `book_chunks` を検索できるようにする Open WebUI Tool が
`openwebui/book_search_tool.py`。単一ファイル自己完結(Open WebUI のサンドボックスに
貼り付けるため `pulse_books` を import できない)で、SQL・1024次元ガードは
`pulse_books.db.SEARCH_SQL` / `pulse_books.embedding` と同じ意味論を複製している
(一致は `tests/test_openwebui_tool.py` のパリティテストが担保)。

前提: Open WebUI が Mac の Docker で稼働し(コンテナから見て Ollama は
`host.docker.internal:11434`)、Mac の Tailscale 経由で Pi の Postgres に到達できること。
Docker Desktop はコンテナの外向き通信をホストのネットワークスタック経由で出すため、
macOS の userspace Tailscale でも**追加設定なしで** Pi の tailnet アドレス
(`<Pi名>.<tailnet>.ts.net:5433` — `~/pulse/.env` の `DATABASE_URL` と同じ接続先)に
届く(実機確認済み。ポートフォワードや `--add-host` は不要)。

1. **Tool 登録**: 管理者でログイン → Workspace → Tools → `+`(New Tool)→
   `openwebui/book_search_tool.py` の内容を丸ごと貼り付けて Save。
   フロントマターの `requirements: psycopg[binary]>=3.2` により保存時に依存が
   自動インストールされる(公式イメージには psycopg 同梱済みなので実質即時)
2. **Valves 設定**: Tools 一覧の該当 Tool の歯車アイコン(Valves)を開き、
   - `DATABASE_URL`: Mac の `~/pulse/.env` の `DATABASE_URL` と同じ値(**必須**)
   - `OLLAMA_HOST`: 既定 `http://host.docker.internal:11434` のままでよい
   - `EMBEDDING_MODEL`: 既定 `bge-m3`(D-12。変更は全書籍の再取り込みを伴う)
   - `TOP_K`: 既定 5
3. **モデルへの有効化**: チャット画面の入力欄の `+` → Tools で有効化するか、
   Admin Panel → Settings → Models → gemma4:12b の編集画面で Tools に
   このツールをチェックして常時有効にする
4. **動作確認**: gemma4:12b とのチャットで「リーダブルコードでは変数の命名について
   何と言っている?」のような質問を投げ、Tool 呼び出し(`search_books`)が走って
   書名つきの回答が返ることを確認する。REST API(`POST /api/chat/completions`)で
   確認する場合は `"params": {"function_calling": "legacy"}` を付ける
   (Open WebUI 0.10.x の既定は native で、セッションのない API 呼び出しでは
   tool_calls がクライアントに返されるだけになる。UI チャットはどちらでも動く)

C-12: この Tool の通信先は Ollama(Mac ローカル)と Pi の Postgres(Tailscale)のみ。
書籍データ・クエリはクラウドに出ない。embedding モデルは書籍取り込み側と同一の
bge-m3 でなければ検索が成立しない点に注意。

## 開発

パッケージ管理は [uv](https://docs.astral.sh/uv/)。

```sh
make dev     # uv sync --all-extras
make test    # pytest
make lint    # ruff + mypy(strict)
make format  # ruff format
```

テストは DB・ネットワーク・Whisper モデル・Ollama をモックした単体テストが基本
(テスト用 PDF は pymupdf でテスト内生成。暗号化ケースも合成 PDF で再現)。実 Postgres での検証
(`tests/test_db_integration.py` / `tests/test_books_db_integration.py`)は backend と
同じ流儀で `TEST_DATABASE_URL` 設定時のみ実行される(専用スキーマを作るため開発用 DB を
指してよい。書籍 RAG 側は pgvector 拡張が必要 — `pgvector/pgvector:pg18` コンテナ推奨)。

旧 catchup-ai(Cloud Run 上の gRPC AI サービス)のコードは Phase 2 の減量で削除済み。
経緯は親リポジトリの `docs/ai-inventory.md` を、必要なら git 履歴を参照。
