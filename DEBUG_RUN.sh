#!/bin/bash
# Debug script to run the application with verbose logging

set -e

cd "$(dirname "$0")"

# Activate virtualenv
source .venv/bin/activate

echo "=================================================="
echo "NEXUS AUDIT V3 - DEBUG RUN"
echo "=================================================="
echo ""
echo "Step 1: Clearing previous audit data..."
rm -f audit_data_complete.json
cat > audit_data_complete.json << 'EOF'
{
  "metadata": {"total_findings": 0},
  "findings": []
}
EOF
echo "✓ Cleared audit_data_complete.json"
echo ""

echo "Step 2: Monitoring JSON file for changes..."
echo "=============================================="
echo "Run this in another terminal to watch the file:"
echo ""
echo "  watch -n 0.1 'echo \"=== audit_data_complete.json ===\"  && jq \".metadata.total_findings, (.findings | length)\" audit_data_complete.json 2>/dev/null || echo \"File is empty or invalid\"'"
echo ""
echo "=============================================="
echo ""

echo "Step 3: Starting server with debug logging..."
echo ""

# Export debug flag
export DEBUG=1

# Run server with Python's verbose output
python -u server.py 2>&1 | while IFS= read -r line; do
    echo "[$(date '+%H:%M:%S.%3N')] $line"
done
