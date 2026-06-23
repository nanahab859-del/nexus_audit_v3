# Nexus Audit V3 — CLI Extension: New Commands

**Document type:** CLI Extension Specification  
**Parent spec:** Nexus Audit CLI Specifications v1.0  
**Integrates:** MCP Server Spec v1.0, Storage Architecture Spec v3.0  
**Version:** 1.0  
**Date:** June 2026

---

## Integration Map

The CLI, MCP server, and storage layer share one `Orchestrator`. They never share state — they each call the same methods independently.

```
┌──────────────────────────────────────────────────────────────┐
│                    Interfaces                                 │
│                                                              │
│   CLI (cli.py)          MCP Server (nexus/mcp/server.py)     │
│   └─ CommandRegistry    └─ FastMCP tool registry             │
│      └─ Handlers           └─ Tool handlers                  │
│         │                     │                              │
│         └──────────┬──────────┘                              │
│                    │                                         │
│              ctx.orchestrator                                │
│                    │                                         │
└────────────────────┼─────────────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────────────┐
│                   Orchestrator                                │
│                                                              │
│  run_audit()   diff_runs()   get_trend()                     │
│  get_fix_queue()   export_audit()   rebuild_index()          │
│  configure_mcp()                                             │
│                    │                                         │
│             ~/.nexus_audit/                                  │
│             ├── projects/<id>/nexus_state.db  (SQLite index) │
│             └── jobs/<job_id>/                               │
│                 ├── audit_data_complete.json                  │
│                 └── audit_summary.json                        │
└──────────────────────────────────────────────────────────────┘
```

**Rule:** CLI handlers and MCP tool handlers must never contain business logic. They format input, call `ctx.orchestrator`, and format output. The Orchestrator is the only place that knows how to read the database or run a scan.

---

## New Commands — Overview

Five commands, filling the gaps left by the existing `audit:run` / `fix:list` / `fix:apply` set:

| Command | Namespace | Privilege | Alias | From Spec |
|---|---|---|---|---|
| `audit:diff` | audit | OPERATOR | `diff` | Storage spec |
| `audit:trend` | audit | READONLY | `trend` | Storage spec |
| `audit:export` | audit | OPERATOR | `export` | Storage + MCP spec |
| `fix:queue` | fix | READONLY | `queue` | Storage spec |
| `mcp:config` | mcp | ADMIN | — | MCP server spec |

---

## Handler File: `core/primitives/commands/handlers/audit_ext.py`

This file extends the audit namespace. It lives alongside `audit.py` and registers additional audit commands.

