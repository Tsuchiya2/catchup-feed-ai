#!/bin/bash
# Generate Python gRPC code from proto files

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PROTO_DIR="$PROJECT_ROOT/proto"
OUTPUT_DIR="$PROJECT_ROOT/src/catchup_ai/api/grpc/generated"

echo "Generating Python gRPC code from proto files..."
echo "Proto dir: $PROTO_DIR"
echo "Output dir: $OUTPUT_DIR"

# Ensure output directory exists
mkdir -p "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR/embedding"

# Generate Python code for article.proto (catchup-ai server)
echo "Generating article.proto..."
python -m grpc_tools.protoc \
    --proto_path="$PROTO_DIR" \
    --python_out="$OUTPUT_DIR" \
    --pyi_out="$OUTPUT_DIR" \
    --grpc_python_out="$OUTPUT_DIR" \
    "$PROTO_DIR/article.proto"

# Fix imports in generated files (grpc_tools generates absolute imports)
# This is a known issue with grpc_tools
sed -i '' 's/^import article_pb2/from . import article_pb2/' "$OUTPUT_DIR/article_pb2_grpc.py" 2>/dev/null || \
sed -i 's/^import article_pb2/from . import article_pb2/' "$OUTPUT_DIR/article_pb2_grpc.py"

# Generate Python code for embedding.proto (backend client)
echo "Generating embedding/embedding.proto..."
python -m grpc_tools.protoc \
    --proto_path="$PROTO_DIR" \
    --python_out="$OUTPUT_DIR" \
    --pyi_out="$OUTPUT_DIR" \
    --grpc_python_out="$OUTPUT_DIR" \
    "$PROTO_DIR/embedding/embedding.proto"

# Fix imports for embedding proto (grpc_tools generates nested module paths)
# Replace "from embedding import embedding_pb2" with "from . import embedding_pb2"
sed -i '' 's/from embedding import embedding_pb2/from . import embedding_pb2/' "$OUTPUT_DIR/embedding/embedding_pb2_grpc.py" 2>/dev/null || \
sed -i 's/from embedding import embedding_pb2/from . import embedding_pb2/' "$OUTPUT_DIR/embedding/embedding_pb2_grpc.py"

# Also fix in embedding_pb2.py if there are any imports
sed -i '' 's/from embedding import/from . import/' "$OUTPUT_DIR/embedding/embedding_pb2.py" 2>/dev/null || \
sed -i 's/from embedding import/from . import/' "$OUTPUT_DIR/embedding/embedding_pb2.py"

# Create __init__.py for embedding subpackage
cat > "$OUTPUT_DIR/embedding/__init__.py" << 'EOF'
"""Generated gRPC code for backend EmbeddingService client."""

from .embedding_pb2 import (
    StoreEmbeddingRequest,
    StoreEmbeddingResponse,
    GetEmbeddingsRequest,
    GetEmbeddingsResponse,
    SearchSimilarRequest,
    SearchSimilarResponse,
    DeleteEmbeddingRequest,
    DeleteEmbeddingResponse,
    ArticleEmbedding,
    SimilarArticle,
)
from .embedding_pb2_grpc import (
    EmbeddingServiceStub,
    EmbeddingServiceServicer,
    add_EmbeddingServiceServicer_to_server,
)

__all__ = [
    # Messages
    "StoreEmbeddingRequest",
    "StoreEmbeddingResponse",
    "GetEmbeddingsRequest",
    "GetEmbeddingsResponse",
    "SearchSimilarRequest",
    "SearchSimilarResponse",
    "DeleteEmbeddingRequest",
    "DeleteEmbeddingResponse",
    "ArticleEmbedding",
    "SimilarArticle",
    # Service
    "EmbeddingServiceStub",
    "EmbeddingServiceServicer",
    "add_EmbeddingServiceServicer_to_server",
]
EOF

echo ""
echo "Proto generation complete!"
echo "Generated files:"
ls -la "$OUTPUT_DIR"
echo ""
echo "Embedding subpackage:"
ls -la "$OUTPUT_DIR/embedding"
