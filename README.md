# catchup-feed-ai (pulse-ai)

pulse Phase 2 の Python 実装。M3 Mac 上で夜間バッチ(launchd)として動く。

役割(詳細は `CLAUDE.md` と親リポジトリの `docs/pulse-phase2-design.md` §5–§7):

1. **transcribe worker**(未実装): jobs テーブルを poll し、YouTube / ポッドキャストを
   字幕取得または faster-whisper で文字起こしして `articles.content` に保存する
2. **書籍 PDF RAG 取り込み**(実装中): PDF → テキスト抽出 → チャンク化 → embedding(Ollama)
   → Pi の pgvector。現状は旧実装から移植したチャンカー(`src/pulse_books/chunker.py`)のみ

## 開発

パッケージ管理は [uv](https://docs.astral.sh/uv/)。

```sh
make dev     # uv sync --all-extras
make test    # pytest
make lint    # ruff + mypy
make format  # ruff format
```

旧 catchup-ai(Cloud Run 上の gRPC AI サービス)のコードは Phase 2 の減量で削除済み。
経緯は親リポジトリの `docs/ai-inventory.md` を、必要なら git 履歴を参照。
