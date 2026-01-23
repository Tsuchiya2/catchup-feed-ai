# catchup-feed-backend 実装プラン: Embedding機能対応

> **このドキュメントについて**
>
> catchup-ai（Python AIサービス）からの要求に基づき、catchup-feed-backend側で実装が必要な内容をまとめています。
> backend側でClaude Codeを起動した際に、このファイルを参照してください。

> **前提条件**
>
> - PostgreSQL 18系にアップグレード済み（16→18へのマイグレーション完了）
> - pgvector拡張はPostgreSQL 18に対応済み

---

## 1. 背景・経緯

### 1.1 catchup-feed ecosystem の全体像

```
┌─────────────────────────────────────────────────────────────────┐
│                    catchup-feed ecosystem                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────┐    gRPC    ┌────────────────────────┐    │
│  │ catchup-feed     │◄──────────►│  catchup-ai (Python)   │    │
│  │ -backend (Go)    │            │                        │    │
│  │                  │            │  • Embedding生成       │    │
│  │ • RSS収集        │            │  • 類似検索            │    │
│  │ • 記事保存       │            │  • RAG (将来)          │    │
│  │ • CLI            │            │  • 要約生成 (将来)     │    │
│  └────────┬─────────┘            └───────────┬────────────┘    │
│           │                                   │                 │
│           │         共有データベース          │                 │
│           └──────────────┬────────────────────┘                 │
│                          ▼                                      │
│           ┌──────────────────────────────┐                      │
│           │  PostgreSQL 18 + pgvector    │                      │
│           │                              │                      │
│           │  • articles (既存)           │                      │
│           │  • sources (既存)            │                      │
│           │  • article_embeddings (新規) │ ← 今回追加           │
│           └──────────────────────────────┘                      │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 なぜbackend側で実装するのか

**設計原則: データの所有権はbackendにある**

| 観点 | 説明 |
|------|------|
| 単一の真実の源泉 | 記事関連データはすべてbackendが管理 |
| 責務の分離 | AI側はembedding「生成」、backend側は「永続化」 |
| 整合性の担保 | FK制約、CASCADE削除などをbackendが制御 |
| マイグレーション管理 | スキーマ変更の履歴を一元管理 |

### 1.3 なぜ既存テーブルへのカラム追加ではなく別テーブルか

**将来の拡張性を考慮:**

1. **複数のembeddingモデル対応**
   - OpenAI text-embedding-3-small (1536次元)
   - Voyage voyage-3 (1024次元)
   - 将来のローカルモデル

2. **複数の対象**
   - タイトルのembedding
   - 本文全体のembedding
   - 要約のembedding

3. **バージョニング**
   - モデル更新時の再生成
   - A/Bテスト

```
# カラム追加だと破綻する例:
articles
  + embedding_openai_title vector(1536)
  + embedding_openai_content vector(1536)
  + embedding_voyage_title vector(1024)
  ... # 組み合わせ爆発

# 別テーブルなら柔軟:
article_embeddings
  - article_id
  - embedding_type ('title', 'content')
  - provider ('openai', 'voyage')
  - model ('text-embedding-3-small')
  - embedding vector(...)
```

---

## 2. 実現したいこと

### 2.1 機能要件

1. **記事のembeddingを保存できる**
   - 1つの記事に対して複数のembeddingを持てる
   - モデル、タイプ（タイトル/本文）で区別可能

2. **類似記事を検索できる**
   - ベクトルの類似度（コサイン類似度）で検索
   - pgvectorのインデックスで高速化

3. **記事削除時にembeddingも削除される**
   - 外部キー制約 + ON DELETE CASCADE

### 2.2 非機能要件

1. **パフォーマンス**
   - 10万件規模の記事でも実用的な検索速度
   - IVFFlatインデックスで近似最近傍探索

2. **拡張性**
   - 新しいembeddingモデルを追加しやすい構造
   - 次元数の異なるモデルにも対応可能

---

## 3. 期待している挙動

### 3.1 データフロー

```
[記事作成時]
1. backend: 新しい記事をarticlesテーブルに保存
2. (将来) backend → catchup-ai: 新規記事の通知（gRPC or イベント）
3. catchup-ai: OpenAI APIでembedding生成
4. catchup-ai: article_embeddingsテーブルに保存

[類似検索時]
1. catchup-ai: クエリテキストをembeddingに変換
2. catchup-ai: article_embeddingsでベクトル検索
3. catchup-ai: 上位N件のarticle_idを取得
4. catchup-ai: articlesテーブルから詳細を取得（JOINまたは別クエリ）