```python
# core/primitives/commands/handlers/audit_ext.py
from __future__ import annotations

import sys

from core.primitives.commands.context import OPERATOR, READONLY


def register(registry) -> None:
    """Called by CommandRegistry._register_all() at startup."""
    from core.primitives.commands.registry import Command
    from core.primitives.commands.parser import CommandParser

    registry.register(Command(
        name="audit:diff",
        description="Show the structural diff between two audit runs.",
        usage="audit:diff [--run-a RUN_ID] [--run-b RUN_ID]",
        handler=_handle_diff,
        required_privilege=OPERATOR,
        aliases=["diff"],
        parser=(
            CommandParser("audit:diff")
            .add_argument(
                "--run-a",
                default=None,
                help="Older run ID (baseline). Defaults to second-to-last run.",
            )
            .add_argument(
                "--run-b",
                default=None,
                help="Newer run ID (target). Defaults to the latest run.",
            )
        ),
    ))

    registry.register(Command(
        name="audit:trend",
        description="Show score trend across recent audit runs.",
        usage="audit:trend [--last N] [--branch BRANCH]",
        handler=_handle_trend,
        required_privilege=READONLY,
        aliases=["trend"],
        parser=(
            CommandParser("audit:trend")
            .add_argument(
                "--last",
                type=int,
                default=10,
                help="Number of runs to include (max 50).",
            )
            .add_argument(
                "--branch",
                default=None,
                help="Filter to a specific git branch.",
            )
        ),
    ))

    registry.register(Command(
        name="audit:export",
        description="Export audit findings in SARIF, JSON, or CSV format.",
        usage="audit:export [--format sarif|json|csv] [--since Nd] [--output PATH]",
        handler=_handle_export,
        required_privilege=OPERATOR,
        aliases=["export"],
        parser=(
            CommandParser("audit:export")
            .add_argument(
                "--format",
                choices=["sarif", "json", "csv"],
                default="sarif",
                help="Output format. Default: sarif (compatible with GitHub, VS Code, GitLab).",
            )
            .add_argument(
                "--since",
                default="90d",
                help="Export runs since N days ago. Examples: 30d, 7d, 90d.",
            )
            .add_argument(
                "--output",
                default=None,
                help="Output file path. Defaults to <project>_<format>_<date>.<ext>.",
            )
        ),
    ))


# ──────────────────────────────────────────────────────────────────
# Handlers
# ──────────────────────────────────────────────────────────────────

async def _handle_diff(ctx, params) -> None:
    """
    Diff two audit runs. Defaults to diffing the two most recent runs.

    DO NOT call click.echo() or print() here.
    DO delegate to ctx.orchestrator.
    """
    if not ctx.active_project:
        ctx.write_error("No active project. Run 'workspace:active <id>' first.")
        return

    run_a = params.get("run_a")
    run_b = params.get("run_b")

    try:
        diff = await ctx.orchestrator.diff_runs(
            project_id=ctx.active_project.id,
            run_id_a=run_a,   # None → orchestrator picks second-to-last
            run_id_b=run_b,   # None → orchestrator picks latest
        )
    except ValueError as e:
        ctx.write_error(str(e))
        return

    # ── Score delta ───────────────────────────────────────────────
    d = diff["score_delta"]
    ctx.write(f"\nRuns:  {diff['run_id_a']}")
    ctx.write(f"    →  {diff['run_id_b']}")
    ctx.write("")
    ctx.write(
        f"Score delta:  overall {d['overall']:+.1f}"
        f"  (security {d['security']:+.1f} | quality {d['quality']:+.1f})"
    )

    # ── Findings ─────────────────────────────────────────────────
    new = diff["new_findings"]
    res = diff["resolved_findings"]
    sev = new.get("by_severity", {})

    ctx.write("")
    ctx.write(
        f"New findings:      {new['count']}"
        + (f"  [CRITICAL: {sev.get('CRITICAL', 0)}  HIGH: {sev.get('HIGH', 0)}]" if new["count"] else "")
    )
    ctx.write(f"Resolved findings: {res['count']}")

    # ── Coupling changes ─────────────────────────────────────────
    cc = diff.get("coupling_changes", {})
    added = cc.get("added_edges", [])
    removed = cc.get("removed_edges", [])

    if added:
        ctx.write("")
        for edge in added:
            ctx.write(f"  + coupling added:   {edge[0]} → {edge[1]}  (check for regression)")
    if removed:
        for edge in removed:
            ctx.write(f"  - coupling removed: {edge[0]} → {edge[1]}  (improved isolation)")

    # ── Probable commit ──────────────────────────────────────────
    if diff.get("probable_commit"):
        ctx.write("")
        ctx.write(f"Probable cause: commit {diff['probable_commit']}")

    # ── Next step hint ───────────────────────────────────────────
    if new["count"] > 0:
        ctx.write("")
        ctx.write("→ Run 'fix:queue' to see prioritised findings.")


async def _handle_trend(ctx, params) -> None:
    """
    Render a score trend table for the last N runs.
    Reads from SQLite index in O(log N). Never touches JSON payloads.
    """
    if not ctx.active_project:
        ctx.write_error("No active project. Run 'workspace:active <id>' first.")
        return

    last_n = min(params.get("last", 10), 50)   # hard cap: 50 runs
    branch = params.get("branch")

    try:
        trend = await ctx.orchestrator.get_trend(
            project_id=ctx.active_project.id,
            last_n_runs=last_n,
            branch=branch,
        )
    except Exception as e:
        ctx.write_error(str(e))
        return

    runs = trend.get("runs", [])
    if not runs:
        ctx.write("No audit runs found for this project.")
        if branch:
            ctx.write(f"  (filtering by branch: {branch})")
        return

    branch_label = f"  branch: {branch}" if branch else ""
    ctx.write(f"\nScore trend — last {len(runs)} runs{branch_label}")
    ctx.write("")
    ctx.write(f"  {'Date':<12}  {'Commit':<8}  {'Overall':>8}  {'Security':>9}  {'Quality':>8}  {'High+':>6}")
    ctx.write(f"  {'─' * 12}  {'─' * 8}  {'─' * 8}  {'─' * 9}  {'─' * 8}  {'─' * 6}")

    prev_overall = None
    for run in runs:
        ts       = run["timestamp"][:10]
        commit   = run.get("git_commit", "?")[:8]
        overall  = run["scores"]["overall"]
        security = run["scores"]["security"]
        quality  = run["scores"].get("quality", 0.0)
        high_plus = run["counts"]["critical"] + run["counts"]["high"]

        # Arrow indicator: ▲ improved, ▼ regressed, · unchanged
        if prev_overall is None:
            arrow = " "
        elif overall > prev_overall + 0.5:
            arrow = "▲"
        elif overall < prev_overall - 0.5:
            arrow = "▼"
        else:
            arrow = "·"

        prev_overall = overall

        ctx.write(
            f"  {ts:<12}  {commit:<8}  {arrow}{overall:>7.1f}  {security:>9.1f}"
            f"  {quality:>8.1f}  {high_plus:>6}"
        )

    ctx.write("")
    ctx.write(f"  Latest overall score: {runs[-1]['scores']['overall']:.1f}")


async def _handle_export(ctx, params) -> None:
    """
    Export audit findings in SARIF, JSON, or CSV format.

    SARIF (default) is the OASIS standard consumed natively by:
      - GitHub Code Scanning
      - VS Code Problems panel
      - GitLab Security Dashboard
    """
    if not ctx.active_project:
        ctx.write_error("No active project. Run 'workspace:active <id>' first.")
        return

    fmt       = params.get("format", "sarif")
    since_raw = params.get("since", "90d")
    output    = params.get("output")

    # Parse "30d" → 30
    try:
        since_days = int(since_raw.rstrip("d"))
    except ValueError:
        ctx.write_error(f"Invalid --since value: '{since_raw}'. Use format like '30d' or '7d'.")
        return

    ctx.write(f"Exporting audit data ({fmt.upper()}, last {since_days} days)...")

    try:
        result = await ctx.orchestrator.export_audit(
            project_id=ctx.active_project.id,
            format=fmt,
            since_days=since_days,
            output_path=output,
        )
    except Exception as e:
        ctx.write_error(str(e))
        return

    ctx.write(f"Export complete: {result['findings_count']} findings")
    ctx.write(f"Output:          {result['output_path']}")

    # Format-specific next-step hints
    if fmt == "sarif":
        ctx.write("")
        ctx.write("Upload to GitHub Code Scanning:")
        ctx.write(f"  gh api /repos/OWNER/REPO/code-scanning/sarifs \\")
        ctx.write(f"      -F sarif=@{result['output_path']}")
        ctx.write("")
        ctx.write("Or commit and let your CI workflow upload automatically.")
```

