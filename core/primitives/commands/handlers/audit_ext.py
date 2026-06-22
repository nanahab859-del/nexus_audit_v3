from __future__ import annotations

import sys
from core.primitives.commands.context import OPERATOR, READONLY

def register(registry) -> None:
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

async def _handle_diff(ctx, params) -> None:
    if not ctx.active_project:
        ctx.write_error("No active project. Run 'workspace:active <id>' first.")
        return

    run_a = params.get("run_a")
    run_b = params.get("run_b")

    try:
        diff = await ctx.orchestrator.diff_runs(
            project_id=ctx.active_project.id,
            run_id_a=run_a,
            run_id_b=run_b,
        )
    except ValueError as e:
        ctx.write_error(str(e))
        return

    d = diff["score_delta"]
    ctx.write(f"\nRuns:  {diff['run_id_a']}")
    ctx.write(f"    →  {diff['run_id_b']}")
    ctx.write("")
    ctx.write(
        f"Score delta:  overall {d['overall']:+.1f}"
        f"  (security {d['security']:+.1f} | quality {d['quality']:+.1f})"
    )

    new = diff["new_findings"]
    res = diff["resolved_findings"]
    sev = new.get("by_severity", {})

    ctx.write("")
    ctx.write(
        f"New findings:      {new['count']}"
        + (f"  [CRITICAL: {sev.get('CRITICAL', 0)}  HIGH: {sev.get('HIGH', 0)}]" if new["count"] else "")
    )
    ctx.write(f"Resolved findings: {res['count']}")

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

    if diff.get("probable_commit"):
        ctx.write("")
        ctx.write(f"Probable cause: commit {diff['probable_commit']}")

    if new["count"] > 0:
        ctx.write("")
        ctx.write("→ Run 'fix:queue' to see prioritised findings.")


async def _handle_trend(ctx, params) -> None:
    if not ctx.active_project:
        ctx.write_error("No active project. Run 'workspace:active <id>' first.")
        return

    last_n = min(params.get("last", 10), 50)
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
    if not ctx.active_project:
        ctx.write_error("No active project. Run 'workspace:active <id>' first.")
        return

    fmt       = params.get("format", "sarif")
    since_raw = params.get("since", "90d")
    output    = params.get("output")

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

    if fmt == "sarif":
        ctx.write("")
        ctx.write("Upload to GitHub Code Scanning:")
        ctx.write(f"  gh api /repos/OWNER/REPO/code-scanning/sarifs \\")
        ctx.write(f"      -F sarif=@{result['output_path']}")
        ctx.write("")
        ctx.write("Or commit and let your CI workflow upload automatically.")
