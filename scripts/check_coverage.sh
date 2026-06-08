#!/bin/bash
# Runs tests and enforces minimum 80% coverage using pytest-cov
echo "=== Running Unit Tests & Coverage Gate (>= 80%) ==="
export PYTHONPATH=backend
if ! pytest --cov=app.pipeline.ranking.reranker backend/tests --cov-fail-under=80; then
    echo "❌ Test suite failed or coverage was under 80%!"
    exit 1
else
    echo "✅ Tests passed and coverage is at least 80%."
    exit 0
fi
