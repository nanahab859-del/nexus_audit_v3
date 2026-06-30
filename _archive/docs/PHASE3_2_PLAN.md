# Nexus Audit V3 — Phase 3.2: Scanner Layer Hardening
**Status:** Planning  
**Depends on:** Phase 3 complete (`v0.3.0` tag exists)  
**Goal:** Fix two critical issues that cause runtime crashes and silent feature gaps,
then close four smaller gaps identified in the Phase 3 review before the frontend
(Phase 4) consumes scanner output and makes these harder to fix.

---

## What Phase 3.2 Fixes

| # | Type | Gap | Symptom if unfixed | File(s) touched |
|---|------|-----|--------------------|----------------|
| 1 | **Critical** | `pathspec` in optional deps only | `import pathspec` crashes on any run without `.[scanners]` installed | `pyproject.toml`, `core/file_discovery.py` |
| 2 | **Critical** | Bandit `severity_filter` config key ignored | All findings returned regardless of user setting; config key is dead code | `plugins/security/bandit_plugin.py`, `tests/test_plugin_bandit.py` |
| 3 | Minor | Semgrep `extra_rules` config key ignored | User-configured extra rules never passed to the CLI | `plugins/quality/semgrep_plugin.py`, `tests/test_plugin_semgrep.py` |
| 4 | Minor | Semgrep progress events unimplementable as described | `--json` output has no per-file events; plan promises real-time feedback that can't be delivered | `plugins/quality/semgrep_plugin.py` |
| 5 | Minor | Vulture `whitelist_path` config key ignored | User whitelist never passed to CLI; dead config | `plugins/architecture/vulture_plugin.py`, `tests/test_plugin_vulture.py` |
| 6 | Minor | `force_rescan` setting has no effect; undocumented | Future caching phase will silently break if callers assume it works | `orchestrator.py`, `docs/` |
| 7 | Minor | Verify `load()` decryption is in place | `save()` fix in Phase 3 Step 0 assumed it was; if not, double-encryption will occur | `core/settings.py`, `tests/test_settings.py` |

---

## Folder Changes After Phase 3.2

```
nexus_audit_v3/
├── core/
│   └── settings.py              ← VERIFY (decrypt in load — add if missing)
├── plugins/
│   ├── security/
│   │   └── bandit_plugin.py     ← EDIT: implement severity_filter
│   ├── quality/
│   │   ├── semgrep_plugin.py    ← EDIT: extra_rules + honest progress events
│   │   └── vulture_plugin.py    ← EDIT: whitelist_path passthrough
├── orchestrator.py               ← EDIT: document force_rescan intent
├── pyproject.toml                ← EDIT: move pathspec to mandatory deps
└── tests/
    ├── test_plugin_bandit.py     ← EDIT: severity_filter tests
    ├── test_plugin_semgrep.py    ← EDIT: extra_rules tests
    └── test_plugin_vulture.py    ← EDIT: whitelist_path tests
```

No new files. No new modules.

---

## Step-by-Step Implementation Order

---

### Step 0 — Verify `load()` decryption before anything else

This is a one-minute check that underpins Steps 1–7. If `load()` does not decrypt,
every `save()` call will double-encrypt.

**Open `core/settings.py` and confirm `load()` contains:**
```python
if settings.api_key and settings.api_key not in ("", "***"):
    try:
        from core.security import decrypt
        settings = dataclasses.replace(settings, api_key=decrypt(settings.api_key))
    except Exception:
        import warnings
        warnings.warn("api_key could not be decrypted ...", stacklevel=2)
```

**If present:** no code change needed. Add a comment above it:
```python
# Always decrypt on load — save() always encrypts, so Settings in memory
# is always plaintext. Phase 2.2 established this invariant.
```

**If missing:** add it now (same code as Phase 2.2 Step 2) before any other work.

**Update `tests/test_settings.py`** — add if not already present:
- Save settings with plaintext key → load → key is plaintext (round-trip).
- Save twice with same plaintext key → both writes succeed → load returns plaintext.
  (Proves no double-encryption after Phase 3 Step 0 removed the prefix guard.)

**Commit:** `fix(settings): verify and document load() decrypt invariant`

---

### Step 1 — Move `pathspec` to mandatory dependencies

**The problem:**  
`core/file_discovery.py` does `import pathspec` at module level. It is a core
module, not a plugin. Any user who runs `pip install -e .` without `.[scanners]`
will hit `ModuleNotFoundError: No module named 'pathspec'` the moment the server
starts — before any scanner runs, before any audit begins.

**Fix in `pyproject.toml`:**

Move `pathspec` from `[project.optional-dependencies].scanners` to
`[project.dependencies]`:

```toml
[project]
dependencies = [
    "aiohttp",
    "aiofiles",
    "jsonschema",
    "cryptography",
    "pathspec>=0.12",   # ← moved here from optional
]

[project.optional-dependencies]
scanners = [
    "bandit>=1.7",
    "vulture>=2.10",
    "radon>=6.0",
    "pip-audit>=2.7",
    "lizard>=1.17",
    "semgrep>=1.60",
    # pathspec is NOT here anymore
]
```

