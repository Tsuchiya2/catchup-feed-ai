# catchup-feed-ai — pulse transcribe worker + 書籍 RAG 取り込み(Phase 2 で解凍)

このリポジトリは pulse Phase 2 の Python 実装を担う。設計の正は親リポジトリの `docs/pulse-phase2-design.md`(特に §5・§6・§7)と `docs/decisions.md`。実装がこれらと食い違う場合は実装が間違っている。

## 役割(Phase 2)

1. **transcribe worker**: Pi の Postgres の `jobs` テーブル(kind='transcribe')を poll し、
   - YouTube: 字幕取得(第2段)→ 失敗時 yt-dlp 音声取得 + faster-whisper(第3段)
   - ポッドキャスト: enclosure mp3 ダウンロード + faster-whisper
   - 結果を `articles.content` に保存(以降は backend の既存要約連鎖が処理)
2. **書籍 RAG 取り込み**: DRM フリー PDF → テキスト抽出 → チャンク化 → embedding(Ollama、ローカル限定)→ Pi の pgvector(`books` / `book_chunks`)

## 制約(違反はレビューでブロック)

- **ゼロ円**: 有料 API・有料 SaaS 禁止。文字起こしはローカル faster-whisper(モデルは **large-v3-turbo**、D-11)のみ
- **プライバシー分界(C-12)**: 書籍 PDF・その派生データを Mac/Pi の外に出さない。無料クラウド API に流してよいのは公開動画・公開ポッドキャスト由来のデータのみ
- **jobs 契約は backend が正**: status 遷移・attempts・SKIP LOCKED の意味論は backend の `internal/jobs` 実装に従う。Python 側で独自拡張しない
- **内部 RPC なし(C-4)**: プロセス間連携は Postgres 経由のみ。gRPC(proto/)は廃止方針
- **1夜の文字起こし上限は音源合計2時間**(D-14)。超過分は翌夜持ち越し
- **動画・音声の生ファイルは非永続**: 一時ディレクトリで完結し、文字起こし成功後に削除
- コミットメッセージ・PR に Co-Authored-By 行を付けない

## 実行環境

- ホスト: M3 Mac(夜間バッチ、launchd。radio の 04:30 より前の 03:00 枠)
- DB 接続: Tailscale 経由で Pi の Postgres(radio と同じ DATABASE_URL 方式)
- パッケージ管理: uv 継続
- デプロイ手順は `catchup-feed-backend/deploy/ai.md`(D-10 のユーザー要件: 他サービスとの連携方法まで含めて詳細に文書化)を正とする

## 旧コードの扱い

旧 EDAF 期の資産(proto/・cloudbuild.yaml・cloudrun-service.yaml・deploy_task.md 等)は棚卸し(親リポジトリ docs/ai-inventory.md)に基づき削除・選別する。コンセプトは継承、コードは選別。