---

## Handler File: `core/primitives/commands/handlers/fix_ext.py`

Extends the fix namespace with a ranked queue command.

```python
# core/primitives/commands/handlers/fix_ext.py
from __future__ import annotations

from core.primitives.commands.context import READONLY


def register(registry) -> None:
    from core.primitives.commands.registry import Command
    from core.primitives.commands.parser import CommandParser

    registry.register(Command(
        name="fix:queue",
        description="Show the ranked fix queue — findings ordered by severity × age × recurrence.",
        usage="fix:queue [--severity LEVEL] [--limit N]",
        handler=_handle_queue,
        required_privilege=READONLY,
        aliases=["queue"],
        parser=(
            CommandParser("fix:queue")
            .add_argument(
                "--severity",
                choices=["CRITICAL", "HIGH", "MEDIUM", "LOW"],
                default="HIGH",
                help="Minimum severity to include. Default: HIGH.",
            )
            .add_argument(
                "--limit",
                type=int,
                default=10,
                help="Maximum items to show (max 50). Default: 10.",
            )
        ),
    ))


async def _handle_queue(ctx, params) -> None:
    """
    Render a ranked fix queue.

    Different from fix:list (which is a flat filter).
    fix:queue uses the Orchestrator's scoring formula:
        priority = severity_weight × age_days × recurrence_count
    """
    if not ctx.active_project:
        ctx.write_error("No active project. Run 'workspace:active <id>' first.")
        return

    severity = params.get("severity", "HIGH")
    limit    = min(params.get("limit", 10), 50)   # hard cap: 50

    try:
        result = await ctx.orchestrator.get_fix_queue(
            project_id=ctx.active_project.id,
            severity_floor=severity,
            limit=limit,
        )
    except Exception as e:
        ctx.write_error(str(e))
        return

    items = result.get("queue", [])

    if not items:
        ctx.write(f"No open findings at {severity}+ severity. Project is clean at this level.")
        return

    ctx.write(f"\nFix queue — {severity}+ severity  ({len(items)} of {result.get('total', '?')} shown)\n")
    ctx.write(f"  {'#':>3}  {'Severity':<10}  {'Rule':<36}  {'File':<30}  {'Age':>5}  {'Impact':>7}")
    ctx.write(f"  {'─' * 3}  {'─' * 10}  {'─' * 36}  {'─' * 30}  {'─' * 5}  {'─' * 7}")

    for i, item in enumerate(items, 1):
        sev    = item["severity"]
        rule   = item["rule_id"][:35]
        fpath  = item["file_path"][-30:]
        age    = item["age_days"]
        impact = item.get("score_impact", 0.0)

        ctx.write(
            f"  {i:>3}  {sev:<10}  {rule:<36}  {fpath:<30}  {age:>4}d  -{impact:>6.1f}"
        )

    top_hash = items[0]["finding_hash"]
    ctx.write("")
    ctx.write(f"→ Inspect top finding: audit:diff  (hash: {top_hash[:12]}...)")
    ctx.write(f"  Snooze it:           fix:apply --snooze {top_hash[:12]} 30d")
```

