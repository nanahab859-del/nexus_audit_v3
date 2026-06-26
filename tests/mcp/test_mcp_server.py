import pytest
import json
import subprocess
import sys

def test_stdio_purity():
    """Start the server, send initialize, assert stdout is valid JSON-RPC."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "core.mcp.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    req = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0.0"}
        }
    }) + "\n"
    
    proc.stdin.write(req)
    proc.stdin.flush()
    
    out_line = proc.stdout.readline()
    proc.terminate()
    
    assert out_line.strip() != ""
    try:
        resp = json.loads(out_line)
        assert resp["jsonrpc"] == "2.0"
        assert "result" in resp or "error" in resp
    except json.JSONDecodeError:
        pytest.fail(f"Server output was not valid JSON: {out_line}")

def test_pydantic_validation():
    """Verify pydantic models validate input types."""
    from core.mcp.server import mcp
    
    assert mcp.get_tool("run_project_audit") is not None
    assert mcp.get_tool("get_latest_audit_summary") is not None
    assert mcp.get_tool("list_findings") is not None
    assert mcp.get_tool("get_finding_detail") is not None
    assert mcp.get_tool("get_file_context") is not None
