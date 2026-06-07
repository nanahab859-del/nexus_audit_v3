# Logic Analysis: Virtual Environment vs Global Python

## Current Problem (What's Happening Now)

```
System State:
- Global Python: /usr/bin/python3 or Miniconda Python (NO vulture/bandit)
- Virtualenv Python: ~/.venv/bin/python3 (HAS vulture/bandit installed ✓)
- Currently Active: Miniconda Python ✗

Current Code Flow:
1. check_module_installed("vulture")
   └─ Uses sys.executable (Miniconda Python)
   └─ Runs: /miniconda3/bin/python3 -c "import vulture"
   └─ Result: ModuleNotFoundError ✗ (not installed in Miniconda)
   └─ Raises error: "vulture is not installed"

2. Scanner catches error, returns []

3. Orchestrator sees empty findings
   └─ Still writes findings: 0
   └─ Still marks audit: "completed"
   └─ WRONG! It should fail if tools not available

The Logic Is Broken Because:
- Tools ARE installed (in virtualenv)
- But checking the WRONG Python (global)
- Saying "not installed" when they actually are
- Then returning 0 findings instead of failing
```

---

## The Correct Logic Should Be

```
Correct Flow:
1. Find the Python to use
   a. Check if virtualenv exists (.venv/bin/python3)
   b. If yes → Use that Python
   c. If no → Use sys.executable (global Python)

2. Check if tool is installed in THAT Python
   a. Run: [selected_python] -c "import vulture"
   b. If found → Continue to run scanner with that Python
   c. If not found → FAIL with clear error

3. Run scanner with the correct Python
   a. Use the Python we confirmed has the tools
   b. Scan the project
   c. Return findings

The Key Difference:
- BEFORE: Check global Python, fail if not found
- AFTER: Check virtualenv first, use that if available, only check global if no virtualenv
```

---

## Code Example: What Should Happen

### Current Broken Code:
```python
def check_module_installed(module_name: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", f"import {module_name}"],  # ✗ WRONG: Always uses global Python
        capture_output=True,
        timeout=2
    )
    if result.returncode != 0:
        raise RuntimeError(f"Module '{module_name}' not installed")
```

### Correct Logic:
```python
def find_python_with_module(module_name: str) -> str:
    """Find Python that has the module. Prioritize virtualenv."""
    
    # Step 1: Try virtualenv Python first
    venv_python = Path.cwd() / ".venv" / "bin" / "python3"
    if venv_python.exists():
        result = subprocess.run(
            [str(venv_python), "-c", f"import {module_name}"],
            capture_output=True,
            timeout=2
        )
        if result.returncode == 0:
            return str(venv_python)  # ✓ Found in virtualenv
    
    # Step 2: If not found in virtualenv, try global Python
    result = subprocess.run(
        [sys.executable, "-c", f"import {module_name}"],
        capture_output=True,
        timeout=2
    )
    if result.returncode == 0:
        return sys.executable  # ✓ Found in global
    
    # Step 3: Not found anywhere - fail clearly
    raise RuntimeError(
        f"Module '{module_name}' not found in virtualenv or global Python.\n"
        f"Install with: pip install {module_name}"
    )
```

---

## Execution Flow With Correct Logic

### Your Environment:
```
.venv/bin/python3  → Has vulture, bandit ✓
/miniconda/bin/python3 → Doesn't have them ✗
```

### What Should Happen:
```
Step 1: Check virtualenv Python first
  find_python_with_module("vulture")
  └─ Test: /home/yusupha/my_tools/nexus_audit_v3/.venv/bin/python3 -c "import vulture"
  └─ Result: EXIT 0 ✓ (found!)
  └─ Return: "/home/yusupha/my_tools/nexus_audit_v3/.venv/bin/python3"

Step 2: Use virtualenv Python to run scanner
  subprocess.run([
    "/home/yusupha/my_tools/nexus_audit_v3/.venv/bin/python3",
    "-m", "vulture", "."
  ])
  └─ Uses correct Python with tools installed ✓
  └─ Returns actual findings

Step 3: Audit completes successfully ✓
```

---

## Why Your Audit Is Failing

1. **Current Code Problem**: Checks global Python first, finds tools missing, throws error
2. **But Then**: Code catches error, returns 0 findings, audit continues (WRONG)
3. **Result**: Audit reports "0 findings" when it should either:
   - Use virtualenv Python and find real findings, OR
   - Fail clearly with error message

---

## The Fix (High Level)

```python
# In each scanner (vulture, bandit):

async def scan(self, target, config, bus):
    # FIND the correct Python first
    python_exe = find_python_with_module(self.name)  # Tries virtualenv first!
    
    # NOW run the scanner with the correct Python
    result = subprocess.run([python_exe, "-m", self.name, ...])
    
    # Parse results
    return findings
```

**Key Points:**
1. Find Python that HAS the tools (virtualenv priority)
2. Use THAT Python to run scanner
3. Return real findings
4. If tools not found ANYWHERE, fail clearly

---

## Summary

**What's Wrong:**
- Checking global Python instead of virtualenv Python
- Saying tools "not installed" when they ARE in virtualenv
- Still returning 0 findings instead of failing

**What's Right:**
- Check virtualenv Python first (.venv/bin/python3)
- If tools found there, use that Python
- If not found anywhere, fail with clear error
- Never return "0 findings" for a failed audit

**Result:**
- Your virtualenv has the tools → Audit finds real findings ✓
- No virtualenv → Check global Python ✓
- Tools truly missing → Fail clearly ✓
