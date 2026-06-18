"""Report generation command handlers."""
from __future__ import annotations
from pathlib import Path
from core.primitives.commands.context import READONLY, OPERATOR


def register(registry) -> None:
    from core.primitives.commands.registry import Command
    from core.primitives.commands.parser import CommandParser

    registry.register(Command(
        name="report:generate",
        description="Generate a report from the latest (or a specified) audit run.",
        usage="report:generate [--format md|json] [--output PATH] [--job JOB_ID]",
        handler=_handle_generate,
        required_privilege=OPERATOR,
        parser=(
            CommandParser("report:generate")
            .add_argument("--format", default="md", choices=["md", "json"])
            .add_argument("--output", default=None,
                          help="Write to this path (default: auto-named)")
            .add_argument("--job",    default=None,
                          help="Job ID to report on (default: latest)")
        ),
    ))

    registry.register(Command(
        name="report:history",
        description="List previously generated reports for the active project.",
        usage="report:history [--limit N]",
        handler=_handle_history,
        required_privilege=READONLY,
        parser=CommandParser("report:history")
                   .add_argument("--limit", type=int, default=10),
    ))


async def _handle_generate(ctx, params) -> None:
    if not ctx.active_project:
        ctx.write_error("No active project. Run 'workspace:active <id>' first.")
        return

    from core.reports import ReportEngine
    engine = ReportEngine(Path.home() / ".nexus_audit" / "projects")

    output = params.get("output")

    try:
        written = await engine.generate(
            project_id=ctx.active_project.id,
            project_name=ctx.active_project.name,
            fmt=params.get("format", "md"),
            output_path=Path(output) if output else None,
            job_id=params.get("job"),
        )
        ctx.write(f"Report generated: {written}")
    except FileNotFoundError as e:
        ctx.write_error(str(e))
    except ValueError as e:
        ctx.write_error(str(e))


async def _handle_history(ctx, params) -> None:
    if not ctx.active_project:
        ctx.write_error("No active project.")
        return

    from core.reports import ReportEngine
    engine  = ReportEngine(Path.home() / ".nexus_audit" / "projects")
    reports = await engine.list_reports(ctx.active_project.id)

    if not reports:
        ctx.write("No reports found. Run 'report:generate' after an audit.")
        return

    ctx.write(f"  {'NAME':<50} {'SIZE':>8}")
    ctx.write(f"  {'─'*50} {'─'*8}")
    for r in reports[:params.get("limit", 10)]:
        size_kb = r.stat().st_size / 1024
        ctx.write(f"  {r.name:<50} {size_kb:>6.1f}k")
