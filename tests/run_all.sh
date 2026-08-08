#!/bin/bash
set -e

PYTHON="./ml-env/bin/python"

echo "=== Running Unit Tests ==="
$PYTHON -m pytest tests/test_model_router.py tests/test_graph_store.py \
    tests/test_admission_unit.py tests/test_checkpoint.py \
    tests/test_faiss_worker.py tests/test_graph_api.py -v --tb=short

echo ""
echo "=== Running Integration Tests (skips automatically if servers are offline) ==="
$PYTHON -m pytest tests/test_integration_admission_worker.py \
    tests/test_integration_graph_chain.py \
    tests/test_integration_model_routing.py \
    tests/test_integration_faiss_graph.py -v --tb=short

echo ""
echo "🎉 All enabled tests completed successfully!"
