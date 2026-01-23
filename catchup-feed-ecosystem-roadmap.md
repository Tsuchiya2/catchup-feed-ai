# catchup-feed ecosystem 学習ロードマップ

> Python（LLM/RAG/ファインチューニング）7 : Go 3 の比重で、理論を押さえつつ手を動かして学ぶ
> catchup-feedとマイクロサービス連携で実践的なアウトプットを目指す

---

## 目次

1. [プロジェクト概要](#プロジェクト概要)
2. [システムアーキテクチャ](#システムアーキテクチャ)
3. [学習ロードマップ（8週間）](#学習ロードマップ8週間)
4. [Week 1 詳細タスク](#week-1-詳細タスク)
5. [成果物と転職活動への接続](#成果物と転職活動への接続)
6. [参考リソース](#参考リソース)

---

## プロジェクト概要

### 背景と目的

catchup-feed（Go製RSSアグリゲーター）をコアとして、Python製のAIサービスをマイクロサービスとして連携させる。これにより以下を達成する：

- **Python/LLM学習**: RAG、Embedding、ファインチューニングの理論と実装
- **Go深化**: gRPC、並行処理パターン、CLI拡張
- **マイクロサービス設計**: 言語を跨いだシステム連携の実践
- **転職市場での差別化**: 「AIを使う」だけでなく「AIの仕組みを理解して実装できる」エンジニアへ

### 狙うポジショニング

| 現在の強み | 追加する強み | 目指す姿 |
|-----------|-------------|---------|
| Rails × AI駆動開発（EDAF） | LLM/RAG実装力 | AIの原理を理解した実装者 |
| Goでのアウトプット | Python + マイクロサービス | 言語を跨いだ設計ができるエンジニア |

---

## システムアーキテクチャ

```
┌─────────────────────────────────────────────────────────────────┐
│                    catchup-feed ecosystem                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    gRPC     ┌──────────────────────────┐     │
│  │ catchup-feed │◄──────────►│   catchup-ai (Python)    │     │
│  │    (Go)      │             │                          │     │
│  │              │             │  ┌────────────────────┐  │     │
│  │ • RSS収集    │   REST API  │  │ Embedding Service  │  │     │
│  │ • 記事保存   │◄───────────►│  └────────────────────┘  │     │
│  │ • CLI        │             │  ┌────────────────────┐  │     │
│  └──────────────┘             │  │ RAG Service        │  │     │
│         │                     │  └────────────────────┘  │     │
│         │                     │  ┌────────────────────┐  │     │
│         ▼                     │  │ Summary Service    │  │     │
│  ┌──────────────┐             │  └────────────────────┘  │     │
│  │  PostgreSQL  │◄────────────┤                          │     │
│  │  + pgvector  │             └──────────────────────────┘     │
│  └──────────────┘                                               │
│         ▲                     ┌──────────────────────────┐     │
│         │                     │   catchup-web (将来)     │     │
│         └─────────────────────┤   Rails / Next.js        │     │
│                               └──────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

### コンポーネント説明

| コンポーネント | 言語 | 責務 |
|--------------|------|------|
| catchup-feed | Go | RSS収集、記事保存、CLI、gRPCクライアント |
| catchup-ai | Python | Embedding生成、RAG検索、要約生成、gRPCサーバー |
| PostgreSQL + pgvector | - | 記事データ + ベクトルデータの永続化 |
| catchup-web | Rails/Next.js | （将来）Webインターフェース |

### 通信方式

- **gRPC**: catchup-feed ↔ catchup-ai 間のサービス間通信
- **REST API**: 外部からのアクセス用（将来のWeb UI向け）
- **PostgreSQL**: 共有データストア（記事 + ベクトル）

---

## 学習ロードマップ（8週間）

### 全体スケジュール

```
Week 1-2: 基礎理論 + 環境構築
Week 3-4: catchup-ai コア実装
Week 5-6: RAG本格実装 + Go連携
Week 7-8: ファインチューニング実験 + 統合
```

---

### Week 1-2: 基礎理論 + 環境構築

#### 理論学習（Python 70%）

| トピック | リソース | 目標 |
|---------|---------|------|
| Transformer基礎 | [Illustrated Transformer](https://jalammar.github.io/illustrated-transformer/) | Attention機構の直感的理解 |
| Embedding概念 | OpenAI Cookbook | ベクトル空間での類似度計算 |
| RAGアーキテクチャ | LangChain/LlamaIndex公式ドキュメント | Retrieval → Augmentation → Generation の流れ |

#### 実践目標

**Python側:**
- Python環境構築（uv / poetry）
- OpenAI API基本操作
- 簡易Embeddingスクリプト作成
- 類似度計算の実装

**Go側（30%）:**
- gRPC基礎学習（proto定義、コード生成）
- サービス間通信の設計検討
- Protocol Buffers チュートリアル

#### 成果物
- [ ] Python開発環境
- [ ] Embedding実験スクリプト
- [ ] gRPC proto定義ドラフト
- [ ] 理論学習ノート

---

### Week 3-4: catchup-ai コア実装

#### 理論学習

| トピック | 内容 |
|---------|------|
| ベクトルDB比較 | pgvector vs Qdrant vs Chroma の特性理解 |
| Chunking戦略 | 文章分割の最適化手法（固定長 vs セマンティック） |
| Retrieval手法 | Dense vs Sparse vs Hybrid検索 |

#### ディレクトリ構成

```
catchup-ai/
├── proto/                    # gRPC定義
│   └── article.proto
├── src/
│   ├── embedding/           # Embeddingサービス
│   │   ├── service.py
│   │   └── models.py
│   ├── rag/                 # RAGサービス
│   │   ├── retriever.py
│   │   └── generator.py
│   └── api/                 # FastAPI / gRPC server
│       ├── grpc_server.py
│       └── rest_server.py
├── tests/
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

#### マイルストーン
- [ ] 記事テキスト → Embedding変換パイプライン
- [ ] pgvectorへの保存・類似検索
- [ ] gRPCエンドポイント実装（EmbedArticle, SearchSimilar）
- [ ] 単体テスト

---

### Week 5-6: RAG本格実装 + Go連携

#### 理論学習

| トピック | 内容 |
|---------|------|
| Prompt Engineering | RAG用プロンプト設計パターン |
| Context Window最適化 | トークン効率の考え方、圧縮手法 |
| Evaluation手法 | RAGの評価指標（Faithfulness, Relevance, Recall） |

#### 実装タスク

**Python側:**
- RAG検索エンドポイント実装
- 要約生成サービス
- プロンプトテンプレート管理

**Go側:**
- gRPCクライアント実装
- CLIコマンド拡張

#### CLI拡張イメージ

```bash
# 意味検索
$ catchup-feed search "今週のRust関連ニュース"
→ gRPC経由でcatchup-aiに問い合わせ
→ 関連記事をRAGで検索・要約して返却

# 週次サマリー
$ catchup-feed summarize --period=week --topic=ai
→ 週次AI関連記事の自動サマリー生成

# 記事追加時の自動Embedding
$ catchup-feed fetch
→ 新規記事取得 → 自動でEmbedding生成・保存
```

#### マイルストーン
- [ ] RAG検索の実装（検索 → コンテキスト構築 → 生成）
- [ ] Go gRPCクライアント
- [ ] CLI `search` / `summarize` コマンド
- [ ] 記事追加時の非同期Embedding処理

---

### Week 7-8: ファインチューニング実験 + 統合

#### 理論学習

| トピック | 内容 |
|---------|------|
| LoRA/QLoRA | パラメータ効率的学習の原理 |
| データセット設計 | Instruction形式の作り方、品質管理 |
| 評価・比較 | Base vs Fine-tuned の定量評価 |

#### 実験プロジェクト: 技術記事分類モデル

```
目的: 記事を自動でカテゴリ分類（AI, Web, Infra, Security, etc.）

データソース: catchup-feedで収集した記事（タイトル + 本文）
手法: LoRAでの分類タスク fine-tuning
評価指標: 
  - 分類精度（Accuracy, F1）
  - 推論速度
  - Base modelとの比較
```

#### 最終統合タスク

- [ ] 全サービスのDocker Compose化
- [ ] E2Eテスト（記事収集 → Embedding → 検索 → 要約）
- [ ] README / アーキテクチャドキュメント整備
- [ ] 技術記事執筆（Qiita/Zenn）

---

## Week 1 詳細タスク

### Day 1-2: 環境構築 + 理論開始

**環境構築:**
```bash
# Python環境（uvを推奨）
curl -LsSf https://astral.sh/uv/install.sh | sh
uv init catchup-ai
cd catchup-ai
uv add openai python-dotenv jupyter

# OpenAI APIキー設定
echo "OPENAI_API_KEY=sk-xxx" > .env
```

**理論学習:**
- Illustrated Transformer 精読（2-3時間）
- 理解したことをノートにまとめる（後の記事ネタに）
- 疑問点をリストアップ

### Day 3-4: Embedding実験

**実装タスク:**
```python
# embedding_experiment.py
from openai import OpenAI
import numpy as np

client = OpenAI()

def get_embedding(text: str) -> list[float]:
    response = client.embeddings.create(
        input=text,
        model="text-embedding-3-small"
    )
    return response.data[0].embedding

def cosine_similarity(a: list[float], b: list[float]) -> float:
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

# catchup-feedの記事データで実験
# - 類似記事の検索
# - カテゴリ別のクラスタリング可視化
```

**目標:**
- [ ] Embedding生成が動作
- [ ] 類似度計算の実装
- [ ] catchup-feedの実データで実験

### Day 5-6: gRPC基礎（Go側）

**学習リソース:**
- [gRPC Go Quick Start](https://grpc.io/docs/languages/go/quickstart/)
- Protocol Buffers Language Guide

**実装タスク:**
```protobuf
// proto/article.proto
syntax = "proto3";

package catchup;

option go_package = "github.com/yourusername/catchup-feed/proto";

service ArticleAI {
  rpc EmbedArticle(EmbedRequest) returns (EmbedResponse);
  rpc SearchSimilar(SearchRequest) returns (SearchResponse);
  rpc Summarize(SummarizeRequest) returns (SummarizeResponse);
}

message EmbedRequest {
  string article_id = 1;
  string title = 2;
  string content = 3;
}

message EmbedResponse {
  string article_id = 1;
  bool success = 2;
}

// ... 他のメッセージ定義
```

### Day 7: 振り返り + 次週計画

- 学んだことの整理
- 疑問点の解消（調査 or 記録）
- Week 2の詳細計画作成
- 必要に応じてスケジュール調整

---

## 成果物と転職活動への接続

### 技術的アピールポイント

| 成果物 | アピール内容 |
|--------|-------------|
| catchup-ai | LLM/RAGの実装原理を理解している証明 |
| マイクロサービス構成 | Go + Python を跨いだシステム設計力 |
| gRPC連携 | モダンなサービス間通信の実装経験 |
| ファインチューニング | MLOps入門、AIカスタマイズの知見 |

### ビジネス的アピールポイント

| 観点 | アピール内容 |
|------|-------------|
| AI機能の内製化 | 外部APIに依存しない実装力 |
| スケーラブル設計 | マイクロサービスによる拡張性 |
| 実用的アウトプット | 自身の情報収集を効率化するツール |

### 技術記事ネタ

1. **Week 2終了時**: 「Transformerの仕組みを図解で理解する」
2. **Week 4終了時**: 「Go + Python gRPCで作るマイクロサービス」
3. **Week 6終了時**: 「自作RAGシステムの設計と実装」
4. **Week 8終了時**: 「LoRAで技術記事分類モデルを作る」

---

## 参考リソース

### 理論学習

- [Illustrated Transformer](https://jalammar.github.io/illustrated-transformer/)
- [OpenAI Cookbook](https://cookbook.openai.com/)
- [LangChain Documentation](https://python.langchain.com/docs/)
- [LlamaIndex Documentation](https://docs.llamaindex.ai/)

### 実装参考

- [gRPC Go Quick Start](https://grpc.io/docs/languages/go/quickstart/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [pgvector GitHub](https://github.com/pgvector/pgvector)

### ファインチューニング

- [Hugging Face PEFT](https://huggingface.co/docs/peft/)
- [LoRA Paper](https://arxiv.org/abs/2106.09685)

---

## 進捗管理

### チェックリスト

**Week 1-2:**
- [ ] Python環境構築完了
- [ ] Transformer理論理解
- [ ] Embedding実験完了
- [ ] gRPC proto定義完了

**Week 3-4:**
- [ ] catchup-ai 基本構造完成
- [ ] Embeddingサービス実装
- [ ] pgvector連携完了

**Week 5-6:**
- [ ] RAG検索実装完了
- [ ] Go gRPCクライアント完成
- [ ] CLI拡張完了

**Week 7-8:**
- [ ] ファインチューニング実験完了
- [ ] Docker Compose統合
- [ ] ドキュメント整備
- [ ] 技術記事公開

---

## 更新履歴

| 日付 | 内容 |
|------|------|
| 2025-01-19 | 初版作成 |

