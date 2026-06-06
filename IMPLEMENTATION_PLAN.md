# Implementation Plan: Robust Virtual Environment Detection

## Problem Summary
- Server runs with Miniconda Python (global)
- Tools (vulture, bandit) installed in `.venv`
- Current code checks global Python → finds tools missing → returns 0 findings
- **Result**: Audit completes successfully with 0 findings (silent lie)

---

## Solution Overview

### Phase 1: Smart Python Detection (Prioritise `.venv`)
**Goal**: Find the correct Python executable that has scanner tools

**Requirements**:
- ✓ Check `VIRTUAL_ENV` environment variable first (if server running in venv)
- ✓ Check local `.venv` in project directory
- ✓ Cross-platform support (POSIX and Windows paths)
- ✓ Fall back to `sys.executable` (global Python) if no venv
- ✓ Fail loudly if tool not found anywhere

**Files to change**:
- `core/python_exe.py` - New helper functions

**Code changes**:
```python
# core/python_exe.py

def _get_venv_python() -> Path | None:
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

def find_python_with_module(module_name: str) -> str:
    """
    Find a Python executable that has the required module installed.
    
    Returns:
        Path to Python executable (as string)
    
    Raises:
        ToolNotAvailableError: If module not found in any Python
    """
    candidates = []
    
    # Priority 1: Virtual environment Python
    venv_python = _get_venv_python()
    if venv_python:
        candidates.append(venv_python)
    
    # Priority 2: Global/system Python
    candidates.append(Path(sys.executable))
    
    # Try each candidate
    for python_path in candidates:
        if not python_path.exists():
            continue
        
        try:
            result = subprocess.run(
                [str(python_path), "-c", f"import {module_name}"],
                capture_output=True,
                timeout=2
            )
            if result.returncode == 0:
                return str(python_path)  # ✓ Found!
        except Exception:
            continue
    
    # Not found anywhere → Raise clear error
    raise ToolNotAvailableError(
        f"Required tool '{module_name}' not found.\n"
        f"Install with: pip install {module_name}"
    )

class ToolNotAvailableError(Exception):
    """Raised when a required scanner tool is not installed."""
    pass
```

---

### Phase 2: Scanners Raise Errors (Don't Silently Return [])
**Goal**: Make scanner failures visible instead of silent

**Requirements**:
- ✓ Use `find_python_with_module()` to get correct Python
- ✓ Raise `ToolNotAvailableError` if tool not found
- ✓ Let exception propagate to orchestrator
- ✓ Don't catch and swallow the error

**Files to change**:
- `plugins/quality/vulture_plugin.py`
- `plugins/security/bandit_plugin.py`

**Code pattern for both scanners**:
```python
# In vulture_plugin.py and bandit_plugin.py

async def scan(self, target: Path, config: dict, bus: EventBus) -> List[Finding]:
    try:
        # Step 1: Find Python that has the tool
        python_exe = find_python_with_module(self.name)
        
        await bus.publish(EventType.LOG, {
            "level": "info",
            "message": f"Using Python: {python_exe}"
        })
        
        # Step 2: Prepare environment with venv's bin in PATH
        env = os.environ.copy()
        venv_python = _get_venv_python()
        if venv_python:
            # Add venv's bin directory to PATH
            bin_dir = venv_python.parent
            env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
        
        # Step 3: Run scanner with correct Python
        result = subprocess.run(
            [python_exe, "-m", self.name, str(target), ...],
            capture_output=True,
            text=True,
            env=env,  # ← Use modified environment
            timeout=self.timeout
        )
        
        # Step 4: Parse and return findings (or empty list)
        # ... existing parsing logic ...
        return findings
        
    except ToolNotAvailableError as e:
        # Let this propagate! Don't catch it.
        raise
    except subprocess.TimeoutExpired:
        await bus.publish(EventType.LOG, {
            "level": "error",
            "message": f"Scanner '{self.name}' timed out"
        })
        return []
    except Exception as e:
        await bus.publish(EventType.LOG, {
            "level": "error",
            "message": f"Scanner '{self.name}' error: {str(e)}"
        })
        return []
```

---

### Phase 3: Orchestrator Handles Scanner Errors Gracefully
**Goal**: Catch tool-not-available errors, record them, continue with other scanners