**Rules:**
- `pathspec` is always installed with the base package. No user action required.
- The optional `scanners` group still works — `pip install -e ".[scanners]"` adds
  the CLI tools on top of the base install.
- Run `pip install -e .` (without extras) and confirm `python -c "import pathspec"`
  succeeds after this change.

**Commit:** `fix(deps): move pathspec to mandatory dependencies`

---

### Step 2 — Implement Bandit `severity_filter`

**The problem:**  
`settings.scanner_configs["bandit"]["severity_filter"]` defaults to `"low"` but
the plugin never reads it. All findings are returned regardless. A user who sets
`"high"` still sees low-severity findings.

**Fix in `plugins/security/bandit_plugin.py`:**

After parsing Bandit's JSON output and constructing the `findings` list, add:

```python
# Apply severity filter from config
severity_filter = config.get("severity_filter", "low").lower()
filter_map = {
    "low":    {Severity.LOW, Severity.MEDIUM, Severity.HIGH},
    "medium": {Severity.MEDIUM, Severity.HIGH},
    "high":   {Severity.HIGH},
}
allowed = filter_map.get(severity_filter, filter_map["low"])
findings = [f for f in findings if f.severity in allowed]
```

**Rules:**
- The filter is applied after construction — `Finding` objects are built first,
  then trimmed. This keeps the mapping logic clean.
- An unrecognised `severity_filter` value falls back to `"low"` (keep all).
  Log a warning: `"Unknown severity_filter '{value}', defaulting to 'low'"`.
- The filter does not affect severity values — it controls what is returned,
  not how things are classified.

**Update `tests/test_plugin_bandit.py`:**
- Add test: config `{"severity_filter": "high"}` on a project with both HIGH and LOW
  findings → only HIGH findings returned.
- Add test: config `{"severity_filter": "medium"}` → LOW findings absent, MEDIUM
  and HIGH present.
- Add test: config `{"severity_filter": "low"}` (default) → all findings returned.
- Add test: config `{"severity_filter": "invalid"}` → all findings returned,
  warning emitted.

**Commit:** `fix(bandit): implement severity_filter config key`

---

### Step 3 — Implement Semgrep `extra_rules` + honest progress events

**Problem A — `extra_rules` ignored:**  
The config key exists but the CLI call never uses it.

**Fix the CLI construction in `plugins/quality/semgrep_plugin.py`:**

```python
rules_path = config.get("rules_path", None)
extra_rules = config.get("extra_rules", [])

# Build the --config argument list
configs = []
if rules_path:
    configs.append(rules_path)
else:
    configs.extend(["p/python", "p/security-audit"])

for rule in extra_rules:
    # extra_rules can be "p/jwt" or a local path; pass as-is
    configs.append(rule)

# Build CLI args: semgrep --config X --config Y --config Z
config_args = []
for c in configs:
    config_args.extend(["--config", c])

cmd = ["semgrep", *config_args, str(target), "--json", "--quiet"]
```

**Rules:**
- Each rule/path gets its own `--config` flag — Semgrep supports multiple.
- An empty `extra_rules` list is a no-op; existing default behaviour is preserved.
- `rules_path` takes precedence over the default rules when provided, as before.

**Problem B — Per-file progress events undeliverable:**  
Semgrep's `--json` output is emitted only when the scan completes — there are no
intermediate per-file events. The Phase 3 plan promised "emit progress events every
10 files" which cannot be implemented without parsing `--verbose` stderr output
(fragile and not worth the coupling).

**Fix: coarse lifecycle progress instead:**

```python
await bus.publish_progress("semgrep", 0, "")
await bus.publish_log("info", "Semgrep scan started — results available on completion")

# ... subprocess runs ...

await bus.publish_progress("semgrep", 100, "")
```

The SSE stream will show 0% → 100% with no intermediate steps. This is honest
and clearly distinguishable from a scanner that supports per-file progress.

Add a comment in the code:
```python
# Semgrep JSON output is atomic — no per-file progress available.
# Coarse 0%/100% lifecycle events are emitted instead.
```

**Update `tests/test_plugin_semgrep.py`:**
- Add test: config with `extra_rules: ["p/jwt"]` → CLI is called with
  `--config p/python --config p/security-audit --config p/jwt`.
- Add test: config with both `rules_path` and `extra_rules` → `rules_path` is
  first, extra rules appended.
- Add test: empty `extra_rules` → CLI unchanged from default behaviour.

**Commit:** `fix(semgrep): implement extra_rules config + honest progress events`

---

### Step 4 — Implement Vulture `whitelist_path`

**The problem:**  
`config.get("whitelist_path")` is never read by the plugin. A user who provides a
Vulture whitelist file to suppress false positives gets no benefit.

**Fix in `plugins/quality/vulture_plugin.py`:**

In the CLI construction:
```python
cmd = ["vulture", str(target), f"--min-confidence={min_confidence}"]

whitelist_path = config.get("whitelist_path")
if whitelist_path:
    whitelist = Path(whitelist_path)
    if whitelist.exists():
        cmd.append(str(whitelist))
    else:
        await bus.publish_log(
            "warning",
            f"Vulture whitelist_path '{whitelist_path}' does not exist — ignored"
        )
```

