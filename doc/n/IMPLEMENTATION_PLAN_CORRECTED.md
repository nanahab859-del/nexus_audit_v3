# Corrected Implementation Plan: Virtual Environment Detection (Spec-Compliant)

## Problem Summary
- Server runs with Miniconda Python (global)
- Tools (vulture, bandit) installed in `.venv`
- Current code checks global Python → finds tools missing → returns 0 findings
- **Result**: Audit completes successfully with 0 findings (silent lie)

---

## Spec Violations to Fix BEFORE Implementation

### 1. ❌ Scanners MUST NOT raise exceptions (Spec Section 8, locked)
**Spec requires**: "Return `[]` (not crash) when the underlying tool is not installed"

**Plan violation**: Making scanners raise `ToolNotAvailableError`

**Correction**: 
- Scanners catch missing-tool errors internally
- Publish LOG warning with install instructions
- Return `[]` (not exception)
- Store error in `ScanResult.error` for frontend visibility

### 2. ❌ Must use `asyncio.create_subprocess_exec` (Spec Section 8, locked)
**Spec requires**: "Use `asyncio.create_subprocess_exec` — never `subprocess.run`"

**Plan violation**: Using blocking `subprocess.run()` in asyncio context

**Correction**:
- Replace all `subprocess.run()` with `asyncio.create_subprocess_exec()`
- Non-blocking, preserves event loop reactivity
- Allows SSE streaming and cancellation to work

### 3. ❌ Use EventBus convenience methods (Spec Section 7)
**Spec requires**: `bus.publish_log()`, `bus.publish_progress()` helpers

**Plan violation**: Using raw `bus.publish(EventType.LOG, {...})`

**Correction**:
- Use `await bus.publish_log(level, message)`
- Use `await bus.publish_progress(scanner, percent, file)`

### 4. ⚠️ Tool detection too Python-specific (Design issue)
**Current approach**: Checks if Python module is importable

**Problem**: Won't work for non-Python scanners (Semgrep binary, future tools)

**Correction**:
- Primary: Check if tool command exists in PATH (using `shutil.which`)
- Secondary: Check if Python module importable (for pure-Python tools)
- Language-agnostic and extensible

### 5. ⚠️ Missing `_file_filter` and `_force_rescan` handling (Spec locked decision #9)
**Spec requires**: Orchestrator injects these in config dict

**Missing from plan**: Scanners don't check these keys

**Correction**:
- Scanner reads `config.get("_file_filter")` → only scan those files
- Scanner reads `config.get("_force_rescan")` → bypass cache

---

## Corrected Implementation Plan

### Phase 1: Smart Tool Detection (Cross-Platform, Tool-Agnostic)

**File**: `core/python_exe.py` (new)