**Requirements**:
- ✓ Catch `ToolNotAvailableError` separately from other exceptions
- ✓ Store error message in `ScanResult`
- ✓ Continue running other scanners (don't stop entire audit)
- ✓ Mark audit as `completed` (with warnings, not `failed`)
- ✓ Frontend shows which scanners had errors

**Files to change**:
- `core/models.py` - Add `error` field to `ScanResult`
- `orchestrator.py` - Handle errors gracefully

**Code changes for orchestrator.py**:
```python
from core.python_exe import ToolNotAvailableError

# In run() method, when processing scanner results:

scanner_errors = []  # Track which scanners had errors

for i, result in enumerate(results):
    scanner_name = scanner_tasks[i][0]
    
    if isinstance(result, list):
        # ✓ Successful: findings returned
        scanner_findings.extend(result)
        job.scan_results.append(ScanResult(
            scanner=scanner_name,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            findings=result,
            error=None  # No error
        ))
        await bus.publish(EventType.LOG, {
            "level": "info",
            "message": f"Scanner '{scanner_name}' found {len(result)} findings"
        })
    
    elif isinstance(result, Exception):
        error_msg = str(result)
        
        if isinstance(result, ToolNotAvailableError):
            # Tool not available — important error to show user
            scanner_errors.append(error_msg)
            job.scan_results.append(ScanResult(
                scanner=scanner_name,
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
                findings=[],
                error=error_msg  # ← Store error for frontend
            ))
            await bus.publish(EventType.LOG, {
                "level": "error",
                "message": f"Scanner '{scanner_name}': {error_msg}"
            })
        else:
            # Other errors — still record but less critical
            job.scan_results.append(ScanResult(
                scanner=scanner_name,
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
                findings=[],
                error=error_msg
            ))
            await bus.publish(EventType.LOG, {
                "level": "error",
                "message": f"Scanner '{scanner_name}' failed: {error_msg}"
            })

# After all scanners complete:

if scanner_errors:
    await bus.publish(EventType.LOG, {
        "level": "warning",
        "message": f"Audit completed with {len(scanner_errors)} scanner error(s):\n" + 
                   "\n".join(scanner_errors)
    })

# Mark audit as completed (with warnings if there were errors)
job.state = "completed"
job.finished_at = datetime.now(UTC)
await bus.publish(EventType.STATUS, {
    "state": "completed",
    "job_id": job.id,
    "warnings": len(scanner_errors)
})
```

**Update ScanResult model** (core/models.py):
```python
@dataclass
class ScanResult:
    scanner: str
    started_at: datetime
    finished_at: datetime
    findings: List[Finding]
    error: Optional[str] = None  # ← NEW: store error message if tool not available
```

---

### Phase 4: Frontend Shows Error Warnings
**Goal**: Display which scanners had errors

**Requirements**:
- ✓ Show warning banner if audit has scanner errors
- ✓ List which tools are missing
- ✓ Provide install instructions

**Files to change**:
- `frontend/js/views/dashboard.js` (or main.js)

**Display logic**:
```javascript
// In dashboard view or main.js

function updateDashboardWithErrors(status, findings, scanResults) {
    const errors = scanResults
        .filter(sr => sr.error)
        .map(sr => `${sr.scanner}: ${sr.error}`);
    
    if (errors.length > 0) {
        showWarningBanner(`
            ⚠️ Audit completed with errors:
            ${errors.join("\n")}
        `);
    }
}
```

---

## Behavior After Fix

### Scenario 1: Tools in `.venv`, Audit via Dashboard
```
Step 1: find_python_with_module("vulture")
  └─ Check VIRTUAL_ENV → not set
  └─ Check .venv/bin/python3 → EXISTS
  └─ Test: .venv/bin/python3 -c "import vulture" → SUCCESS ✓
  └─ Return: ".venv/bin/python3"

Step 2: Run scanner with correct Python
  └─ Execute: .venv/bin/python3 -m vulture .
  └─ With PATH including .venv/bin
  └─ Returns: 67 findings ✓

Result: Audit completes, shows 67 findings ✓
```

### Scenario 2: Tools NOT Installed Anywhere
```
Step 1: find_python_with_module("vulture")
  └─ Check VIRTUAL_ENV → not set
  └─ Check .venv/bin/python3 → doesn't exist
  └─ Check sys.executable → exists but no vulture
  └─ Raise: ToolNotAvailableError ✓

Step 2: Orchestrator catches error
  └─ Stores error in ScanResult
  └─ Continues with other scanners
  └─ Records: error = "Required tool 'vulture' not found..."

Result: Audit completes, shows warning ⚠️
  "Scanner 'vulture': Required tool not found. Install with: pip install vulture"
```

### Scenario 3: Users Without Virtualenv (Global Python)
```
Step 1: find_python_with_module("vulture")
  └─ Check VIRTUAL_ENV → not set
  └─ Check .venv → doesn't exist
  └─ Check sys.executable → exists and HAS vulture ✓
  └─ Return: sys.executable

Step 2: Run scanner with global Python
  └─ Works fine if user installed tools globally ✓

Result: Audit completes, shows findings ✓
```

---

## Summary of Changes

| File | Change | Why |
|------|--------|-----|
| `core/python_exe.py` | New: Smart venv detection + `find_python_with_module()` | Prioritize venv, handle cross-platform |
| `core/models.py` | Add `error: Optional[str]` to `ScanResult` | Store scanner errors for frontend |
| `plugins/quality/vulture_plugin.py` | Use `find_python_with_module()`, raise errors | Use correct Python, make errors visible |
| `plugins/security/bandit_plugin.py` | Use `find_python_with_module()`, raise errors | Use correct Python, make errors visible |
| `orchestrator.py` | Catch `ToolNotAvailableError`, store in `ScanResult` | Handle errors gracefully, continue audit |
| `frontend/js/main.js` (or dashboard) | Show warning banner if scanner errors | User sees which tools are missing |

---

## Testing Checklist

- [ ] Tools in `.venv` → Audit finds real findings
- [ ] Tools not installed → Audit shows clear error, completes with warnings
- [ ] No `.venv` but tools global → Audit uses global Python
- [ ] One scanner fails, other succeeds → Audit continues, shows both results
- [ ] Windows path handling → `.venv\Scripts\python.exe` works
- [ ] VIRTUAL_ENV variable respected → Uses active venv if set

---

## Future Enhancement (Not in this phase)

"Install missing tools" button in UI:
- User clicks button
- System runs: `{python_exe} -m pip install vulture bandit`
- Refreshes and re-runs audit
- Tools now available

For now: Clear error message + install instructions is sufficient.