[記事削除時]
1. backend: articlesテーブルから記事を削除
2. (自動) ON DELETE CASCADEでembeddingsも削除
```

### 3.2 テーブル関係

```
articles (既存)              article_embeddings (新規)
┌──────────────────┐         ┌──────────────────────────────┐
│ id (PK)          │◄────────│ article_id (FK)              │
│ source_id        │         │ id (PK)                      │
│ title            │         │ embedding_type               │
│ url              │         │ provider                     │
│ summary          │         │ model                        │
│ published_at     │         │ dimension                    │
│ created_at       │         │ embedding                    │
└──────────────────┘         │ created_at                   │
                             │ updated_at                   │
                             └──────────────────────────────┘
```

---

## 4. backend側で実装が必要なこと

### 4.1 マイグレーション（必須）

#### Migration 1: pgvector拡張の有効化

```sql
-- Up
CREATE EXTENSION IF NOT EXISTS vector;

-- Down
DROP EXTENSION IF EXISTS vector;
```

**注意点:**
- PostgreSQL 18 + pgvector拡張が必要
- 本番環境では事前にpgvector拡張をインストールしておく必要あり
- Docker: `pgvector/pgvector:pg18` イメージを使用
- PostgreSQL 18では並列クエリの改善により、大規模なベクトル検索のパフォーマンスが向上

#### Migration 2: article_embeddingsテーブル作成

```sql
-- Up
CREATE TABLE IF NOT EXISTS article_embeddings (
    id              SERIAL PRIMARY KEY,
    article_id      BIGINT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    embedding_type  VARCHAR(50) NOT NULL,   -- 'title', 'content', 'summary'
    provider        VARCHAR(50) NOT NULL,   -- 'openai', 'voyage'
    model           VARCHAR(100) NOT NULL,  -- 'text-embedding-3-small', 'voyage-3'
    dimension       INT NOT NULL,           -- 1536, 1024, etc.
    embedding       vector(1536) NOT NULL,  -- ベクトルデータ（初期は1536次元固定）
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- 同一記事・同一タイプ・同一モデルの組み合わせは一意
    UNIQUE(article_id, embedding_type, provider, model)
);

-- インデックス
CREATE INDEX idx_article_embeddings_article_id ON article_embeddings(article_id);

-- ベクトル検索用インデックス（IVFFlat）
-- 注意: データが入った後に作成する方が効率的
-- lists の値は sqrt(総レコード数) が目安
CREATE INDEX idx_article_embeddings_vector ON article_embeddings
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Down
DROP TABLE IF EXISTS article_embeddings;
```

**ベクトル次元数について:**
- 初期実装では `vector(1536)` （OpenAI text-embedding-3-small）で固定
- 異なる次元数のモデルを使う場合は、マイグレーションで対応
- 将来的に複数次元をサポートする場合は、テーブル分割を検討

### 4.2 Goモデル定義（推奨）

```go
// internal/domain/entity/article_embedding.go

package entity

import "time"

// EmbeddingType represents the type of content that was embedded
type EmbeddingType string

const (
    EmbeddingTypeTitle   EmbeddingType = "title"
    EmbeddingTypeContent EmbeddingType = "content"
    EmbeddingTypeSummary EmbeddingType = "summary"
)

// EmbeddingProvider represents the embedding service provider
type EmbeddingProvider string

const (
    EmbeddingProviderOpenAI EmbeddingProvider = "openai"
    EmbeddingProviderVoyage EmbeddingProvider = "voyage"
)

// ArticleEmbedding represents a vector embedding for an article
type ArticleEmbedding struct {
    ID            int64
    ArticleID     int64
    EmbeddingType EmbeddingType
    Provider      EmbeddingProvider
    Model         string
    Dimension     int
    Embedding     []float32  // pgvectorはfloat32
    CreatedAt     time.Time
    UpdatedAt     time.Time
}
```

### 4.3 リポジトリ実装（推奨）

```go
// internal/domain/repository/article_embedding_repository.go

package repository

import "context"

type ArticleEmbeddingRepository interface {
    // 保存（INSERT or UPDATE）
    Upsert(ctx context.Context, embedding *entity.ArticleEmbedding) error

    // 取得
    FindByArticleID(ctx context.Context, articleID int64) ([]*entity.ArticleEmbedding, error)

    // 類似検索（オプション - catchup-ai側で直接SQLを実行してもよい）
    SearchSimilar(ctx context.Context, queryVector []float32, limit int) ([]*entity.ArticleEmbedding, error)

    // 削除（CASCADE削除があるため、通常は使用しない）
    DeleteByArticleID(ctx context.Context, articleID int64) error
}
```

### 4.4 gRPCエンドポイント（オプション）

catchup-aiがembeddingを保存するためのエンドポイント。
直接DBアクセスを許可する場合は不要。

```protobuf
// proto/embedding.proto

