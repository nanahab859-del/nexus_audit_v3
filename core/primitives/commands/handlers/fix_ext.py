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
    if not ctx.active_project:
        ctx.write_error("No active project. Run 'workspace:active <id>' first.")
        return

    severity = params.get("severity", "HIGH")
    limit    = min(params.get("limit", 10), 50)

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
        sev    = item.get("severity", "UNKNOWN")
        rule   = item.get("rule_id", "Unknown")[:35]
        fpath  = item.get("file_path", "Unknown")[-30:]
        age    = item.get("age_days", 0)
        impact = item.get("score_impact", 0.0)

        ctx.write(
            f"  {i:>3}  {sev:<10}  {rule:<36}  {fpath:<30}  {age:>4}d  -{impact:>6.1f}"
        )

    if items:
        top_hash = items[0].get("finding_hash", "Unknown")
        ctx.write("")
        ctx.write(f"→ Inspect top finding: audit:diff  (hash: {top_hash[:12]}...)")
        ctx.write(f"  Snooze it:           fix:apply --snooze {top_hash[:12]} 30d")
