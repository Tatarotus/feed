#!/bin/bash
# Enforces maximum file size of 500 lines for Python files. Warns at 300 lines.

STAGED_ONLY=false
if [ "$1" == "--staged-only" ]; then
    STAGED_ONLY=true
fi

echo "=== Running File Size Audits (Max 500 lines) ==="

if [ "$STAGED_ONLY" = true ]; then
    FILES=$(git diff --cached --name-only --diff-filter=ACM | grep '\.py$')
else
    FILES=$(find backend/app -name "*.py")
fi

VIOLATIONS=0
for FILE in $FILES; do
    if [ -f "$FILE" ]; then
        LINES=$(wc -l < "$FILE")
        if [ "$LINES" -gt 500 ]; then
            echo "❌ File too large: $FILE ($LINES lines exceeds 500 max)"
            VIOLATIONS=$((VIOLATIONS + 1))
        elif [ "$LINES" -gt 300 ]; then
            echo "⚠️  Warning: $FILE is getting large ($LINES lines exceeds 300 warn)"
        fi
    fi
done

if [ "$VIOLATIONS" -gt 0 ]; then
    echo "❌ File size audit failed! Please split files exceeding 500 lines."
    exit 1
else
    echo "✅ File size audits passed."
    exit 0
fi