service EmbeddingService {
    // Embeddingを保存
    rpc StoreEmbedding(StoreEmbeddingRequest) returns (StoreEmbeddingResponse);

    // 記事のEmbeddingを取得
    rpc GetEmbeddings(GetEmbeddingsRequest) returns (GetEmbeddingsResponse);
}

message StoreEmbeddingRequest {
    int64 article_id = 1;
    string embedding_type = 2;  // 'title', 'content', 'summary'
    string provider = 3;        // 'openai', 'voyage'
    string model = 4;           // 'text-embedding-3-small'
    int32 dimension = 5;
    repeated float embedding = 6;
}

message StoreEmbeddingResponse {
    bool success = 1;
    string error_message = 2;
}
```

---

## 5. 実装の優先順位

### Phase 1: 最小構成（必須）

1. ✅ pgvector拡張のマイグレーション
2. ✅ article_embeddingsテーブルのマイグレーション
3. ✅ IVFFlatインデックスの作成

これだけあれば、catchup-ai側から直接SQLでembeddingを保存・検索できます。

### Phase 2: Go側の整備（推奨）

4. ArticleEmbedding エンティティ定義
5. ArticleEmbeddingRepository インターフェース定義
6. PostgreSQLリポジトリ実装

### Phase 3: API整備（オプション）

7. gRPCエンドポイント（StoreEmbedding, GetEmbeddings）
8. CLIコマンド拡張（embedding関連の操作）

---

## 6. 本番環境への適用

### 6.1 前提条件

- PostgreSQL 18（アップグレード済み）
- pgvector拡張がインストール済み
  - AWS RDS: `CREATE EXTENSION vector;` が実行可能（PostgreSQL 18対応済み）
  - Cloud SQL: pgvector拡張を有効化
  - Self-hosted: `apt install postgresql-18-pgvector` 等
  - Docker: `pgvector/pgvector:pg18` イメージを使用

### 6.2 マイグレーション実行

```bash
# 開発環境
go run cmd/migrate/main.go up

# 本番環境（CI/CDパイプラインで実行）
./migrate -database "$DATABASE_URL" up
```

### 6.3 既存記事のbackfill

マイグレーション完了後、既存記事にembeddingを生成するバッチ処理が必要です。
これはcatchup-ai側で実装予定：

```bash
# catchup-ai側で実行（将来実装）
uv run python -m catchup_ai.scripts.backfill_embeddings --batch-size 100
```

---

## 7. 参考情報

### 7.1 pgvectorドキュメント

- GitHub: https://github.com/pgvector/pgvector
- Go client: https://github.com/pgvector/pgvector-go

### 7.2 関連ファイル（catchup-ai側）

- `catchup-feed-ai/src/catchup_ai/infra/db/models.py` - SQLAlchemyモデル（参考）
- `catchup-feed-ai/proto/article.proto` - gRPC定義（参考）
- `catchup-feed-ai/compose.yml` - 開発用Docker設定（pgvectorイメージ使用）

### 7.3 テスト用SQLクエリ

```sql
-- pgvector拡張の確認
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';

-- テーブル存在確認
SELECT table_name FROM information_schema.tables
WHERE table_name = 'article_embeddings';

-- サンプルデータ挿入（1536次元のゼロベクトル）
INSERT INTO article_embeddings (article_id, embedding_type, provider, model, dimension, embedding)
VALUES (1, 'content', 'openai', 'text-embedding-3-small', 1536, '[0,0,0,...,0]'::vector(1536));

-- 類似検索テスト
SELECT article_id, 1 - (embedding <=> '[0.1,0.2,...]'::vector(1536)) as similarity
FROM article_embeddings
ORDER BY embedding <=> '[0.1,0.2,...]'::vector(1536)
LIMIT 10;
```

---

## 8. 質問・確認事項

backend実装時に確認が必要な点：

1. **マイグレーションツール**: 現在使用しているマイグレーションツールは？（golang-migrate, goose, 独自実装など）

2. **ベクトル次元数**: 初期は1536（OpenAI）固定でよいか？将来的に可変にする予定はあるか？

3. **gRPCエンドポイント**: catchup-aiからの直接DB書き込みを許可するか、gRPC経由のみにするか？

4. **バッチ処理**: 既存記事のbackfillはどのタイミングで実行するか？

---

**作成日**: 2026-01-22
**更新日**: 2026-01-22（PostgreSQL 18対応に更新）
**作成者**: catchup-ai開発（Claude Code支援）
**対象**: catchup-feed-backend 開発者
