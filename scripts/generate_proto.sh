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

# Generate Python code
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

echo "Proto generation complete!"
echo "Generated files:"
ls -la "$OUTPUT_DIR"