---

## Handler File: `core/primitives/commands/handlers/mcp.py`

New `mcp:` namespace. Writes agent host configuration — no server management (the agent host spawns the MCP server process, not the CLI).

```python
# core/primitives/commands/handlers/mcp.py
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from core.primitives.commands.context import ADMIN, READONLY


def register(registry) -> None:
    from core.primitives.commands.registry import Command
    from core.primitives.commands.parser import CommandParser

    registry.register(Command(
        name="mcp:config",
        description="Write the Nexus MCP server entry to the agent host config file.",
        usage="mcp:config [--timeout SECONDS] [--host claude|cursor|custom]",
        handler=_handle_config,
        required_privilege=ADMIN,
        parser=(
            CommandParser("mcp:config")
            .add_argument(
                "--timeout",
                type=int,
                default=180,
                help="Tool call timeout in seconds. Default: 180 (3 minutes).",
            )
            .add_argument(
                "--host",
                choices=["claude", "cursor", "custom"],
                default="claude",
                help="Agent host to configure. Default: claude (Claude Desktop).",
            )
        ),
    ))

    registry.register(Command(
        name="mcp:status",
        description="Show current MCP server configuration status.",
        usage="mcp:status",
        handler=_handle_status,
        required_privilege=READONLY,
        parser=CommandParser("mcp:status"),
    ))


# ── Config paths by host ─────────────────────────────────────────

_CONFIG_PATHS = {
    "claude": {
        "darwin":  Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
        "win32":   Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json",
        "linux":   Path.home() / ".config" / "claude" / "claude_desktop_config.json",
    },
    "cursor": {
        "darwin":  Path.home() / "Library" / "Application Support" / "Cursor" / "User" / "mcp_config.json",
        "win32":   Path(os.environ.get("APPDATA", "")) / "Cursor" / "User" / "mcp_config.json",
        "linux":   Path.home() / ".config" / "Cursor" / "User" / "mcp_config.json",
    },
}


def _resolve_config_path(host: str) -> Path:
    platform = sys.platform
    paths = _CONFIG_PATHS.get(host, {})
    return paths.get(platform, paths.get("linux"))


# ── Handlers ─────────────────────────────────────────────────────

async def _handle_config(ctx, params) -> None:
    """
    Write the MCP server config entry to the agent host config file.

    The MCP server is spawned by the agent host (Claude Desktop, Cursor),
    not by the CLI. This command only writes the config entry — it does not
    start a process.

    Requires ADMIN privilege because it writes to a system config file.
    """
    host    = params.get("host", "claude")
    timeout = params.get("timeout", 180)

    config_path = _resolve_config_path(host)
    if config_path is None:
        ctx.write_error(f"Cannot resolve config path for host '{host}' on platform '{sys.platform}'.")
        return

    server_entry = {
        "nexus-audit-v3": {
            "command": sys.executable,       # use the same Python as the CLI
            "args": ["-m", "nexus.mcp.server"],
            "env": {
                "NEXUS_LOG_LEVEL": "INFO",
                "NEXUS_TOOL_TIMEOUT_SECONDS": str(timeout),
            },
        }
    }

    # Load existing config or start fresh
    try:
        existing = json.loads(config_path.read_text()) if config_path.exists() else {}
    except json.JSONDecodeError:
        ctx.write_error(f"Existing config at {config_path} is not valid JSON. Fix it first.")
        return

    existing.setdefault("mcpServers", {})
    already_existed = "nexus-audit-v3" in existing["mcpServers"]
    existing["mcpServers"].update(server_entry)

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(existing, indent=2))
    except PermissionError:
        ctx.write_error(
            f"Cannot write to {config_path}. "
            "On macOS, ensure Claude Desktop has been launched at least once."
        )
        return

    action = "Updated" if already_existed else "Added"
    ctx.write(f"{action} nexus-audit-v3 in: {config_path}")
    ctx.write(f"Tool timeout: {timeout}s")
    ctx.write("")
    ctx.write("Restart the agent host to load the Nexus MCP server.")
    ctx.write("Tools that will become available after restart:")
    ctx.write("  get_server_info   run_project_audit   get_latest_audit_summary")
    ctx.write("  get_finding_detail   list_findings   get_fix_queue")
    ctx.write("  get_trend   diff_runs   get_file_context")


async def _handle_status(ctx, params) -> None:
    """Show whether the MCP server is configured in known agent host config files."""
    found_any = False

    for host, paths in _CONFIG_PATHS.items():
        config_path = paths.get(sys.platform, paths.get("linux"))
        if config_path is None or not config_path.exists():
            continue

        try:
            config = json.loads(config_path.read_text())
        except (json.JSONDecodeError, PermissionError):
            continue

        servers = config.get("mcpServers", {})
        if "nexus-audit-v3" in servers:
            entry = servers["nexus-audit-v3"]
            ctx.write(f"  {host:<10}  ✓ configured   {config_path}")
            ctx.write(f"             command: {' '.join([entry.get('command', '')] + entry.get('args', []))}")
            found_any = True

    if not found_any:
        ctx.write("  MCP server not configured in any known agent host.")
        ctx.write("  Run: mcp:config  (requires --admin flag)")
```

