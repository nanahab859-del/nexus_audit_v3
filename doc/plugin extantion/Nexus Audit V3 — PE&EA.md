# Nexus Audit V3 — Plugin Experience & Extensibility Architecture

**Document Type:** Technical Report / Next-Phase Blueprint  
**Status:** Design Phase  
**Depends on:** Phase 4 frontend shell, corrected virtual‑environment detection  
**Target:** Make Nexus Audit V3 accessible to three distinct user profiles:  
simple users, tool‑integrators, and plugin developers.

---

## 1. Problem Statement

The current tool requires the user to know which scanners exist, manually edit
`settings.json` to enable them, and ensure the underlying tools are installed
in the correct Python environment. If a tool is missing, the audit silently
returns zero findings. This makes the tool inaccessible to developers who
are not comfortable with command‑line tooling or Python environments.

Additionally, there is no path for a developer to add a custom script or a
self‑written scanner without modifying the source code of Nexus Audit itself.

**Goal:** Make scanner management a first‑class feature of the dashboard,
allowing any user to discover, install, enable, and even add custom scanners
without leaving the browser.

---

## 2. The Three User Profiles

### Level 1 — The Simple User (“Vibe Coder”)
- Uses the dashboard to toggle scanners on/off.
- Expects the tool to tell them if a scanner is not installed.
- Expects a one‑click “Install” button.
- Never touches a terminal or a configuration file.

### Level 2 — The Developer with a Custom Script
- Has an existing linting script, a shell command, or a binary that checks
  something specific to their project.
- Wants to plug it into Nexus Audit as if it were a built‑in scanner.
- Provides a name and a path; the tool handles the rest.

### Level 3 — The Plugin Developer
- Writes a Python class that follows the `BaseScanner` interface.
- Drops the file into the `plugins/` directory.
- Expects the tool to auto‑discover, validate, and use it.
- Can also write YAML rules that extend the analysis without writing code.

---

## 3. How the Existing Architecture Supports This

| Existing component | What it already does | Which level it enables |
|--------------------|----------------------|------------------------|
| `PluginRegistry` | Auto‑discovers `BaseScanner` subclasses in `plugins/` | Level 3 |
| `settings.json` scanner toggles | `"bandit": true/false` | Level 1 (manual for now) |
| `find_tool_command()` | Checks `.venv/bin/` and system `PATH` for a tool binary | Detection for Levels 1 & 2 |
| `ScanResult.error` | Stores error message when a scanner fails | Level 1 feedback |
| Independent settings page (`/settings`) | Already designed as a decoupled page | UI for all three levels |

---

## 4. What Needs to Be Built

### 4.1 Scanner Status Detection

A backend function that, given a scanner name, returns whether the
corresponding tool is installed.

```python
# core/tool_finder.py (extension)
def is_tool_available(scanner_name: str) -> bool:
    """Return True if the tool executable is found."""
    try:
        find_tool_command(scanner_name)
        return True
    except FileNotFoundError:
        return False
```

**API endpoint:** `GET /api/scanners/status`  
Returns a map of `{scanner_name: "installed" | "not_installed"}` for all
registered scanners.

---

### 4.2 One‑Click Install

**API endpoint:** `POST /api/scanners/install`  
Body: `{"name": "bandit"}`  

The server:
1. Locates the correct Python executable (venv, then system).  
2. Runs `pip install <name>` via `asyncio.create_subprocess_exec`.  
3. Streams output via SSE events so the UI can show real‑time progress.  
4. Returns `{"status": "installed"}` on success, or an error message on failure.

---

### 4.3 Custom Plugin Registration

**API endpoint:** `POST /api/scanners/custom`  
Body: `{"name": "my-linter", "executable": "/home/user/scripts/check.sh"}`  

The server:
1. Validates that the executable exists.  
2. Saves the plugin definition to `settings.json` under a new key
   `custom_scanners`.  
3. The `PluginRegistry`, on next startup, reads `custom_scanners` and creates
   a `GenericScriptScanner` wrapper for each entry.

**`GenericScriptScanner`** is a built‑in scanner class that:
- Calls the external executable with the project path as an argument.
- Captures stdout and parses each line into a `Finding` (the script must
  output a simple format: `SEVERITY:file:line:message`).
- Can be configured with a regex pattern in the settings to parse
  non‑standard output.

---

### 4.4 Settings Page UI Updates

Add the following to the existing settings page design:

- **Scanner List Panel:**  
  A grid of scanner cards, each showing:
  - Scanner name and description.
  - Status badge: ✅ Installed / ⚠️ Not Installed / 🔌 Custom.
  - Toggle switch (enable/disable).
  - “Install” button (visible only when not installed).

- **Custom Plugin Form:**  
  A button “Add Custom Plugin” that opens a modal with:
  - Name field.
  - Executable path field (with file picker).
  - Output format selector (simple line format or custom regex).

---

### 4.5 Plugin Developer Documentation

A new file `docs/PLUGINS.md` containing:
- The `BaseScanner` interface explained.
- A minimal example scanner.
- How to drop it into `plugins/`.
- How to define YAML rules for the rules engine.
- How to test a plugin locally.

---

## 5. Implementation Order

Each step is independently testable and adds visible user value.

| Step | Deliverable | Users affected |
|------|-------------|----------------|
| 1 | `is_tool_available()` + `GET /api/scanners/status` | Levels 1, 2 |
| 2 | `POST /api/scanners/install` with SSE progress | Level 1 |
| 3 | Settings page: scanner cards with status badges | Level 1 |
| 4 | `POST /api/scanners/custom` + `GenericScriptScanner` | Level 2 |
| 5 | Settings page: “Add Custom Plugin” form | Level 2 |
| 6 | `docs/PLUGINS.md` | Level 3 |

---

## 6. Behaviour After Completion

### Level 1 User
1. Opens Settings → sees “Bandit: ⚠️ Not Installed”.  
2. Clicks “Install”. Progress bar appears, SSE output streams.  
3. Status changes to “✅ Installed”.  
4. Toggles Bandit ON.  
5. Runs audit → real findings appear.

### Level 2 User
1. Opens Settings → “Add Custom Plugin”.  
2. Enters name “dead‑link‑checker”, points to `~/scripts/check_links.sh`.  
3. Saves. The scanner appears in the list as “🔌 Custom”.  
4. Toggles it ON.  
5. Runs audit → their script runs and produces findings.

### Level 3 Developer
1. Reads `docs/PLUGINS.md`.  
2. Writes `plugins/quality/my_analyzer.py`.  
3. Restarts the server.  
4. “my_analyzer” appears in the scanner list.  
5. Toggles it ON, runs audit, sees findings.

---

## 7. Design Principles (Non‑Negotiable)

- **No silent failures** — a missing tool is always reported to the user.  
- **Install is optional** — the user can dismiss the warning and still run other scanners.  
- **Custom scanners survive updates** — stored in `settings.json`, not in the source tree.  
- **Plugin developer docs are a deliverable, not an afterthought.**

---

## 8. Relationship to the YAML Rules Engine

The rules engine (YAML‑based) is complementary to this plugin system.
- A **plugin** is for running an external tool.
- A **rule** is for defining logic that the engine evaluates directly
  (boundary checks, regex patterns, metric thresholds).
- Both produce `Finding` objects and both are configurable from the
  dashboard.

A future enhancement can allow custom rules to be packaged as plugins,
but that is out of scope for this phase.

---

*Document ready for inclusion in project notes as the next major feature phase
after core stability and dashboard completion.*