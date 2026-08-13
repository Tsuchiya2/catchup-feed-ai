# catchup-feed-ai — pulse transcribe worker + 書籍 RAG 取り込み(Phase 2 で解凍)

このリポジトリは pulse Phase 2 の Python 実装を担う。設計の正は親リポジトリの `docs/pulse-phase2-design.md`(特に §5・§6・§7)と `docs/decisions.md`。実装がこれらと食い違う場合は実装が間違っている。

## 役割(Phase 2。実装は全件完了、運用中)

1. **transcribe worker**(`src/pulse_transcribe/`、CLI `pulse-transcribe`): Pi の Postgres の `jobs` テーブルを poll する。claim するのは **`kind='transcribe'` と `kind='book_ingest'` の2種だけ**(他 kind は Pi worker の領分)
   - YouTube: 字幕取得(第2段)→ 失敗時 yt-dlp 音声取得 + faster-whisper(第3段)
   - ポッドキャスト: enclosure mp3 ダウンロード + faster-whisper
   - 結果を `articles.content` に保存(以降は backend の既存要約連鎖が処理)
   - `book_ingest`(D-25): ダッシュボードからアップロードされた PDF を Pi の tailnet 専用エンドポイント `GET /private/books/<ファイル名>` から一時取得し、下の 2 と同一のパイプラインで取り込む。**文字起こしより先に全件ドレインし、D-14 の音源予算は適用しない**。`BOOKS_PRIVATE_BASE_URL` 未設定なら claim せず pending のまま(縮退動作)
2. **書籍 RAG 取り込み**(`src/pulse_books/`、CLI `pulse-books`): DRM フリー PDF → PyMuPDF でテキスト抽出 → チャンク化 → embedding(Ollama bge-m3、ローカル限定)→ Pi の pgvector(`books` / `book_chunks`)。同一性キーは `books.file_path`(再取り込みは置き換え=冪等)
3. **Open WebUI 用書籍検索 Tool**(`openwebui/book_search_tool.py`、A-23): 壁打ち中のローカル LLM が `book_chunks` を cosine 検索するための単一ファイル Tool。サンドボックスに貼り付ける都合で `pulse_books` を import できないため SQL・1024次元ガードを複製しており、**一致は `tests/test_openwebui_tool.py` のパリティテストが担保する**(片方だけ直さない)

## 制約(違反はレビューでブロック)

- **ゼロ円**: 有料 API・有料 SaaS 禁止。文字起こしはローカル faster-whisper(モデルは **large-v3-turbo**、D-11)のみ
- **プライバシー分界(C-12)**: 書籍 PDF・その派生データを Mac/Pi の外に出さない。無料クラウド API に流してよいのは公開動画・公開ポッドキャスト由来のデータのみ
- **jobs 契約は backend が正**: status 遷移・attempts・SKIP LOCKED の意味論は backend の `internal/jobs` 実装に従う。Python 側で独自拡張しない
- **内部 RPC なし(C-4)**: プロセス間連携は Postgres 経由のみ。gRPC(proto/)は削除済みで、再導入しない
- **1夜の文字起こし上限は音源合計2時間**(D-14)。超過分は翌夜持ち越し。持ち越しは失敗ではなく **attempts を消費しない**(未着手ジョブを pending に戻す)。単体でフル予算を超える長尺だけ Permanent failed(足切り)
- **動画・音声・PDF の生ファイルは非永続**: 一時ディレクトリで完結し、成功・失敗どちらでも削除
- **このリポジトリは GitHub 公開・AGPL-3.0**(依存の PyMuPDF が AGPL のため)。実 tailnet ホスト名・DSN・API キー・書籍 PDF をコミットしない(過去に実ホスト名の混入をレビューで差し戻した実績あり)。依存追加は AGPL-3.0 と両立するライセンスに限る
- コミットメッセージ・PR に Co-Authored-By 行を付けない

## 実行環境

- ホスト: M3 Mac(夜間バッチ、launchd。radio の 04:30 より前の 03:00 枠)。運用の起動は backend の `deploy/scripts/transcribe-run.sh`(`~/pulse/.env` を読む)が正で、`make run` は開発用ショートカット
- DB 接続: Tailscale 経由で Pi の Postgres(radio と同じ DATABASE_URL 方式)
- Python 3.14(`.python-version` / `requires-python >=3.14`)、パッケージ管理は uv 継続
- 完了条件は `make lint`(ruff + mypy strict、`openwebui/` も同基準)と `make test`。CI(`.github/workflows/ci.yml`)が同じ内容を回す。DB 統合テストは `TEST_DATABASE_URL` 未設定なら graceful skip(書籍側は pgvector 拡張が必要)
- デプロイ手順は `catchup-feed-backend/deploy/ai.md`(D-10 のユーザー要件: 他サービスとの連携方法まで含めて詳細に文書化)を正とする

## 旧コードの扱い(完了済み)

旧 EDAF 期の資産(proto/・cloudbuild.yaml・cloudrun-service.yaml・Dockerfile・旧 docs 等)は棚卸し(親リポジトリ `docs/ai-inventory.md`)に基づき **2026-07-06 に全削除済み**。流用したのは `chunker.py` 1本のみで `src/pulse_books/` に移植した。復元が必要になったら git 履歴を参照する。コンセプトは継承、コードは選別。
