# Nexus Audit V3 — Plugin Development Guide

This document explains the three ways to add scanner capability to Nexus Audit V3.

---

## Case 1 — Plugin file exists, tool not installed

This is the normal path for built-in scanners like **Bandit** and **Vulture**.

A `.py` plugin file already exists in `plugins/security/` or `plugins/quality/`.  
The backend knows about the scanner but the executable is not on `PATH`.

**Resolution:**

1. Open **Settings → Scanners**.
2. Find the scanner card showing **⚠ Not Installed**.
3. Click **⬇ Install**. Live pip output streams to the UI.
4. When the badge changes to **✅ Installed**, toggle the scanner **ON**.
5. Run an audit — no restart required.

---

## Case 2 — Writing a New Plugin File

Use this when you want Nexus to drive a tool that doesn't have a plugin yet
(e.g., `radon`, `pylint`, `semgrep`).

### 2.1 Create the plugin file

```
plugins/
  quality/
    radon_plugin.py    ← new file here
  security/
    bandit_plugin.py
```

### 2.2 Implement `BaseScanner`

```python
# plugins/quality/radon_plugin.py
from __future__ import annotations
import asyncio
import json
from pathlib import Path
from typing import List

from plugins.base import BaseScanner
from core.models import Finding, Category, Severity, Persistence, FixStatus
from core.events import EventBus


class RadonScanner(BaseScanner):
    name      = "radon"              # must be unique across all plugins
    version   = "1.0.0"
    languages = ["Python"]
    category  = Category.QUALITY
    timeout   = 120

    async def scan(
        self,
        target: Path,
        config: dict,
        bus: EventBus,
    ) -> List[Finding]:
        findings: List[Finding] = []

        await bus.publish_log("info", "[radon] Starting complexity scan...")
        await bus.publish_progress("radon", 10, str(target))

        proc = await asyncio.create_subprocess_exec(
            "radon", "cc", str(target), "--json", "-a",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)

        try:
            results = json.loads(stdout.decode())
        except Exception:
            await bus.publish_progress("radon", 100, str(target))
            return findings

        for file_path, blocks in results.items():
            for block in blocks:
                rank = block.get("rank", "A")
                if rank in ("D", "E", "F"):
                    sev = Severity.HIGH if rank == "F" else Severity.MEDIUM
                    findings.append(Finding(
                        id=f"radon-{file_path}-{block['lineno']}",
                        scanner="radon",
                        file=file_path,
                        line=block["lineno"],
                        column=0,
                        severity=sev,
                        category=self.category,
                        title=f"High complexity: {block['name']} (rank {rank})",
                        description=f"Cyclomatic complexity rank {rank} "
                                    f"(complexity={block['complexity']})",
                        suggestion="Refactor to reduce complexity below rank C.",
                        persistence=Persistence.NEW,
                        fix_status=FixStatus.OPEN,
                    ))

        await bus.publish_progress("radon", 100, str(target))
        await bus.publish_log("info", f"[radon] Found {len(findings)} issues")
        return findings
```

### 2.3 Required class attributes

| Attribute    | Type        | Required | Description                                              |
|--------------|-------------|----------|----------------------------------------------------------|
| `name`       | `str`       | yes      | Unique scanner key (lowercase, hyphens ok)               |
| `version`    | `str`       | yes      | Plugin version string                                    |
| `languages`  | `list[str]` | yes      | Language tags, or `["*"]` for all                        |
| `category`   | `Category`  | yes      | QUALITY, SECURITY, DEPENDENCY, ARCHITECTURE, PERFORMANCE |
| `timeout`    | `int`       | optional | Max seconds for subprocess (default 300)                 |
| `is_internal`| `bool`      | optional | Set True to hide from the UI                             |

### 2.4 Pick up the new plugin without restarting

1. Drop the `.py` file into `plugins/` (or a subdirectory with an `__init__.py`).
2. Open **Settings → Scanners** and click **Refresh**.
3. The new scanner appears instantly.

---

## Case 3 — Custom Script (No Python Required)

### 3.1 Script output format

Default pattern (one finding per line):

```
SEVERITY:relative/file/path.py:LINE:Message text here
```

SEVERITY must be: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, or `INFO`.

### 3.2 Register via the UI

1. Open **Settings → Scanners** and click **Add Custom Plugin**.
2. Fill in: Scanner Name, Executable Path, Output Pattern (optional regex).
3. Click **Register Scanner**.
4. Toggle it ON and run an audit.

### 3.3 Internal behaviour

The executable is called with the target path as its only argument:

```bash
/path/to/my-script /home/user/project
```

---

## BaseScanner Interface

```python
class BaseScanner(ABC):
    name:      str
    version:   str
    languages: list[str]
    category:  Category
    timeout:   int = 300

    @abstractmethod
    async def scan(self, target: Path, config: dict, bus: EventBus) -> list[Finding]:
        ...
```

`config` dict keys available in `scan()`:

| Key               | Type              | Description                          |
|-------------------|-------------------|--------------------------------------|
| `strictness`      | `str`             | "Low", "Medium", or "High"           |
| `exclude_paths`   | `list[str]`       | Path prefixes to skip                |
| `skip_checks`     | `list[str]`       | Check IDs to suppress                |
| `_file_filter`    | `Callable`        | `(Path) -> bool` — use to skip files |

---

## EventBus Methods

```python
await bus.publish_log("info"|"warning"|"error"|"debug", "message")
await bus.publish_progress(scanner_name, percent_0_to_100, current_file)
```

Always call `publish_progress(name, 100, ...)` before returning.
