# Complete Guide: Adding a New Scanner Plugin to Nexus Audit V3

**Last Updated:** 2026-06-06  
**Scope:** Every detail, no assumptions, comprehensive walkthrough

---

## TABLE OF CONTENTS

1. [System Architecture Overview](#system-architecture-overview)
2. [How Plugins Work (Complete Flow)](#how-plugins-work-complete-flow)
3. [The Plugin Registry System](#the-plugin-registry-system)
4. [BaseScanner Abstract Class Requirements](#basescanner-abstract-class-requirements)
5. [Complete Step-by-Step: Adding a New Scanner](#complete-step-by-step-adding-a-new-scanner)
6. [Existing Scanner Examples (Detailed)](#existing-scanner-examples-detailed)
7. [Configuration System](#configuration-system)
8. [Installation vs Plugin](#installation-vs-plugin)
9. [Common Pitfalls & Solutions](#common-pitfalls--solutions)
10. [Testing Your Scanner](#testing-your-scanner)

---

## SYSTEM ARCHITECTURE OVERVIEW

### What is a Scanner Plugin?

A scanner plugin is a **Python class** that:
1. Inherits from `BaseScanner` abstract class
2. Implements a single `scan()` async method
3. Returns a list of `Finding` objects
4. Handles its own errors (doesn't crash the audit)
5. Gets automatically discovered and registered by the system

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ API Server (server.py)                                      │
│  - Receives /api/run request                                │
│  - Creates Job, starts orchestrator                         │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ Orchestrator (orchestrator.py)                              │
│  1. Load PluginRegistry                                     │
│  2. Detect target languages                                 │
│  3. Filter scanners by language compatibility               │
│  4. Run matching scanners in parallel (asyncio.gather)      │
│  5. Collect findings                                        │
│  6. Write audit_data_complete.json                          │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ PluginRegistry (core/registry.py)                           │
│  - Discovers all .py files in plugins/ directory           │
│  - Finds BaseScanner subclasses in each file               │
│  - Validates each class with validate_scanner_class()      │
│  - Returns {name: ScannerClass} dictionary                 │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ Scanner Plugins (plugins/category/scanner_plugin.py)       │
│  - VultureScanner (quality)                                 │
│  - BanditScanner (security)                                 │
│  - [Your new scanner here]                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## HOW PLUGINS WORK (COMPLETE FLOW)

### Startup Flow (What Happens When Audit Runs)

**STEP 1: API Call**
```
User clicks "Run" button
  ↓
Browser: POST /api/run
  ↓
server.py: handle_run()
```

**STEP 2: Job Creation**
```
orchestrator.start_run(settings)
  ↓
Creates Job object with state="running"
  ↓
Publishes STATUS event to SSE stream
  ↓
Spawns asyncio task: orchestrator._run_job()
```

**STEP 3: Scanner Discovery**
```
Orchestrator.run() method executes:
  ↓
registry = PluginRegistry(Path("plugins"))
registry.load()
  ↓
Registry._walk_and_load(plugins_dir, max_depth=2)
  └─ Recursively walks: plugins/security/bandit_plugin.py
  └─ Recursively walks: plugins/quality/vulture_plugin.py
  └─ Any other .py files matching pattern
```

**STEP 4: Plugin Loading Mechanics**

```
For each .py file found:
  1. Convert file path to module path
     Example: plugins/quality/vulture_plugin.py
             → plugins.quality.vulture_plugin
  
  2. Import the module using importlib.import_module()
  
  3. Scan the module for classes:
     - Find all classes (name in dir(module))
     - Check if isinstance(obj, type) (is it a class?)
     - Check if issubclass(obj, BaseScanner) (inherits from BaseScanner?)
     - Check if obj is not BaseScanner (skip the base class itself)
  
  4. Validate the class with validate_scanner_class()
     - Check: name, version, languages, category are defined
     - Check: name matches regex [a-z0-9_-]+
     - Check: languages is non-empty list
     - Check: category is Category enum
     - Check: scan() method is implemented
  
  5. If validation passes:
     - Add to registry: _registry[obj.name] = obj
     - If duplicate name, log warning and overwrite
  
  6. If validation fails:
     - Log warning with validation errors
     - Skip loading this class (doesn't crash)
```

**STEP 5: Language Detection**
```
Orchestrator detects languages in target directory:

detect_languages(working_path)
  ├─ Walks all files in working_path
  ├─ Checks file extensions (.py, .js, .java, etc.)
  ├─ Returns set of detected languages
  └─ Example: {"python", "javascript"}
```

**STEP 6: Scanner Filtering**
```
For each scanner in registry:
  1. Check if enabled in settings.scanners
     settings.scanners = {"vulture": true, "bandit": true}
     If false, skip this scanner
  
  2. Check language compatibility:
     VultureScanner.languages = ["python"]
     Detected languages = {"python", "javascript"}
     Result: python in both → COMPATIBLE
  
  3. Skip if not compatible with target language
```

**STEP 7: Scanner Execution**
```
For each compatible scanner:
  1. Get scanner class from registry
  2. Instantiate: scanner_instance = cls()
  3. Build config dict:
     config = settings.scanner_configs.get("scanner_name", {})
     config["_force_rescan"] = settings.force_rescan
     config["_file_filter"] = [...]  (if applicable)
  4. Create async task:
     task = asyncio.create_task(
       _run_single_scanner(cls, working_path, config, name)
     )
  5. Add to scanner_tasks list
  
  6. Run all tasks in parallel:
     results = await asyncio.gather(
       *[t for _, t in scanner_tasks],
       return_exceptions=True
     )
```

**STEP 8: Scanner Invocation (Inside _run_single_scanner)**
```
_run_single_scanner(cls, target, config, name):
  1. Instantiate scanner: scanner = cls()
  
  2. Call scan() method (async):
     findings = await scanner.scan(target, config, bus)
  
  3. Scanner.scan():
     a. Find tool command (vulture, bandit, etc.)
     b. Prepare environment
     c. Build command-line arguments
     d. Execute tool with asyncio.create_subprocess_exec()
     e. Parse output
     f. Create Finding objects
     g. Return list of findings
     h. If tool missing: catch FileNotFoundError, log warning, return []
     i. If error: catch Exception, log error, return []
  
  4. Catch exceptions from scan():
     - If exception (not list): create ScanResult with error field
     - If list: process findings normally
```

**STEP 9: Results Collection**
```
For each scanner result:
  1. Create ScanResult object:
     ScanResult(
       scanner="vulture",
       started_at=datetime,
       finished_at=datetime,
       findings=[...],
       error=None or "error message"
     )
  2. Add to job.scan_results list
  3. Add findings to scanner_findings list
  
  If scanner had error:
    - Add to frontend error tracking
    - Publish LOG event with error message
```

**STEP 10: Audit Data Output**
```
Create audit_data_complete.json:
{
  "metadata": {...},
  "findings": [all findings from all scanners],
  "scan_results": [
    {scanner: "vulture", findings: [...]},
    {scanner: "bandit", findings: [...]}
  ]
}

Write to disk: audit_data_complete.json
```

**STEP 11: Frontend Display**
```
Dashboard requests: GET /api/data
  ↓
Returns: audit_data_complete.json contents
  ↓
Dashboard sorts findings by priority
  ↓
Shows top 10 critical findings
```

---

## THE PLUGIN REGISTRY SYSTEM

### Registry Discovery Process (Detailed)

**File: core/registry.py**

```python
class PluginRegistry:
    def __init__(self, plugins_dir: Path = Path("plugins")):
        self.plugins_dir = plugins_dir          # Path("plugins")
        self._registry: dict = {}               # {name: ScannerClass}
        self._loaded = False                    # Idempotent flag

    def load(self):
        """Called once during orchestrator.run()"""
        if self._loaded:
            return  # Safe to call multiple times
        
        if not self.plugins_dir.exists():
            print(f"Warning: plugins_dir not found", file=sys.stderr)
            self._loaded = True
            return
        
        # Start recursive walk
        self._walk_and_load(self.plugins_dir, current_depth=0, max_depth=2)
        self._loaded = True

    def _walk_and_load(self, directory, current_depth, max_depth):
        """Recursively walk directory up to max_depth=2"""
        if current_depth > max_depth:
            return  # Stop recursion
        
        for item in directory.iterdir():
            # Process Python files
            if item.is_file() and item.suffix == ".py" and item.name != "__init__.py":
                self._load_file(item)
            
            # Recurse into directories
            elif item.is_dir() and current_depth < max_depth:
                self._walk_and_load(item, current_depth + 1, max_depth)

    def _load_file(self, py_file):
        """Load a single .py file and discover scanner classes"""
        try:
            # Convert file path to module path
            # plugins/quality/vulture_plugin.py → plugins.quality.vulture_plugin
            module_path = (
                py_file.relative_to(Path("."))      # Remove ./ prefix
                    .with_suffix("")                 # Remove .py
                    .as_posix()                      # Convert to POSIX (/)
                    .replace("/", ".")               # Replace / with .
            )
            
            # Import the module
            module = importlib.import_module(module_path)
            
            # Find scanner classes in this module
            for name in dir(module):
                obj = getattr(module, name)
                
                # Check if it's a class and subclass of BaseScanner
                if (isinstance(obj, type) and 
                    issubclass(obj, BaseScanner) and 
                    obj is not BaseScanner):
                    
                    # Validate it
                    errors = validate_scanner_class(obj)
                    
                    if errors:
                        # Log validation errors
                        for error in errors:
                            print(f"Warning: {obj.__name__} validation failed: {error}",
                                  file=sys.stderr)
                    else:
                        # Register it
                        if obj.name in self._registry:
                            print(f"Warning: duplicate name {obj.name}, overwriting",
                                  file=sys.stderr)
                        self._registry[obj.name] = obj
        
        except (ImportError, SyntaxError) as e:
            print(f"Warning: failed to load {py_file}: {e}", file=sys.stderr)
    
    def get(self, name):
        """Get scanner class by name"""
        return self._registry.get(name)
    
    def all(self):
        """Get all registered scanner classes"""
        return list(self._registry.values())
    
    def names(self):
        """Get all registered scanner names"""
        return list(self._registry.keys())
```

### Critical Registry Facts

1. **Max Depth = 2**: Registry only looks 2 levels deep
   - Level 0: plugins/
   - Level 1: plugins/security/, plugins/quality/
   - Level 2: plugins/security/bandit_plugin.py, etc.
   - It will NOT find: plugins/security/v1/utils/helpers.py

2. **__init__.py Files Are Required**: Each directory must have __init__.py
   - plugins/__init__.py ✓ (required, can be empty)
   - plugins/security/__init__.py ✓ (required, can be empty)
   - plugins/quality/__init__.py ✓ (required, can be empty)
   - If missing: directory is silently skipped, no error raised

3. **Module Import Path**: Must match file structure
   - File: plugins/security/bandit_plugin.py
   - Module path: plugins.security.bandit_plugin
   - Python module system is very strict about this

4. **Idempotent**: Can call load() multiple times safely
   - Check `if self._loaded: return`
   - Prevents re-loading the same plugins

5. **Silent Failures**: Registry doesn't crash on errors
   - ImportError: logged, skipped
   - SyntaxError: logged, skipped
   - Validation errors: logged, skipped
   - This design ensures one bad plugin doesn't break audit

---

## BASESCANNER ABSTRACT CLASS REQUIREMENTS

### File: plugins/base.py

```python
from abc import ABC, abstractmethod
from typing import ClassVar, List
from pathlib import Path
from core.models import Finding, Category
from core.events import EventBus

class BaseScanner(ABC):
    """Abstract base class for all scanner plugins"""
    
    # ═══════════════════════════════════════════════════════════════
    # REQUIRED: ClassVar attributes (must be defined in each subclass)
    # ═══════════════════════════════════════════════════════════════
    
    name: ClassVar[str]
    # Unique identifier for this scanner
    # Must match: [a-z0-9_-]+
    # Used in: settings.json, logs, API responses
    # Example: "vulture", "bandit", "pylint"
    # Note: Must be unique across ALL loaded scanners
    
    version: ClassVar[str]
    # Version of this scanner plugin
    # Example: "1.0.0", "2.1.5"
    # Used for: tracking which scanner plugin version found issues
    # Note: Does NOT control the version of the underlying tool
    
    languages: ClassVar[List[str]]
    # Programming languages this scanner supports
    # Example: ["python"], ["javascript", "typescript"]
    # Used for: filtering scanners by target language compatibility
    # Important: Must not be empty! At least one language required
    
    category: ClassVar[Category]
    # Category enum for findings
    # Options: Category.SECURITY, Category.QUALITY, Category.PERFORMANCE,
    #          Category.DEPENDENCY, Category.ARCHITECTURE
    # Used for: tagging findings with category
    # Example: Category.SECURITY for bandit, Category.QUALITY for vulture
    
    # ═══════════════════════════════════════════════════════════════
    # OPTIONAL: ClassVar attributes (default values provided)
    # ═══════════════════════════════════════════════════════════════
    
    requires_ai: ClassVar[bool] = False
    # Does this scanner need AI to work?
    # Example: True for "ai-powered code reviewer"
    # Used for: filtering if AI is disabled
    
    timeout: ClassVar[int] = 120
    # Maximum seconds for scan() to run
    # Example: 60 seconds for fast scanners, 300 for slow ones
    # Enforced by: asyncio.wait_for(proc.communicate(), timeout=self.timeout)
    # If exceeded: asyncio.TimeoutError is raised
    
    # ═══════════════════════════════════════════════════════════════
    # REQUIRED: async scan() method
    # ═══════════════════════════════════════════════════════════════
    
    @abstractmethod
    async def scan(
        self,
        target: Path,
        config: dict,
        bus: EventBus,
    ) -> List[Finding]:
        """
        Scan the target directory and return findings.
        
        Args:
            target: Path to directory to scan
                    Example: Path("/home/user/nexus-gaming")
            
            config: Configuration dictionary for this scanner
                    Keys automatically added by orchestrator:
                      - "_force_rescan": bool (force re-scan)
                      - "_file_filter": list (files to scan)
                    Keys from settings.json:
                      - Any custom config for this scanner
                    Example: {
                        "_force_rescan": False,
                        "exclude_patterns": ["*.test.py"],
                        "max_complexity": 10
                    }
            
            bus: EventBus for publishing logs and progress
                 Usage:
                   await bus.publish_log("info", "message")
                   await bus.publish_log("warning", "message")
                   await bus.publish_log("error", "message")
                   await bus.publish_progress(self.name, percent, file)
        
        Returns:
            List of Finding objects found during scan
            
            CRITICAL REQUIREMENT: ALWAYS return a list, never raise exceptions
            
            If tool is missing:
              - Catch FileNotFoundError
              - Log warning message
              - Return [] (empty list)
            
            If scan has error:
              - Catch Exception
              - Log error message
              - Return [] (empty list)
            
            If scan succeeds:
              - Return list of Finding objects
            
            NEVER raise exceptions - orchestrator expects always []
        
        Finding object requires:
            id: str - unique identifier (use hashlib.sha256)
            scanner: str - self.name
            file: str - relative or absolute path
            line: int - line number (0 if unknown)
            column: int - column number (0 if unknown)
            severity: Severity - CRITICAL, HIGH, MEDIUM, LOW, INFO
            category: Category - self.category
            title: str - short issue title
            description: str - detailed issue description
            suggestion: str - how to fix
            persistence: Persistence - NEW, PERSISTENT, INTERMITTENT, RESOLVED
            fix_status: FixStatus - OPEN, IN_PROGRESS, DONE, SNOOZED
            cwe: Optional[str] - CWE number if applicable
            cvss_score: Optional[float] - CVSS score if applicable
        
        Example return:
            [
                Finding(
                    id="abc123def456",
                    scanner="vulture",
                    file="/home/user/app.py",
                    line=42,
                    column=0,
                    severity=Severity.LOW,
                    category=Category.QUALITY,
                    title="Dead code detected",
                    description="Variable 'unused_var' is never used",
                    suggestion="Remove unused variable",
                    persistence=Persistence.NEW,
                    fix_status=FixStatus.OPEN
                )
            ]
        """
        ...
```

### Validation Function

```python
def validate_scanner_class(cls: type) -> list[str]:
    """
    Validate scanner class before registering.
    Returns list of error strings (empty = valid).
    """
    errors: list[str] = []
    
    # Check all required ClassVar fields exist
    required = ["name", "version", "languages", "category"]
    for field_name in required:
        if not hasattr(cls, field_name):
            errors.append(f"Missing ClassVar: {field_name}")
    
    # Check name format
    if hasattr(cls, "name"):
        name = getattr(cls, "name")
        if not isinstance(name, str):
            errors.append(f"name must be str, got {type(name).__name__}")
        elif not re.match(r"^[a-z0-9_-]+$", name):
            errors.append(f"name must match [a-z0-9_-]+, got: {name}")
    
    # Check languages is non-empty list
    if hasattr(cls, "languages"):
        langs = getattr(cls, "languages")
        if not isinstance(langs, list) or len(langs) == 0:
            errors.append("languages must be non-empty list")
    
    # Check category is Category enum
    if hasattr(cls, "category"):
        cat = getattr(cls, "category")
        if not isinstance(cat, Category):
            errors.append(f"category must be Category enum, got {type(cat).__name__}")
    
    # Check scan() is implemented
    if not hasattr(cls, "scan") or cls.scan is BaseScanner.scan:
        errors.append("scan() must be implemented")
    
    return errors
```

---

## COMPLETE STEP-BY-STEP: ADDING A NEW SCANNER

### Example: Adding a PyLint Scanner

Let's walk through adding "pylint" scanner step by step.

### STEP 1: Determine the Category

Decide where your scanner belongs. Choose from:
- security/ - Security scanning (bandit is here)
- quality/ - Code quality (vulture is here)
- performance/ - Performance analysis
- dependency/ - Dependency checking
- architecture/ - Architecture analysis

For pylint: **quality/** (it detects code quality issues)

### STEP 2: Create the Plugin File

**File:** `plugins/quality/pylint_plugin.py`

```python
import asyncio
import os
from pathlib import Path
from typing import List
import json
import hashlib

from plugins.base import BaseScanner
from core.models import Finding, Category, Severity, Persistence, FixStatus
from core.events import EventBus
from core.python_exe import find_tool_command, _get_venv_python


class PylintScanner(BaseScanner):
    # ═══════════════════════════════════════════════════════════════
    # STEP 2A: Define Required ClassVar attributes
    # ═══════════════════════════════════════════════════════════════
    
    name = "pylint"
    # Unique name matching [a-z0-9_-]+
    # This will appear in: settings.json, logs, dashboard
    # Used by orchestrator as: settings.scanners["pylint"]
    
    version = "1.0.0"
    # Version of THIS plugin (not pylint version)
    # incremented when you change the plugin code
    
    languages = ["python"]
    # Pylint only works on Python
    # Orchestrator will skip this if target is JavaScript
    
    category = Category.QUALITY
    # Categorize the findings as code quality issues
    
    timeout = 120
    # Allow up to 120 seconds for pylint to run
    # Pylint can be slow on large codebases
    
    # ═══════════════════════════════════════════════════════════════
    # STEP 2B: Implement the scan() method
    # ═══════════════════════════════════════════════════════════════
    
    async def scan(
        self,
        target: Path,
        config: dict,
        bus: EventBus,
    ) -> List[Finding]:
        """
        Run pylint on target directory.
        """
        findings = []
        
        try:
            # STEP 2B-1: Log that we're starting
            await bus.publish_log("info", "Starting pylint scan...")
            
            # STEP 2B-2: Find pylint command
            # This looks in: .venv/bin, system PATH, importable modules
            # If not found: raises FileNotFoundError (we catch it below)
            try:
                tool_cmd = find_tool_command("pylint")
                await bus.publish_log("info", f"Using: {tool_cmd}")
            except FileNotFoundError:
                await bus.publish_log(
                    "warning",
                    "pylint not installed. Install with: pip install pylint"
                )
                return []  # Return empty, don't crash
            
            # STEP 2B-3: Prepare environment
            env = os.environ.copy()
            venv_python = _get_venv_python()
            if venv_python:
                bin_dir = venv_python.parent
                env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
            
            # STEP 2B-4: Build command arguments
            # Pylint format: pylint [options] target
            cmd = [
                tool_cmd,
                str(target),
                # Output as JSON for easy parsing
                "--output-format=json",
                # Include only errors and warnings
                "--disable=R,C",  # R=refactor, C=convention
                # Exclude certain patterns
                "--ignore-patterns=test_.*?py",
            ]
            
            # STEP 2B-5: Publish progress
            await bus.publish_progress(self.name, 10, str(target))
            
            # STEP 2B-6: Run the tool asynchronously
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env
                )
                
                # Wait for completion with timeout enforcement
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self.timeout
                )
                
                # STEP 2B-7: Parse the output
                if stdout:
                    try:
                        # Pylint outputs JSON array of issues
                        issues = json.loads(stdout.decode('utf-8'))
                        
                        for issue in issues:
                            # Severity mapping: pylint ratings → Finding severity
                            severity_map = {
                                "fatal": Severity.CRITICAL,
                                "error": Severity.HIGH,
                                "warning": Severity.MEDIUM,
                                "refactor": Severity.LOW,
                                "convention": Severity.LOW,
                            }
                            
                            # Create unique ID
                            finding_id = hashlib.sha256(
                                f"{issue.get('path')}{issue.get('line')}{issue.get('symbol')}".encode()
                            ).hexdigest()[:16]
                            
                            # Create Finding object
                            finding = Finding(
                                id=finding_id,
                                scanner=self.name,
                                file=issue.get("path", "unknown"),
                                line=issue.get("line", 0),
                                column=issue.get("column", 0),
                                severity=severity_map.get(
                                    issue.get("type", "warning"),
                                    Severity.MEDIUM
                                ),
                                category=Category.QUALITY,
                                title=f"[{issue.get('symbol')}] {issue.get('message', 'Issue')}",
                                description=issue.get("message", ""),
                                suggestion=f"See pylint documentation for {issue.get('symbol')}",
                                persistence=Persistence.NEW,
                                fix_status=FixStatus.OPEN
                            )
                            findings.append(finding)
                        
                        await bus.publish_log(
                            "info",
                            f"pylint found {len(findings)} issues"
                        )
                    
                    except json.JSONDecodeError as e:
                        await bus.publish_log(
                            "warning",
                            f"Failed to parse pylint JSON: {str(e)}"
                        )
                
                # STEP 2B-8: Update progress to complete
                await bus.publish_progress(self.name, 100, str(target))
            
            except asyncio.TimeoutError:
                await bus.publish_log(
                    "error",
                    f"pylint timed out after {self.timeout}s"
                )
            
            except Exception as e:
                await bus.publish_log(
                    "error",
                    f"pylint error: {str(e)}"
                )
        
        except Exception as e:
            await bus.publish_log(
                "error",
                f"pylint scanner error: {str(e)}"
            )
        
        # ALWAYS return a list (even if empty due to error)
        return findings
```

### STEP 3: Ensure Directory Structure

```
plugins/
├── __init__.py                    ← Already exists
├── base.py                        ← Already exists
├── security/
│   ├── __init__.py               ← Already exists (can be empty)
│   └── bandit_plugin.py          ← Already exists
└── quality/
    ├── __init__.py               ← Already exists (can be empty)
    ├── vulture_plugin.py         ← Already exists
    └── pylint_plugin.py          ← YOU CREATE THIS
```

**Critical:** Each directory MUST have `__init__.py`!

### STEP 4: Update settings.json

Add the new scanner to the configuration:

**File:** `settings.json`

```json
{
  "project_path": "/home/yusupha/nexus-gaming",
  "api_key": null,
  "ai_enabled": false,
  "ai_provider": "claude",
  "ai_model": "claude-opus-4-7",
  "force_rescan": false,
  "scanners": {
    "vulture": true,
    "bandit": true,
    "pylint": true    ← ADD THIS LINE
  },
  "scanner_configs": {
    "vulture": {},
    "bandit": {},
    "pylint": {       ← ADD THIS SECTION
      "disable": ["R0123"]  ← Optional: configuration for pylint
    }
  },
  "ui": {}
}
```

### STEP 5: Install the Tool (If Needed)

The plugin expects the actual tool to be installed. For pylint:

```bash
# Install in the project's virtual environment
source .venv/bin/activate
pip install pylint

# Verify it's installed
which pylint
```

**Important:** The plugin itself doesn't install the tool. It assumes it's already available in:
1. `.venv/bin/pylint` (virtual environment)
2. System PATH (e.g., /usr/bin/pylint)
3. As importable Python module (checked as fallback)

If not found: Scanner logs warning and returns empty list (doesn't crash).

### STEP 6: Test the Scanner

**Restart the server:**
```bash
# Kill existing server
pkill -f "python server.py"

# Start fresh
python server.py
```

**In the dashboard:**
1. Click "Run" button
2. Wait for audit to complete
3. Check console logs (F12 → Console tab):
   ```
   [Dashboard] Sorting 5000 findings by priority
   ```
   Look for pylint in the logs:
   ```
   [Stream:log] [info] Running 'pylint' scanner...
   [Stream:log] [info] Using: /home/user/.venv/bin/pylint
   [Stream:log] [info] pylint found 42 issues
   ```

**Check audit data:**
```bash
python3 -c "
import json
with open('audit_data_complete.json') as f:
    data = json.load(f)
    for result in data['scan_results']:
        if result['scanner'] == 'pylint':
            print(f\"pylint: {len(result['findings'])} findings\")
"
```

---

## EXISTING SCANNER EXAMPLES (DETAILED)

### Example 1: VultureScanner (Simple Output Parsing)

**File:** `plugins/quality/vulture_plugin.py`

Key characteristics:
- Simple text output (not JSON)
- One finding per line
- Regex parsing to extract data
- Simple categorization (all LOW severity)

**Why look at it:** Learn basic regex parsing pattern

### Example 2: BanditScanner (JSON Output Parsing)

**File:** `plugins/security/bandit_plugin.py`

Key characteristics:
- JSON output (structured)
- Multiple fields per issue
- Severity mapping (HIGH, MEDIUM, LOW)
- CWE reference extraction

**Why look at it:** Learn JSON parsing and severity mapping

---

## CONFIGURATION SYSTEM

### How Scanner Configuration Works

**In settings.json:**

```json
{
  "scanner_configs": {
    "pylint": {
      "disable": ["R0123", "C0103"],
      "max_line_length": 120
    },
    "vulture": {
      "min_confidence": 80
    }
  }
}
```

**In your scanner's scan() method:**

```python
async def scan(self, target, config, bus):
    # config automatically contains:
    # - All keys from settings.scanner_configs["pylint"]
    # - Plus "_force_rescan" and "_file_filter" added by orchestrator
    
    disable = config.get("disable", [])
    max_line_length = config.get("max_line_length", 120)
    force_rescan = config.get("_force_rescan", False)
    
    if force_rescan:
        await bus.publish_log("info", "Force re-scan enabled")
```

### API Endpoint for Configuration

The settings API allows updating scanner configs:

**API:** `POST /api/settings`

**Request:**
```json
{
  "scanners": {
    "pylint": true
  },
  "scanner_configs": {
    "pylint": {
      "disable": ["R0123"]
    }
  }
}
```

**Response:** Updated settings

---

## INSTALLATION VS PLUGIN

### Key Distinction

**Plugin:** The Python class you write
- Location: `plugins/quality/my_scanner.py`
- Automatically discovered by PluginRegistry
- Invoked by Orchestrator
- No installation required (Python file)

**Tool:** The actual scanning executable
- Location: `/usr/bin/pylint` or `.venv/bin/pylint`
- Must be installed separately (pip, apt, brew, etc.)
- Used BY the plugin (plugin calls it)
- **Plugin doesn't install it!**

### Installation Process

```
User wants to use pylint:

1. Write plugin: plugins/quality/pylint_plugin.py ✓
   - Inherits BaseScanner
   - Implements scan()
   
2. Install the tool: pip install pylint
   - In virtual environment
   - OR in system PATH
   
3. Plugin discovers and uses the tool
   - Plugin calls find_tool_command("pylint")
   - Finds /path/to/venv/bin/pylint
   - Calls it with asyncio.create_subprocess_exec()

If tool not installed:
   - find_tool_command() raises FileNotFoundError
   - Plugin catches it
   - Returns []
   - Audit continues
```

### Two-Part Checklist

**Part 1: Plugin**
- ✓ File created: `plugins/quality/my_scanner.py`
- ✓ Class inherits: `BaseScanner`
- ✓ Has: `name`, `version`, `languages`, `category`, `timeout`
- ✓ Implements: `async def scan()`
- ✓ Returns: `List[Finding]`
- ✓ Catches: `FileNotFoundError` when tool missing

**Part 2: Tool**
- ✓ Tool installed: `pip install toolname`
- ✓ In virtual env: `which toolname`
- ✓ Accessible by: Plugin via `find_tool_command()`

---

## COMMON PITFALLS & SOLUTIONS

### Pitfall 1: FileNotFoundError Crashes Audit

**Wrong:**
```python
async def scan(self, target, config, bus):
    tool_cmd = find_tool_command("mytool")  # Raises if not found
    # Audit crashes if tool not installed
```

**Right:**
```python
async def scan(self, target, config, bus):
    try:
        tool_cmd = find_tool_command("mytool")
    except FileNotFoundError as e:
        await bus.publish_log("warning", f"mytool not available: {e}")
        return []  # Return empty list, let audit continue
```

### Pitfall 2: Raising Exceptions Inside scan()

**Wrong:**
```python
async def scan(self, target, config, bus):
    try:
        data = json.loads(stdout)
    except JSONDecodeError:
        raise ValueError("Invalid JSON")  # Crashes orchestrator
```

**Right:**
```python
async def scan(self, target, config, bus):
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as e:
        await bus.publish_log("warning", f"Parse error: {e}")
        return []
```

### Pitfall 3: Missing __init__.py in Category Directory

**Wrong:**
```
plugins/
├── security/
│   └── my_scanner.py           ← No __init__.py!
```
Result: Scanner is silently NOT discovered, no error message

**Right:**
```
plugins/
├── security/
│   ├── __init__.py             ← Must exist!
│   └── my_scanner.py
```

### Pitfall 4: Invalid Scanner Name

**Wrong:**
```python
name = "My-Scanner"  # Has space? Uppercase? Not matching [a-z0-9_-]
# Validation fails, scanner not registered
```

**Right:**
```python
name = "my_scanner"  # Only lowercase, numbers, underscore, hyphen
```

### Pitfall 5: Forgetting to Use asyncio for Subprocess

**Wrong:**
```python
import subprocess

proc = subprocess.run(["mytool", str(target)])  # Blocks event loop!
```

**Right:**
```python
proc = await asyncio.create_subprocess_exec(
    "mytool", str(target),
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE
)
stdout, stderr = await proc.communicate()
```

### Pitfall 6: Duplicate Scanner Name

If two plugins define `name = "pylint"`:
- First loaded: Gets registered
- Second loaded: Logs warning "duplicate scanner name"
- Second: Gets registered (overwrites first)

**Solution:** Use unique names

### Pitfall 7: Languages Set to Empty List

**Wrong:**
```python
languages = []  # No languages specified!
# Validation fails, error message logged
```

**Right:**
```python
languages = ["python", "python3"]  # At least one
```

### Pitfall 8: Not Using .venv Python

**Problem:** Tool installed in .venv but system Python tries to use global version

**Solution:** Use _get_venv_python() and add to PATH:
```python
venv_python = _get_venv_python()
if venv_python:
    bin_dir = venv_python.parent
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
```

---

## TESTING YOUR SCANNER

### Unit Test Pattern

**File:** `tests/test_my_scanner.py`

```python
import pytest
import asyncio
from pathlib import Path
from plugins.quality.my_scanner_plugin import MyScanner
from core.models import Finding
from core.events import EventBus

@pytest.mark.asyncio
async def test_my_scanner_finds_issues():
    # Setup
    scanner = MyScanner()
    bus = EventBus()
    target = Path("/path/to/test/project")
    config = {}
    
    # Execute
    findings = await scanner.scan(target, config, bus)
    
    # Assert
    assert isinstance(findings, list)
    assert len(findings) > 0
    assert all(isinstance(f, Finding) for f in findings)
    assert all(f.scanner == "my_scanner" for f in findings)

@pytest.mark.asyncio
async def test_my_scanner_handles_missing_tool():
    # When tool not installed, should not crash
    scanner = MyScanner()
    bus = EventBus()
    target = Path("/path/to/test/project")
    config = {}
    
    # Mock find_tool_command to raise FileNotFoundError
    # (in real scenario, tool is just not installed)
    
    # Execute and verify it doesn't crash
    findings = await scanner.scan(target, config, bus)
    
    # Assert: should return empty list, not raise exception
    assert findings == []
```

### Manual Testing

```bash
# 1. Ensure tool is installed
pip install mytool

# 2. Start server
python server.py

# 3. Run audit in dashboard or API
curl -X POST http://127.0.0.1:8421/api/run

# 4. Check logs in browser console (F12)
[Stream:log] [info] Running 'my_scanner' scanner...

# 5. Verify findings in audit data
python3 -c "
import json
with open('audit_data_complete.json') as f:
    data = json.load(f)
    for result in data['scan_results']:
        if result['scanner'] == 'my_scanner':
            print(f\"Found {len(result['findings'])} findings\")
            for finding in result['findings'][:3]:
                print(f\"  - {finding['title']}\")
"
```

---

## SUMMARY: Adding a Scanner Requires

### Code Files to Create/Modify:

1. **Create:** `plugins/category/scanner_plugin.py`
   - Inherit from BaseScanner
   - Define: name, version, languages, category, timeout (ClassVar)
   - Implement: async scan() method
   - Must not raise exceptions, catch all errors

2. **Create/Verify:** `plugins/category/__init__.py`
   - Must exist (can be empty)
   - Registry needs this to find the package

3. **Modify:** `settings.json`
   - Add scanner name to `scanners` dict
   - Add config to `scanner_configs` dict

### Installation Required:

- Actual tool must be installed separately
- Plugin doesn't do installation
- Plugin calls find_tool_command() to locate it
- If missing: Scanner logs warning, returns []

### Discovery & Registration:

- PluginRegistry automatically finds it
- Validates ClassVar attributes
- Registers if valid, logs warning if invalid
- Never crashes on invalid plugin

### Execution:

- Orchestrator loads registry
- Filters scanners by language compatibility
- Runs matching scanners in parallel
- Collects findings
- Writes to audit_data_complete.json

---

**This is the COMPLETE picture. Every detail is here.**