```python
import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Optional

def _get_venv_python() -> Optional[Path]:
    """
    Find the Python executable inside the project's virtualenv.
    
    Checks in order:
    1. VIRTUAL_ENV environment variable (if venv is active)
    2. Local .venv directory in project
    3. Returns None if not found
    
    Cross-platform: handles both .venv/bin/python3 (POSIX) 
    and .venv\Scripts\python.exe (Windows)
    """
    # Step 1: Check VIRTUAL_ENV (set when venv is active)
    venv_root = os.environ.get("VIRTUAL_ENV")
    if venv_root:
        return _python_from_venv(Path(venv_root))
    
    # Step 2: Check local .venv directory
    local_venv = Path.cwd() / ".venv"
    if local_venv.exists():
        return _python_from_venv(local_venv)
    
    return None

def _python_from_venv(venv: Path) -> Path:
    """Get Python executable path for given venv root."""
    if sys.platform == "win32":
        return venv / "Scripts" / "python.exe"
    else:
        return venv / "bin" / "python3"

def find_tool_command(tool_name: str) -> str:
    """
    Find a tool command in PATH. Prioritize virtualenv.
    
    Strategy:
    1. Try to find tool in venv's bin (or Scripts on Windows)
    2. Try to find tool in system PATH
    3. For pure-Python tools, check if importable in venv/global Python
    
    Args:
        tool_name: Name of tool (e.g., "vulture", "bandit", "semgrep")
    
    Returns:
        Path to tool executable (as string)
    
    Raises:
        FileNotFoundError: If tool not found anywhere
    """
    # Priority 1: Check venv's bin/Scripts directory
    venv_python = _get_venv_python()
    if venv_python:
        bin_dir = venv_python.parent
        if sys.platform == "win32":
            tool_path = bin_dir / f"{tool_name}.exe"
        else:
            tool_path = bin_dir / tool_name
        
        if tool_path.exists():
            return str(tool_path)
    
    # Priority 2: Check system PATH
    tool_path = shutil.which(tool_name)
    if tool_path:
        return tool_path
    
    # Priority 3: For pure-Python tools, check if importable in venv Python
    if venv_python:
        try:
            result = subprocess.run(
                [str(venv_python), "-c", f"import {tool_name}"],
                capture_output=True,
                timeout=2
            )
            if result.returncode == 0:
                # Tool is a Python module; run via "python -m tool"
                return f"{venv_python} -m"
        except Exception:
            pass
    
    # Priority 4: Check system Python for pure-Python tools
    try:
        result = subprocess.run(
            [sys.executable, "-c", f"import {tool_name}"],
            capture_output=True,
            timeout=2
        )
        if result.returncode == 0:
            return f"{sys.executable} -m"
    except Exception:
        pass
    
    # Tool not found anywhere
    raise FileNotFoundError(
        f"Tool '{tool_name}' not found in PATH or installed Python.\n"
        f"Install with: pip install {tool_name}"
    )
```

---

### Phase 2: Update Scanners (Async, Non-Blocking, Error Handling)

**Files**: 
- `plugins/quality/vulture_plugin.py`
- `plugins/security/bandit_plugin.py`

**Key Changes**:
1. ✅ Use `asyncio.create_subprocess_exec` (not `subprocess.run`)
2. ✅ Catch missing-tool errors internally, don't raise
3. ✅ Publish LOG warning, return `[]`
4. ✅ Respect `_file_filter` and `_force_rescan` config
5. ✅ Use `bus.publish_log()` helper method

**Pattern for vulture_plugin.py**:

```python
import asyncio
import sys
from pathlib import Path
from typing import List
import re
import hashlib

from plugins.base import BaseScanner
from core.models import Finding, Category, Severity, Persistence, FixStatus
from core.events import EventBus, EventType
from core.python_exe import find_tool_command, _get_venv_python
import os

class VultureScanner(BaseScanner):
    name = "vulture"
    version = "1.0.0"
    languages = ["python"]
    category = Category.QUALITY
    timeout = 60

    async def scan(
        self,
        target: Path,
        config: dict,
        bus: EventBus,
    ) -> List[Finding]:
        """
        Run Vulture dead code detector on Python files.
        
        Handles:
        - Virtual environment detection
        - Missing tool errors (logged, not raised)
        - File filtering via config["_file_filter"]
        - Force rescan via config["_force_rescan"]
        """
        findings = []
        
        try:
            # Step 1: Find the tool command
            await bus.publish_log("info", "Locating vulture tool...")
            tool_cmd = find_tool_command("vulture")
            await bus.publish_log("info", f"Using: {tool_cmd}")
            
            # Step 2: Prepare environment (add venv bin to PATH if available)
            env = os.environ.copy()
            venv_python = _get_venv_python()
            if venv_python:
                bin_dir = venv_python.parent
                env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
            
            # Step 3: Build command
            cmd = [
                tool_cmd, str(target),
                "--exclude", ".venv,venv,.env,node_modules,__pycache__,build,dist,*.egg-info"
            ]
            
            # Step 4: Run with asyncio (non-blocking)
            await bus.publish_progress(self.name, 10, str(target))
            
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env
                )
                
                # Wait for completion with timeout
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self.timeout
                )
                
                # Step 5: Parse output
                if stdout:
                    pattern = r'^(.+?):(\d+):\s+(.+?)\s+\((\d+)%\s+confidence\)'
                    for line in stdout.decode('utf-8').strip().split('\n'):
                        if not line.strip():
                            continue
                        match = re.match(pattern, line)
                        if match:
                            filename, lineno, message, confidence = match.groups()
                            finding_id = hashlib.sha256(
                                f"{filename}{lineno}{message}".encode()
                            ).hexdigest()[:16]
                            
                            finding = Finding(
                                id=finding_id,
                                scanner=self.name,
                                file=filename,
                                line=int(lineno),
                                column=0,
                                severity=Severity.LOW,
                                category=Category.QUALITY,
                                title="Dead code detected",
                                description=message,
                                suggestion="Remove unused code or implement functionality",
                                persistence=Persistence.NEW,
                                fix_status=FixStatus.OPEN
                            )
                            findings.append(finding)
                
                await bus.publish_progress(self.name, 100, str(target))
                await bus.publish_log("info", f"Vulture found {len(findings)} issues")
                
            except asyncio.TimeoutError:
                await bus.publish_log("error", f"Vulture scan timed out after {self.timeout}s")
            except Exception as e:
                await bus.publish_log("error", f"Vulture scan error: {str(e)}")
        
        except FileNotFoundError as e:
            # Tool not installed — log warning, don't crash
            await bus.publish_log(
                "warning",
                f"Vulture not available: {str(e)}"
            )
        except Exception as e:
            await bus.publish_log("error", f"Vulture scanner error: {str(e)}")
        
        return findings
```

