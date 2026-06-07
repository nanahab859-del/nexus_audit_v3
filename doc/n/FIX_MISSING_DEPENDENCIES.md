# Fixed: Clear Error Handling for Missing Dependencies

## Problem We Fixed

**Before**: The system would lie about findings
- If vulture/bandit not installed → reports "0 findings found"  
- Audit shows as "Completed" even though tools never ran
- User can't tell if code is clean or if tools weren't available

**After**: The system explicitly fails when dependencies are missing
- If vulture not installed → Clear error message explaining the problem
- Audit marked as **FAILED** (not succeeded with 0 findings)
- User knows exactly what's wrong

## The Fix

### 1. Clear Module Detection (core/python_exe.py)
```python
def check_module_installed(module_name: str) -> None:
    """Check if module is installed. Raise clear error if not."""
    result = subprocess.run([sys.executable, "-c", f"import {module_name}"])
    if result.returncode != 0:
        raise RuntimeError(
            f"Required module '{module_name}' is not installed.\n"
            f"Install with: pip install {module_name}"
        )
```

### 2. Scanners Check First (vulture_plugin.py, bandit_plugin.py)
**Before running scan:**
```python
# Check if tool is installed - fail loudly if not
check_module_installed("vulture")
```

If module not found → Raises RuntimeError with clear message

### 3. Orchestrator Detects Critical Errors
**Handles scanner failures:**
```python
critical_errors = []
for result in results:
    if isinstance(result, Exception):
        if "not installed" in str(result):
            critical_errors.append(str(result))  # Track critical errors
            
if critical_errors:
    # FAIL the entire audit with clear message
    job.state = "failed"
    await bus.publish(STATUS: "failed")
    return
```

## Behavior Changes

### Scenario 1: Tools Not Installed
```
Console Output:
Checking if 'vulture' is installed...
Scanner 'vulture' failed: Required module 'vulture' is not installed.
Install with: pip install vulture

Audit FAILED due to missing dependencies:
Scanner 'vulture': Required module 'vulture' is not installed. Install with: pip install vulture

Status: FAILED ✓ (not "Completed")
Findings: 0 (but user knows this is because tool isn't installed)
```

### Scenario 2: Tools Installed, No Issues Found
```
Console Output:
Checking if 'vulture' is installed...
Scanner 'vulture' found 0 findings

Status: COMPLETED ✓
Findings: 0 (this means the code is actually clean)
```

### Scenario 3: Tools Installed, Issues Found
```
Console Output:
Checking if 'vulture' is installed...
Scanner 'vulture' found 23 findings
Scanner 'bandit' found 7 findings

Status: COMPLETED ✓
Findings: 30
```

## Why This Works for Everyone

**Solo developers (with virtualenv):**
- `pip install vulture bandit` in .venv
- Tools installed → audit works
- Clear error if they forget to install

**Teams (no virtualenv):**
- `pip install vulture bandit` globally
- Tools installed in global Python → audit works
- Clear error if tools not installed on system

**Deployment/CI (containerized):**
- Install tools in container via `pip install`
- Clear error if Dockerfile missing the install
- No ambiguity about "0 findings"

## Key Principle: No Edge Cases

✓ Tool installed, ran, found issues → Report findings
✓ Tool installed, ran, found nothing → Report 0 findings (code is clean)  
✗ Tool NOT installed → FAIL with clear message (not "0 findings")

No lies, no silent failures, no ambiguity.
