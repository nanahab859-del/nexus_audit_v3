"""JSON report generator for audit results."""
from __future__ import annotations
import json
from pathlib import Path


def generate_json_report(
    result_data: dict,
    project_name: str,
    output_path: Path,
) -> None:
    """
    Write the full audit result as formatted JSON.

    Output is a superset of audit_data_complete.json with `project_name`
    injected at the top level for readability. Suitable for CI consumption,
    diffs between runs, or external dashboards.
    """
    report = {"project_name": project_name, **result_data}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, default=str),
        encoding="utf-8",
    )