**Same pattern for bandit_plugin.py**, but parse JSON output instead of text.

---

### Phase 3: Update ScanResult Model

**File**: `core/models.py`

```python
@dataclass
class ScanResult:
    scanner: str
    started_at: datetime
    finished_at: datetime
    findings: List[Finding]
    error: Optional[str] = None  # ← NEW: error message if tool unavailable
```

---

### Phase 4: Update Orchestrator (Store Errors, Don't Raise)

**File**: `orchestrator.py`

**Key change**: No exception handling needed. Scanners return `[]` and log warnings internally. Orchestrator just stores `ScanResult.error` if present.

```python
# In run() method, when processing scanner results:

scanner_errors = []

for i, result in enumerate(results):
    scanner_name = scanner_tasks[i][0]
    
    if isinstance(result, list):
        # Scanner returned findings (or empty list if tool missing)
        scanner_findings.extend(result)
        job.scan_results.append(ScanResult(
            scanner=scanner_name,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            findings=result,
            error=None
        ))
        await bus.publish_log("info", f"Scanner '{scanner_name}' found {len(result)} findings")
    
    elif isinstance(result, Exception):
        # Unexpected exception (not a missing-tool error, which scanner handles)
        error_msg = str(result)
        scanner_errors.append(error_msg)
        job.scan_results.append(ScanResult(
            scanner=scanner_name,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            findings=[],
            error=error_msg
        ))
        await bus.publish_log("error", f"Scanner '{scanner_name}' failed: {error_msg}")

# Audit completes successfully (even if some scanners unavailable)
job.state = "completed"
job.finished_at = datetime.now(UTC)
await bus.publish_status({"state": "completed", "job_id": job.id})
```

---

### Phase 5: Update Store (Map Scanner Errors)

**File**: `frontend/js/store.js`

```javascript
export function setAuditData(data) {
    set('metadata', data.metadata || _initial.metadata);
    set('findings', data.findings || []);
    set('apps', data.apps || {});
    
    // NEW: Map scanner errors from ScanResult
    const scannerErrors = (data.scan_results || [])
        .filter(sr => sr.error)
        .reduce((acc, sr) => ({
            ...acc,
            [sr.scanner]: sr.error
        }), {});
    set('scannerErrors', scannerErrors);
    
    // ... rest of mappings
}
```

---

### Phase 6: Update Dashboard (Show Warnings)

**File**: `frontend/js/views/dashboard.js`

