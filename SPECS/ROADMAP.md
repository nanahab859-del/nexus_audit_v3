# Legacy Feature Integration — Roadmap

**Branch:** `feature/legacy-feature-integration`
**Worktree:** `~/my_tools/nexus_audit_v3_features/`
**Reference document:** `docs/LEGACY_FEATURE_INTEGRATION_PLAN.md` (untracked, in both repos)

---

## Working Rules

These apply to every feature, without exception:

1. **One feature at a time.** Do not start the next feature until the current one is fully implemented, tested, and merged.
2. **Research before spec.** For each feature, first research the best way to implement it in v3's architecture — not how legacy did it.
3. **Spec before code.** Write a spec in `specs/features/` for the feature. No code changes until the spec exists and is agreed on.
4. **This worktree only.** All changes happen in `nexus_audit_v3_features/` on `feature/legacy-feature-integration`. Nothing touches `nexus_audit_v3/` directly.
5. **Merge by review.** When a feature is done, it is reviewed before merging into `main`. Nothing lands in `main` without that review.
6. **Legacy is a reference for what, not how.** Legacy tells us what the feature is supposed to do. It does not dictate the implementation. v3's architecture (plugin system, rules engine, YAML, async orchestrator) is the target — we find the best way to express the feature there.

---

## Feature List and Sequence

Taken from `docs/LEGACY_FEATURE_INTEGRATION_PLAN.md`. Sequence follows the roadmap in that document (Phase 1 → Phase 4), with research order within each phase based on complexity and dependency.

### Phase 1 — Make the audit correct and trustworthy

These two must come first. Until they are done, v3's output cannot be trusted on the Nexus codebase.

---

#### Feature 1: Circular Dependency Detection

**What it is:** Detect when two or more modules import each other in a circle — A imports B, B imports A. This is a real architectural problem that causes subtle runtime bugs in Django.

**What v3 has today:** A `cycle` rule type exists in `rules_engine.py` but the internal algorithm is unsafe (can crash on large projects). Also, no `cycle` rule exists in `default_rules.yaml`, so the detector never actually runs regardless.

**What needs to happen:**
- Research: what is the safest, best algorithm for this? How does it fit v3's rules engine?
- Spec: write `specs/features/01_circular_dependency_detection.md`
- Implement

**Status:** ✅ Done — implemented, tested (28/28), merged.

---

#### Feature 2: App Boundary Enforcement

**What it is:** Detect when a module in one app imports directly from another app in a way that breaks the agreed architectural boundaries (which apps can talk to which, and under what conditions).

**What v3 has today:** `boundary_engine.py` exists and is well designed, but has no Nexus-specific configuration. Its default behavior passes everything through without flagging violations.

**What needs to happen:**
- Research: how should Nexus's boundary rules be expressed in v3's architecture? YAML rules? Config? Plugin?
- Spec: write `specs/features/02_app_boundary_enforcement.md`
- Implement

**Status:** Not started

---

### Phase 2 — Restore signature intelligence

The three features that made the legacy tool distinctively useful, beyond what any generic linter does.

---

#### Feature 3: AI Recommendation Engine

**What it is:** After an audit run, generate specific, actionable fix recommendations for the violations found. In legacy this was a five-layer system: per-violation fixes, per-app health narratives, shared-utility extraction plans, outdated-package upgrade advice, and CVE remediation guidance.

**What v3 has today:** `ai:recommend` exists as a literal stub — it prints "not yet implemented." The AI infrastructure (`routes_ai.py`) only handles diagnosing scanner failures, not generating recommendations.

**What needs to happen:**
- Research: what is the right shape for an AI recommendation engine inside v3's async plugin/orchestrator architecture? How should multi-model fallback work? How does it connect to the existing settings (ai_provider, ai_model)?
- Spec: write `specs/features/03_ai_recommendation_engine.md`
- Implement

**Status:** Not started

---

#### Feature 4: Config Health Scanner

**What it is:** A dedicated scanner that checks Django configuration files specifically — `settings.py`, `asgi.py`, `wsgi.py`, `urls.py`, `celery.py` — for correctness, security, and architectural cleanliness. Produces a single weighted score with per-check detail.

**What v3 has today:** `django_settings_plugin.py` covers `settings.py` only (about a quarter of what legacy did), and its output is mixed in with generic security findings rather than being a separate scored section.

**What needs to happen:**
- Research: how should a multi-file config health scanner be structured as a v3 plugin? How does a dedicated config health score surface in the orchestrator output?
- Spec: write `specs/features/04_config_health_scanner.md`
- Implement

