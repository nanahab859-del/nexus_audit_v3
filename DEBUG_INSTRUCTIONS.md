# How to Debug the JSON File Issue

## Quick Start (One Terminal)

Run this command in the terminal:

```bash
cd /home/yusupha/my_tools/nexus_audit_v3
source .venv/bin/activate
python server.py
```

Then open your browser to http://localhost:8421 and click the "Run" button.

Watch the terminal output for these debug messages:
- `[SCANNER DEBUG] 'vulture' starting scan...`
- `[SCANNER DEBUG] 'vulture' returned X findings`
- `[SCANNER DEBUG] 'bandit' starting scan...`  
- `[SCANNER DEBUG] 'bandit' returned X findings`
- `[ORCHESTRATOR DEBUG] Collected X total findings from all scanners`
- `[ORCHESTRATOR DEBUG] audit_data findings count: X`
- `[ORCHESTRATOR DEBUG] ✓ File written and verified: X findings in file`

## Advanced Debug (Two Terminals)

**Terminal 1 - Start the server:**
```bash
cd /home/yusupha/my_tools/nexus_audit_v3
source .venv/bin/activate
python server.py
```

**Terminal 2 - Monitor the JSON file:**
```bash
cd /home/yusupha/my_tools/nexus_audit_v3
watch -n 0.1 'jq ".metadata.total_findings, (.findings | length)" audit_data_complete.json 2>/dev/null || echo "empty"'
```

**Terminal 3 - Test the API directly:**
```bash
cd /home/yusupha/my_tools/nexus_audit_v3
curl -s http://localhost:8421/api/data | jq ".metadata.total_findings, (.findings | length)"
```

## What to Look For

The debug messages will tell us:
1. **Are scanners running?** Look for `[SCANNER DEBUG] 'vulture' starting scan...`
2. **Are scanners finding anything?** Look for `returned X findings`
3. **Are findings being collected?** Look for `[ORCHESTRATOR DEBUG] Collected X total findings`
4. **Are findings in the JSON?** Look for `[ORCHESTRATOR DEBUG] ✓ File written and verified: X findings in file`

If you see `[ORCHESTRATOR DEBUG] ✗ File write FAILED`, the file isn't being written at all.

## What I Changed

I added detailed logging to:
- **orchestrator.py**: Added debug messages to see what findings are collected and written
- **scanner execution**: Added debug messages to see what each scanner returns

Now when you run, every step will be visible in the terminal and browser logs.