Vulture accepts a whitelist as a positional argument after the target:
`vulture target/ whitelist.py --min-confidence=60`

**Rules:**
- If `whitelist_path` is provided but does not exist: log a warning and continue
  without it — never crash or return `[]` for a bad config value.
- If `whitelist_path` is `None` or `""`: no-op, existing behaviour preserved.
- The whitelist path can be absolute or relative to the project root. Resolve it
  relative to `target` if it is not absolute.

**Update `tests/test_plugin_vulture.py`:**
- Add test: config with valid `whitelist_path` → CLI includes the whitelist path.
- Add test: config with non-existent `whitelist_path` → warning logged, scan
  continues without it, `[]` is not returned.
- Add test: config with no `whitelist_path` → CLI unchanged.

**Commit:** `fix(vulture): implement whitelist_path config key`

---

### Step 5 — Document `force_rescan` intent in orchestrator

**The problem:**  
`force_rescan` is defined in `Settings` and exposed in `settings.schema.json`
but currently has no effect. This is acceptable — caching is a later phase —
but it is undocumented, so future developers may assume it works or accidentally
implement caching without honouring it.

**Fix in `orchestrator.py`:**

At the top of `_run_job`, add:

```python
# force_rescan flag is defined but not yet honoured.
# When the SQLite result cache is implemented (Phase 5/6), this flag
# will bypass it and re-run all scanners unconditionally.
# For now, every run is a full scan regardless of this setting.
_ = settings.force_rescan  # acknowledged, not yet used
```

No logic change. This is documentation only and prevents the `mypy --strict`
"assigned but never used" warning if it exists.

**Additionally**, add a note to `docs/PHASE3_PLAN.md` under "What Phase 3 Does
NOT Include":

```
| SQLite result cache / force_rescan honour | Phase 5 — force_rescan is
  accepted in settings but currently a no-op; every run is a full scan.
```

**Commit:** `docs(orchestrator): document force_rescan as not-yet-implemented`

---

### Step 6 — Final tag

After all tests pass:

```bash
cd ~/my_tools/nexus_audit_v3
pytest --tb=short -q         # must exit 0
mypy core/ plugins/ api/ orchestrator.py server.py --strict
ruff check .
git add -A
git commit -m "feat: Phase 3.2 complete — scanner layer hardening"
git tag v0.3.2
```

---

## What Phase 3.2 Does NOT Include

| Excluded | Reason |
|----------|--------|
| SQLite caching | Phase 5/6 — `force_rescan` is documented as no-op for now |
| New scanner plugins | Phase 3 plugin set is complete for now |
| Frontend | Phase 4 |
| Semgrep per-file progress | Not achievable with `--json` output; documented as coarse lifecycle events |
| Changing any public API | No breaking changes to REST endpoints or SSE format |

## Scanner Tool Availability Policy (Reminder)

Unchanged from Phase 3. Every scanner must satisfy:

```
Tool installed  → scan() runs, returns findings
Tool missing    → scan() emits LOG warning, returns []
Bad config      → LOG warning, use safe default, never crash
Network timeout → caught by asyncio.wait_for, ScanResult.error set
```

---

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| `pathspec` in mandatory deps | It is a core runtime dependency, not a scanner tool. Keeping it optional was a classification error |
| Severity filter after construction | Keeps mapping logic and filtering logic separate — easier to test each independently |
| Coarse Semgrep progress (0%/100%) | Honest is better than broken. Per-file progress would require `--verbose` stderr parsing — fragile, not worth it |
| Whitelist path as positional arg | This is Vulture's documented interface; `--exclude` is for directory patterns, not whitelist files |
| `force_rescan` as no-op with comment | Explicit documentation prevents both accidental "fix" attempts and silent future breakage |

---

## Definition of Done — Phase 3.2

- [ ] `load()` in `core/settings.py` decrypts `api_key` — confirmed in code and tests
- [ ] `pathspec` is in `[project.dependencies]`, not in `[project.optional-dependencies]`
- [ ] `pip install -e .` (no extras) → `import pathspec` succeeds
- [ ] Bandit `severity_filter: "high"` → only HIGH findings returned
- [ ] Bandit `severity_filter: "medium"` → LOW findings absent
- [ ] Bandit unknown `severity_filter` value → warning + all findings returned
- [ ] Semgrep `extra_rules: ["p/jwt"]` → `--config p/jwt` in CLI call
- [ ] Semgrep progress emits 0% on start and 100% on completion only
- [ ] Vulture `whitelist_path` is passed to CLI when valid
- [ ] Vulture non-existent `whitelist_path` → warning, scan continues
- [ ] `orchestrator.py` has `force_rescan` no-op comment
- [ ] `mypy ... --strict` exits 0
- [ ] `pytest --tb=short -q` exits 0 (all prior tests + new tests)
- [ ] `ruff check .` exits 0
- [ ] `git tag v0.3.2` exists

---

*Plan written: 2026-05-28 | Follows: Phase 3 (`v0.3.0`) | Precedes: Phase 4 (Frontend)*