---

## Registration — Changes to `registry.py`

Add the three new modules to `_register_all()`. Two lines per module.

```python
# core/primitives/commands/registry.py  — only the _register_all() method shown

def _register_all(self) -> None:
    from core.primitives.commands.handlers import (
        audit, project, report, fix, log, workspace, settings, system,
        # ── New modules ──────────────────────────────────────────
        audit_ext,   # audit:diff, audit:trend, audit:export
        fix_ext,     # fix:queue
        mcp,         # mcp:config, mcp:status
    )

    audit.register(self)
    project.register(self)
    report.register(self)
    fix.register(self)
    log.register(self)
    workspace.register(self)
    settings.register(self)
    system.register(self)
    # ── New ─────────────────────────────────────────────────────
    audit_ext.register(self)
    fix_ext.register(self)
    mcp.register(self)
```

That is the **only** change to existing files. Everything else is additive.

---

## Updated Command Table

Full command list after this extension:

| Command | Alias | Privilege | Handler File |
|---|---|---|---|
| `audit:run` | `run` | OPERATOR | `audit.py` |
| `audit:stop` | — | OPERATOR | `audit.py` |
| `audit:diff` | `diff` | OPERATOR | `audit_ext.py` ← new |
| `audit:trend` | `trend` | READONLY | `audit_ext.py` ← new |
| `audit:export` | `export` | OPERATOR | `audit_ext.py` ← new |
| `fix:list` | — | READONLY | `fix.py` |
| `fix:apply` | — | OPERATOR | `fix.py` |
| `fix:queue` | `queue` | READONLY | `fix_ext.py` ← new |
| `mcp:config` | — | ADMIN | `mcp.py` ← new |
| `mcp:status` | — | READONLY | `mcp.py` ← new |
| `project:create` | — | OPERATOR | `project.py` |
| `project:list` | `ls` | READONLY | `project.py` |
| `project:delete` | — | ADMIN | `project.py` |
| `report:generate` | — | OPERATOR | `report.py` |
| `report:history` | — | READONLY | `report.py` |
| `log:view` | — | READONLY | `log.py` |
| `log:stream` | — | READONLY | `log.py` |
| `workspace:active` | — | OPERATOR | `workspace.py` |
| `workspace:list` | — | READONLY | `workspace.py` |
| `settings:get` | — | OPERATOR | `settings.py` |
| `settings:set` | — | ADMIN | `settings.py` |
| `exit` | — | READONLY | `system.py` |

