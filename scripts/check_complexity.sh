#!/bin/bash
# Enforces CCN <= 20 per function using radon
echo "=== Running Cyclomatic Complexity Checks (CCN <= 20) ==="
if ! command -v radon &> /dev/null; then
    echo "radon could not be found. Please install it with 'pip install radon'."
    exit 1
fi

VIOLATIONS=$(radon cc --min D backend/app backend/main.py -i "routes")

if [ -n "$VIOLATIONS" ]; then
    echo "❌ Complexity checks failed! The following functions have CCN > 20:"
    echo "$VIOLATIONS"
    exit 1
else
    echo "✅ Complexity checks passed (all functions CCN <= 20)."
    exit 0
fi
