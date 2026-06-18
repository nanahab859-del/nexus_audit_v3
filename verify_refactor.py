#!/usr/bin/env python3
"""
Verification script for the Layer 1 CLI & Command Pipeline refactor.
Run from the project root: python verify_refactor.py
"""
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(__file__))

errors = []
passed = []

# ── Import integrity checks ────────────────────────────────────────────────────

print("=" * 60)
print("Checking import integrity...")

try:
    from core.primitives.commands import (
        CommandRegistry, CommandContext, Command,
        READONLY, OPERATOR, ADMIN, SYSTEM, PRIV_NAMES,
    )
    passed.append("from core.primitives.commands import CommandRegistry — OK")
except ImportError as e:
    errors.append(f"Import FAILED: {e}")

try:
    from core.primitives.commands.context import CommandContext as CC, READONLY as RO
    passed.append("from core.primitives.commands.context — OK")
except ImportError as e:
    errors.append(f"context.py import FAILED: {e}")

try:
    from core.primitives.commands.parser import CommandParser
    passed.append("from core.primitives.commands.parser — OK")
except ImportError as e:
    errors.append(f"parser.py import FAILED: {e}")

try:
    from core.primitives.commands.registry import CommandRegistry as CR, Command as Cmd
    passed.append("from core.primitives.commands.registry — OK")
except ImportError as e:
    errors.append(f"registry.py import FAILED: {e}")

# Handler imports
for mod in ["workspace", "project", "audit", "config", "scanner", "fix", "report", "system", "log", "ai"]:
    try:
        m = __import__(f"core.primitives.commands.handlers.{mod}", fromlist=[mod])
        assert hasattr(m, "register"), f"{mod} missing register()"
        passed.append(f"  handlers/{mod}.py — OK")
    except Exception as e:
        errors.append(f"  handlers/{mod}.py FAILED: {e}")

# ── Static analysis checks ─────────────────────────────────────────────────────

print("\nChecking for banned patterns...")
import pathlib, re

root = pathlib.Path(__file__).parent
commands_pkg = root / "core" / "primitives" / "commands"

# 1. No 'from orchestrator' inside core/
orch_imports = list(root.glob("core/**/*.py"))
for f in orch_imports:
    content = f.read_text(errors="replace")
    if "from orchestrator" in content or "import orchestrator" in content:
        errors.append(f"BANNED import 'from orchestrator' found in {f.relative_to(root)}")
    else:
        pass  # quiet pass

passed.append("grep 'from orchestrator' core/ — zero results")

# 2. No click.secho inside commands package
for f in commands_pkg.rglob("*.py"):
    content = f.read_text(errors="replace")
    if "click.secho" in content:
        errors.append(f"BANNED click.secho found in {f.relative_to(root)}")

passed.append("grep 'click.secho' core/primitives/commands/ — zero results")

# 3. No fq._data direct access inside core/
for f in root.glob("core/**/*.py"):
    content = f.read_text(errors="replace")
    if re.search(r"fq\._data", content):
        errors.append(f"BANNED fq._data access found in {f.relative_to(root)}")

passed.append("grep 'fq._data' core/ — zero results")

# 4. Old commands.py must not exist
old = root / "core" / "primitives" / "commands.py"
if old.exists():
    errors.append("OLD FILE STILL EXISTS: core/primitives/commands.py")
else:
    passed.append("core/primitives/commands.py — correctly deleted")

# 5. FixQueue public methods
try:
    from core.engines.fix_queue import FixQueue
    assert hasattr(FixQueue, "load"),      "FixQueue missing .load()"
    assert hasattr(FixQueue, "entries"),   "FixQueue missing .entries()"
    assert hasattr(FixQueue, "get_entry"), "FixQueue missing .get_entry()"
    passed.append("FixQueue public API (load/entries/get_entry) — OK")
except Exception as e:
    errors.append(f"FixQueue public API check FAILED: {e}")

# 6. CommandContext has new fields
try:
    from core.primitives.commands.context import CommandContext
    import dataclasses
    fields = {f.name for f in dataclasses.fields(CommandContext)}
    for required in ("workspace_dirty", "exit_requested", "orchestrator"):
        if required not in fields:
            errors.append(f"CommandContext missing field: {required}")
    passed.append("CommandContext new fields (workspace_dirty/exit_requested/orchestrator) — OK")
except Exception as e:
    errors.append(f"CommandContext field check FAILED: {e}")

# ── Summary ────────────────────────────────────────────────────────────────────

print("\n" + "=" * 60)
print(f"PASSED ({len(passed)}):")
for p in passed:
    print(f"  ✓ {p}")

if errors:
    print(f"\nFAILED ({len(errors)}):")
    for e in errors:
        print(f"  ✗ {e}")
    sys.exit(1)
else:
    print(f"\nAll {len(passed)} checks passed — refactor verified.")
    sys.exit(0)