**Status:** Not started

---

#### Feature 5: Dependency Intelligence (Vault)

**What it is:** Check every dependency for two things: whether it is outdated (newer version available on PyPI), and whether it has known CVEs (via OSV.dev). Cache results intelligently so repeated runs are fast — longer cache for clean packages, shorter for risky ones.

**What v3 has today:** `safety_plugin.py` checks CVEs only (via `pip-audit`). A cache module (`dep_cache.py`) exists but is not connected to anything — `orchestrator.py` hardcodes `dependency_scan: []`. No outdated-version checking exists.

**What needs to happen:**
- Research: how should PyPI freshness checking and risk-tiered caching be structured as a v3 plugin? How does it combine with the existing CVE plugin output?
- Spec: write `specs/features/05_dependency_intelligence.md`
- Implement

**Status:** Not started

---

### Phase 3 — Surface what the backend already computes

These three features have working backend logic already in v3. The gap is the API and frontend layer.

---

#### Feature 6: Coupling Map UI

**What it is:** A visual heatmap showing how much each app depends on every other app — a matrix of coupling strength, with drill-down to see the specific imports driving it.

**What v3 has today:** `coupling.py` already builds the matrix and the orchestrator runs it. The frontend `coupling` view is a placeholder card.

**What needs to happen:**
- Research: what is the right frontend approach for this in v3's SPA structure?
- Spec: write `specs/features/06_coupling_map_ui.md`
- Implement

**Status:** Not started

---

#### Feature 7: Trends / Timeline UI

**What it is:** Charts showing how each app's health score has changed across runs over time — so you can see if things are getting better or worse.

**What v3 has today:** `timeline.py` already computes the history and the orchestrator runs it. The frontend `trends` view is a placeholder card.

**What needs to happen:**
- Research: what chart library/approach fits v3's frontend?
- Spec: write `specs/features/07_trends_timeline_ui.md`
- Implement

**Status:** Not started

---

#### Feature 8: Fix Queue — API and UI

**What it is:** An interactive list of recommended fixes with status tracking — open, in progress, done, snoozed. Marks a fix as "reappeared" if it was marked done but comes back in a later run.

**What v3 has today:** `fix_queue.py` computes and fingerprints items. No API endpoint exists to read or update them. No frontend view.

**What needs to happen:**
- Research: how should fix queue status be persisted and exposed via the aiohttp API?
- Spec: write `specs/features/08_fix_queue.md`
- Implement

**Status:** Not started

---

### Phase 4 — Visualization and polish

---

#### Feature 9: Interactive Dependency Graph

**What it is:** A force-directed visual graph of all modules and their import connections, with three interaction modes: normal, separated by app, and edge inspection. Cycle paths are highlighted.

**What v3 has today:** The `graph` frontend view is a placeholder card. No graph code of any kind exists in v3's frontend. The data is already available from `dna_builder.py`.

**What needs to happen:**
- Research: what is the right graph visualization approach for v3's frontend?
- Spec: write `specs/features/09_dependency_graph.md`
- Implement

**Status:** Not started

---

#### Feature 10: Downloadable Markdown Reports

**What it is:** Full audit reports downloadable from the dashboard — a comprehensive full report, per-app reports, and per-category reports (complexity, violations, security, dependencies, etc.).

**What v3 has today:** A thin `markdown_report.py` exists and is wired to a CLI command, but it covers only a fraction of the content and has no API endpoint for dashboard download.

**What needs to happen:**
- Research: what sections should the v3 report cover? How should the download API be structured?
- Spec: write `specs/features/10_markdown_reports.md`
- Implement

**Status:** Not started

---

#### Feature 11: Watch Mode

**What it is:** Automatically re-run the audit whenever a Python file changes in the project being audited, without the user having to manually trigger it.

**What v3 has today:** Nothing. No file-watching exists anywhere in the codebase.

**What needs to happen:**
- Research: how does file-watching fit into v3's async orchestrator? What library?
- Spec: write `specs/features/11_watch_mode.md`
- Implement

**Status:** Not started

---

#### Feature 12: CLI and Server Conveniences

**What it is:** Small quality-of-life items — WSL-aware browser auto-launch when the server starts, clickable terminal links, startup banner.

**What v3 has today:** None of these.

**What needs to happen:**
- Research: which of these are worth the effort in v3's architecture?
- Spec: write `specs/features/12_cli_conveniences.md`
- Implement

**Status:** Not started

---

## Current Position

Starting with **Feature 2: App Boundary Enforcement** — research phase.
