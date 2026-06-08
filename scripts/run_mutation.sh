#!/bin/bash
# Runs mutation testing with mutmut and validates mutation score
echo "=== Running Mutation Testing Gate (>= 60%) ==="
export PYTHONPATH=backend

rm -f .mutmut-cache

# Run mutmut targeting the reranker module to keep it fast
mutmut run > /dev/null

# Get the results
RESULTS=$(mutmut results)
echo "$RESULTS"

# Parse counts of killed, survived, suspended etc.
# mutmut results output format: "To apply a patch:..." followed by status line
# E.g. "4/4  killed 4" or similar
# Let's extract total and killed using a robust regex or python parsing script
PARSED=$(python3 -c "
import sys, re
text = sys.stdin.read()
# Find line containing 'killed' or 'survived'
lines = [l for l in text.split('\n') if 'killed' in l or 'survived' in l]
if not lines:
    print('0 0')
    sys.exit(0)
line = lines[-1]
# E.g. '4/4  killed 4'
m_all = re.search(r'(\d+)/(\d+)', line)
m_killed = re.search(r'killed (\d+)', line)
if m_all and m_killed:
    print(f'{m_all.group(2)} {m_killed.group(1)}')
else:
    print('0 0')
" <<< "$RESULTS")

read -r TOTAL KILLED <<< "$PARSED"

if [ -z "$TOTAL" ] || [ "$TOTAL" -eq 0 ]; then
    echo "⚠️  No mutations generated or mutmut run failed!"
    exit 1
fi

SCORE=$(python3 -c "print(int(($KILLED / $TOTAL) * 100))")
echo "Mutation Score: $SCORE% ($KILLED killed out of $TOTAL total mutations)"

if [ "$SCORE" -lt 60 ]; then
    echo "❌ Mutation score was under 60%!"
    exit 1
else
    echo "✅ Mutation score passed (>= 60%)."
    exit 0
fi