---

## Tests

Each handler is tested without a terminal (per the CLI spec pattern in Part 10).

```python
# tests/commands/test_audit_ext.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from core.primitives.commands import CommandContext, CommandRegistry, OPERATOR, READONLY

def _make_ctx(privilege=OPERATOR, has_project=True):
    ctx = MagicMock(spec=CommandContext)
    ctx.stdout_buffer = []
    ctx.has_error = False
    ctx.active_project = MagicMock(id="proj-001") if has_project else None
    ctx.privilege_level = privilege
    ctx.orchestrator = AsyncMock()
    ctx.write = lambda t: ctx.stdout_buffer.append(t)
    ctx.write_error = lambda t: ctx.stdout_buffer.append(f"[ERROR] {t}") or setattr(ctx, "has_error", True)
    return ctx


# ── audit:diff ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_diff_no_project():
    ctx = _make_ctx(has_project=False)
    registry = CommandRegistry(MagicMock(), orchestrator=AsyncMock())
    await registry.execute("audit:diff", ctx)
    assert ctx.has_error
    assert any("No active project" in line for line in ctx.stdout_buffer)


@pytest.mark.asyncio
async def test_diff_renders_delta():
    ctx = _make_ctx()
    ctx.orchestrator.diff_runs.return_value = {
        "run_id_a": "2026-06-08T10-00Z_abc",
        "run_id_b": "2026-06-15T14-00Z_def",
        "score_delta": {"overall": -9.2, "security": -14.1, "quality": 4.9},
        "new_findings": {"count": 3, "by_severity": {"CRITICAL": 1, "HIGH": 2}},
        "resolved_findings": {"count": 1},
        "coupling_changes": {"added_edges": [["auth", "payments"]], "removed_edges": []},
        "probable_commit": "a3f9c2b",
    }
    registry = CommandRegistry(MagicMock(), orchestrator=ctx.orchestrator)
    await registry.execute("audit:diff", ctx)
    assert not ctx.has_error
    assert any("−9.2" in line or "-9.2" in line for line in ctx.stdout_buffer)
    assert any("auth" in line for line in ctx.stdout_buffer)


# ── audit:trend ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_trend_no_runs():
    ctx = _make_ctx()
    ctx.orchestrator.get_trend.return_value = {"runs": []}
    registry = CommandRegistry(MagicMock(), orchestrator=ctx.orchestrator)
    await registry.execute("audit:trend", ctx)
    assert not ctx.has_error
    assert any("No audit runs" in line for line in ctx.stdout_buffer)


@pytest.mark.asyncio
async def test_trend_renders_table():
    ctx = _make_ctx()
    ctx.orchestrator.get_trend.return_value = {
        "runs": [
            {"timestamp": "2026-06-14T10:00:00Z", "git_commit": "abc1234",
             "scores": {"overall": 88.0, "security": 84.0, "quality": 90.0},
             "counts": {"critical": 0, "high": 2}},
            {"timestamp": "2026-06-15T14:00:00Z", "git_commit": "def5678",
             "scores": {"overall": 82.4, "security": 78.1, "quality": 88.0},
             "counts": {"critical": 1, "high": 5}},
        ]
    }
    registry = CommandRegistry(MagicMock(), orchestrator=ctx.orchestrator)
    await registry.execute("audit:trend --last 2", ctx)
    assert not ctx.has_error
    assert any("88.0" in line for line in ctx.stdout_buffer)
    assert any("▼" in line for line in ctx.stdout_buffer)   # regression arrow


# ── fix:queue ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_queue_clean_project():
    ctx = _make_ctx()
    ctx.orchestrator.get_fix_queue.return_value = {"queue": [], "total": 0}
    registry = CommandRegistry(MagicMock(), orchestrator=ctx.orchestrator)
    await registry.execute("fix:queue", ctx)
    assert not ctx.has_error
    assert any("clean" in line for line in ctx.stdout_buffer)


@pytest.mark.asyncio
async def test_queue_renders_ranked_list():
    ctx = _make_ctx()
    ctx.orchestrator.get_fix_queue.return_value = {
        "total": 12,
        "queue": [
            {"rank": 1, "finding_hash": "a8f9c2b4d6e1", "rule_id": "SQL_INJECTION",
             "severity": "CRITICAL", "file_path": "src/auth/login.py",
             "age_days": 7, "score_impact": 14.1},
        ]
    }
    registry = CommandRegistry(MagicMock(), orchestrator=ctx.orchestrator)
    await registry.execute("fix:queue --severity CRITICAL --limit 1", ctx)
    assert not ctx.has_error
    assert any("SQL_INJECTION" in line for line in ctx.stdout_buffer)


# ── mcp:config ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mcp_config_writes_entry(tmp_path, monkeypatch):
    from core.primitives.commands.handlers import mcp as mcp_handler

    config_path = tmp_path / "claude_desktop_config.json"

    # Patch the config path resolution
    monkeypatch.setattr(
        mcp_handler,
        "_CONFIG_PATHS",
        {"claude": {"linux": config_path, "darwin": config_path, "win32": config_path}},
    )

    ctx = _make_ctx(privilege=3)  # ADMIN
    registry = CommandRegistry(MagicMock(), orchestrator=ctx.orchestrator)
    await registry.execute("mcp:config --host claude", ctx)

    assert not ctx.has_error
    written = json.loads(config_path.read_text())
    assert "nexus-audit-v3" in written["mcpServers"]
    assert written["mcpServers"]["nexus-audit-v3"]["args"] == ["-m", "nexus.mcp.server"]
```