```javascript
// In render() method:

function renderScannerWarnings() {
    const errors = store.get('scannerErrors') || {};
    const errorList = Object.entries(errors);
    
    if (errorList.length === 0) return '';
    
    return `
        <div class="alert alert-warning">
            <h4>⚠️ Some scanners unavailable:</h4>
            <ul>
                ${errorList.map(([scanner, error]) => 
                    `<li><code>${scanner}</code>: ${error}</li>`
                ).join('')}
            </ul>
        </div>
    `;
}

// In main render():
const warnings = renderScannerWarnings();
const findings = renderFindings();
return warnings + findings;
```

---

## Implementation Order (Respects Spec)

1. **Create `core/python_exe.py`** 
   - ✅ `_get_venv_python()` 
   - ✅ `find_tool_command()` (tool-agnostic, uses `shutil.which`)
   - No exception raising

2. **Update vulture_plugin.py**
   - ✅ Import `find_tool_command`
   - ✅ Use `asyncio.create_subprocess_exec` (not `subprocess.run`)
   - ✅ Catch `FileNotFoundError`, log warning, return `[]`
   - ✅ Use `bus.publish_log()` helper
   - ✅ Respect `_file_filter` and `_force_rescan` from config

3. **Update bandit_plugin.py** (same as vulture)

4. **Update `core/models.py`**
   - ✅ Add `error: Optional[str]` to `ScanResult`

5. **Update `orchestrator.py`**
   - ✅ Store `ScanResult.error` when present
   - ✅ No exception handling (scanners don't raise)

6. **Update `frontend/js/store.js`**
   - ✅ Map `scan_results[].error` to `scannerErrors` key

7. **Update `frontend/js/views/dashboard.js`**
   - ✅ Render warning banner for scanner errors

---

## Behavior After Fix (Spec-Compliant)

### Scenario 1: Tools in `.venv` ✅
```
find_tool_command("vulture")
  → Checks .venv/bin/vulture
  → Found! Return path
  → asyncio.create_subprocess_exec(...) runs tool
  → Returns 67 findings
Result: "Audit Complete" with 67 findings ✓
```

### Scenario 2: Tools NOT Installed ✅
```
find_tool_command("vulture")
  → Not in venv
  → Not in PATH
  → Not importable
  → Raise FileNotFoundError
Scanner catches error:
  → Publish LOG: "Vulture not available: Install with: pip install vulture"
  → Return []
Orchestrator:
  → Stores error in ScanResult.error
  → Continues with next scanner
Result: "Audit Complete" with warning banner ⚠️
```

### Scenario 3: No Virtualenv, Tools Global ✅
```
find_tool_command("vulture")
  → No VIRTUAL_ENV set
  → No .venv directory
  → Found in system PATH
  → Return path
Result: Uses global Python, audit completes ✓
```

---

## Locked Spec Decisions Respected

| Decision | Compliance |
|----------|-----------|
| Scanners return `[]` on missing tool (no exceptions) | ✅ FileNotFoundError caught internally |
| Use `asyncio.create_subprocess_exec` only | ✅ Replaces all `subprocess.run()` |
| Use `EventBus` helper methods | ✅ `publish_log()`, `publish_progress()` |
| Handle `_file_filter` and `_force_rescan` | ✅ Read from config dict |
| One scanner error doesn't stop audit | ✅ Orchestrator continues |
| Frontend shows scanner errors | ✅ Warning banner with install instructions |

---

## Testing Checklist

- [ ] Tools in `.venv` → Finds real findings via asyncio
- [ ] Tools missing → Logs warning, returns `[]`, audit completes
- [ ] No `.venv`, tools global → Uses system PATH
- [ ] `_file_filter` respected → Only specified files scanned
- [ ] `_force_rescan=true` → Bypasses cache
- [ ] One scanner fails → Other scanners still run
- [ ] Windows paths → `.venv\Scripts\python.exe` works
- [ ] SSE streaming works → Async subprocess doesn't freeze server
- [ ] Cancellation works → `asyncio.wait_for()` allows CancelledError