---

## What the Orchestrator Must Expose

These are the five new methods the `Orchestrator` class must implement before these handlers can be wired:

```python
# orchestrator.py — new method signatures only

class Orchestrator:

    async def diff_runs(
        self,
        project_id: str,
        run_id_a: str | None = None,   # None → second-to-last
        run_id_b: str | None = None,   # None → latest
    ) -> dict: ...

    async def get_trend(
        self,
        project_id: str,
        last_n_runs: int = 10,
        branch: str | None = None,
    ) -> dict: ...

    async def export_audit(
        self,
        project_id: str,
        format: str = "sarif",         # "sarif" | "json" | "csv"
        since_days: int = 90,
        output_path: str | None = None,
    ) -> dict: ...                     # returns {"findings_count": N, "output_path": str}

    async def get_fix_queue(
        self,
        project_id: str,
        severity_floor: str = "HIGH",
        limit: int = 10,
    ) -> dict: ...                     # returns {"total": N, "queue": [...]}

    # mcp:config does not need Orchestrator — it writes a config file directly
```

These are the only new contracts. The MCP server tools defined in the MCP Server Specification call the same four `Orchestrator` methods (`diff_runs`, `get_trend`, `export_audit`, `get_fix_queue`) — they are implemented once and consumed by both interfaces.

---

*Nexus Audit V3 — CLI Extension Specification v1.0 · June 2026*  
*Three new handler files. One two-line change to `_register_all()`. No changes to existing handlers.*
