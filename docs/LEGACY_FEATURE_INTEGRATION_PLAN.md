# Nexus Audit — Legacy Feature Inventory & v3 Integration Plan

**Subject:** Feature gap analysis between `nexus_audit` (legacy) and `nexus_audit_v3` (rewrite), with a prioritized plan for porting legacy capabilities into the v3 architecture.
**Legacy path:** `~/my_tools/nexus_audit/`
**v3 path:** `~/my_tools/nexus_audit_v3/`
**Date:** June 20, 2026
**Method:** Direct inspection of both codebases' source files (not derived from documentation — see §2).

---

## 1. Executive Summary

`nexus_audit_v3` is a genuine architectural rewrite, not a refactor: an async REPL CLI with a command-bus pattern, multi-project workspace support, a plugin-based scanner registry, an `aiohttp` backend, and a 51-file test suite (legacy has none of this — it is a single hardcoded-for-Nexus script with one developer-facing test file). On raw static-analysis breadth, v3 already exceeds legacy, running nine scanner types legacy never had (Semgrep, TruffleHog, Secretscrub, Ruff, Pylint, Mypy, ESLint, djLint, Lizard).

However, the rewrite has not yet carried over legacy's most distinctive and heavily-engineered capabilities. The single largest gap is the **AI-powered recommendation engine** — a five-layer system with multi-model fallback, quota-aware key rotation, and best-of-N sampling — which is the feature legacy spent the most iteration on (per project history) and which v3 currently implements only as a stub. Several other backend engines in v3 already compute the right data (coupling matrix, score timeline, fix queue) but have **no frontend to display it** — the dashboard router defines 12 views and 9 of them render literal "coming soon" placeholder cards. One v3 engine (circular-dependency detection) was also found to have **reintroduced a bug legacy had deliberately fixed** (unbounded recursion instead of an iterative traversal) — see §6.3.

This document inventories every legacy feature, confirms its current state in v3 by reading the actual code (not v3's own design docs, which are themselves sometimes ahead of what's implemented), and proposes a phased integration order.

| # | Feature | State in v3 | Priority |
|---|---|---|---|
| 1 | AI recommendation engine (5 layers) | Stub only | **Critical** |
| 2 | Django/Celery-aware boundary config | Engine ready, no config | **High** |
| 3 | Circular dependency detection | Exists but unsafe + inactive | **High** |
| 4 | Holistic Config Health scanner | Partial (1 of 6 areas) | **High** |
| 5 | Tier 2 dependency intelligence (Vault) | Partial, unwired cache | **High** |
| 6 | Interactive dependency graph | Backend partial, UI placeholder | Medium-High |
| 7 | Coupling map UI | Backend done, UI placeholder | Medium |
| 8 | Trends / timeline UI | Backend done, UI placeholder | Medium |
| 9 | Fix queue — API + UI | Backend done, no API/UI | Medium |
| 10 | Downloadable Markdown reports | Thin version exists | Medium |
| 11 | Watch mode | Not present | Low |
| 12 | CLI/server conveniences | Not present | Low |

---

## 2. Methodology & Caveats

Both projects' own documentation was read first, then **verified against the live source**, because both were found to drift from what they describe:

- Legacy's `docs/HANDOVER_v3.md` describes report generation via `report/html_report.py` and a `dashboard_template.html` string-template file. Neither file exists anymore — the current package only has `report/markdown_report.py` and `report/assets.py`; the actual HTML dashboard is a static SPA shell (`visuals/index.html`) that fetches `data.json` client-side. The handover doc predates that change.
- Legacy's docs (`HANDOVER_v3.md`, `NEXUS_AUDIT_CODEX_v4.md`, `NEXUS_AUDIT_USAGE_GUIDE.md`) all document a `pulse.py --install-hook` flag for installing a git pre-commit hook. It does not exist in the current `main.py` argparse definition. Treated here as a documented-but-removed feature, not a real gap.
- `nexus_audit/report/markdown_report.py` defines `generate_comprehensive_markdown()`, but no caller of it exists anywhere in the current package (verified by grep across `nexus_audit/`, `pulse.py`, `pulse.sh`). The `AUDIT_REPORT_COMPREHENSIVE.md` file the dashboard's download button serves from is read directly off disk by `features/server.py`, not regenerated — so today the "Full Report" download only works if that file happens to already exist from some earlier process. This is itself a small legacy bug worth knowing about before treating that code path as a finished reference implementation.
- v3's own `docs/` folder (CLI_SPECIFICATIONS.md, PLUGINS_REFACTOR.md, API_BACKEND_REFACTOR.md, etc.) is large (~9,000 lines) and describes target architecture more confidently than the code currently delivers in places — most notably the AI module and most frontend views. All v3 gap claims in §6 are backed by reading `orchestrator.py`, the relevant `core/engines/`, `core/primitives/commands/handlers/`, `api/routes_*.py`, and `frontend/js/` files directly, not the docs.

---

## 3. Architectural Context — Read Before Integrating

Legacy and v3 do not share a shape, so this is not a copy-paste port:

- **Entry point:** Legacy is a one-shot `argparse` script (`pulse.py` → `main()`) that runs top to bottom and exits. v3 is a persistent `asyncio` REPL (`cli.py` → `NexusCLI._run_async()`) where commands flow through `CommandRegistry` → `CommandParser` → handler → `CommandContext` → renderer, with one event loop alive for the whole session so background jobs and SSE streams can run concurrently with the prompt.
- **Project scope:** Legacy is hardcoded to one project (the Nexus codebase, with paths baked into `config.py`). v3 has a multi-project `Workspace` with project IDs, registered via `SettingsManager`, and per-project job history under `~/.nexus_audit/projects/{project_id}/jobs/{job_id}/`.
- **Scanning:** Legacy hand-rolls each scanner call inline in `scanners.py`/`dependency.py`. v3 has a `PluginRegistry` of `BaseScanner` subclasses, auto-discovered and run in parallel via `asyncio.gather`.
- **Server:** Legacy's `--serve` is a hand-rolled `ThreadingHTTPServer` subclass with manual routing. v3 uses `aiohttp` with a real router (`api/server.py`) and a more robust SSE implementation (it supports `Last-Event-ID` replay for reconnects; legacy's does not).
- **Orchestration:** Legacy's `main()` does everything procedurally. v3 has a single `Orchestrator` class, instantiated once at CLI startup, that runs a fixed 13-phase pipeline (`setup → source_sync → dna_build → fast_check → load_rules → run_scanners → evaluate_rules → score_apps → coupling_matrix → timeline → fix_queue → git_context → write_output`) and publishes progress over an `EventBus`.

**Practical implication:** every gap below should be re-implemented as a new phase/engine/route inside v3's existing pipeline and command pattern, not dropped in as a ported legacy file.

---

## 4. What v3 Already Does Better

- **Scanner breadth.** Nine scanner types with no legacy equivalent: Semgrep, TruffleHog, Secretscrub, Ruff, Pylint, Mypy, ESLint, djLint, and Lizard as a first-class plugin.
- **Real test suite.** 51 test files under `tests/`. Legacy has one ad hoc script.
- **VEX suppression support.** `api/routes_config.py` exposes `GET/POST/DELETE /api/vex`.
- **Privilege levels.** `READONLY` / `OPERATOR` / `ADMIN` / `SYSTEM` gating per command.
- **More robust SSE.** `routes_stream.py` supports `Last-Event-ID`-based event replay on reconnect.
- **Scanner self-management API.** `/api/scanners/status` and `/api/scanners/install`.
- **Extensible custom rules.** v3's `rules_engine.py` supports a generic tree-sitter-style `pattern` rule type.

---

## 5. Confirmed Feature Parity (no action needed)

| Legacy capability | Legacy location | v3 equivalent |
|---|---|---|
| Bandit / Vulture / Radon scanning | `nexus_audit/scanners.py` | `plugins/security/bandit_plugin.py`, `plugins/quality/vulture_plugin.py`, `plugins/quality/radon_plugin.py` |
| Ghost file detection | `audit_engine.py::is_ghost_file` | `core/engines/scoring_engine.py` (via `imported_by` graph) |
| App-level scoring | `audit_engine.py::calculate_app_score` | `core/engines/scoring_engine.py::calculate_scores` |
| Cross-app boundary classification | `audit_engine.py::classify_connection` | `core/engines/boundary_engine.py::BoundaryEngine` |
| Fast/changed-file-only scanning | `features/quick_check.py` | `core/infra/fast_check.py` |
| Git context | `audit_engine.py::get_git_context` | `core/infra/git_context.py` |
| Atomic JSON writes | `main.py` | `core/primitives/atomic.py::write_json` |
| Per-run history | timestamped files | `~/.nexus_audit/projects/{id}/jobs/{job_id}/` |
| Run / Cancel control | `features/server.py` | `api/routes_run.py` |
| Live log streaming | `features/server.py` SSE | `api/routes_stream.py` |

---

## 6. Feature Gaps — Detailed Inventory

### 6.1 AI-Powered Recommendation Engine — CRITICAL

**Legacy files:** `nexus_audit/ai/backend.py`, `ai/recommendations.py`, `ai/prompts.py`, `key_pool.py`

Five layers: per-violation refactoring analysis (top 5, best-of-2 sampling for top 2), per-app health narratives (apps below 90%), shared-utility extraction plans, outdated-package upgrade advice, CVE remediation guidance.

Supporting infrastructure: Ollama → Gemini (19 models, 20-key rotation) → Claude → template fallback chain; task-specialized model routing; pre-flight quota probing; best-of-N response scoring; JSON extraction from malformed LLM output; 4s inter-call pacing; violation-persistence-aware prompting.

**v3 state:** `ai:recommend` is a literal stub. `routes_ai.py` only diagnoses scanner failures. `orchestrator.py` hardcodes `recommendations: []`.

### 6.2 Django/Celery-Aware Boundary Configuration — HIGH

**Legacy files:** `audit_engine.py::classify_connection` — `BOOTSTRAP_LEAVES`, Signal/Celery exemptions, hub-app treatment.

**v3 state:** `boundary_engine.py` is well-designed but has zero Nexus-specific configuration. `default_action` defaults to `"allow"` — meaning it silently passes everything through today.

### 6.3 Circular Dependency Detection — HIGH

**Legacy files:** `audit_engine.py::find_circular_dependencies_accurate` — iterative DFS, Django-models self-cycle suppression.

**v3 state:** `rules_engine.py::_evaluate_cycle` uses recursive DFS (same crash risk legacy fixed). No `cycle` rule in `default_rules.yaml` so the detector never runs.

### 6.4 Holistic Config Health Scanner — HIGH

**Legacy files:** `config_health.py` (409 lines) — 20 checks across `settings.py`, `asgi.py`, `wsgi.py`, `urls.py`, `celery.py`, unexpected-file detection. Single weighted 0-100 score.

**v3 state:** `django_settings_plugin.py` covers `settings.py` only (4 checks). `orchestrator.py` hardcodes `config_health: []`.

### 6.5 Tier 2 Dependency Intelligence — HIGH

**Legacy files:** `config.py` (PyPI freshness + OSV.dev CVE) + `dep_cache.py` (risk-tiered TTL: 24h/48h/168h).

**v3 state:** `safety_plugin.py` does CVE only (via `pip-audit`). `dep_cache.py` exists but nothing calls it. No PyPI freshness check anywhere. `orchestrator.py` hardcodes `dependency_scan: []`.

### 6.6 Interactive Dependency Graph — Medium-High

**Legacy files:** `visuals/js/components/graph.js` (788 lines) + `physics.worker.js` — force-directed graph, 3 interaction modes, cycle highlighting.

**v3 state:** `graph` view is a placeholder card. No graph code in frontend.

### 6.7 Coupling Map UI — Medium

**Legacy files:** `features/coupling_map.py` + `tabs.js::generateCouplingMapTab` — color-coded heatmap with drill-down.

**v3 state:** `coupling.py` backend is complete and wired. Frontend `coupling` view is a placeholder.

### 6.8 Trends / Timeline UI — Medium

**Legacy files:** `features/timeline.py` + `trends.js` — per-app score history over 30 runs.

**v3 state:** `timeline.py` backend is complete and wired. Frontend `trends` view is a placeholder.

### 6.9 Fix Queue — API + UI — Medium

**Legacy files:** `features/fix_queue.py` — hash-stable IDs, open/in_progress/done/snoozed, regression detection. Exposed via `GET/PUT /fix-queue`.

**v3 state:** `fix_queue.py` engine exists and runs. No API endpoint. No frontend view.

### 6.10 Downloadable Markdown Reports — Medium

**Legacy files:** `report/markdown_report.py` (670 lines) — comprehensive full report, per-app variant, per-category variant (8 categories). Served via `/api/download/report/*`.

**v3 state:** `core/reports/markdown_report.py` (106 lines) — thin summary only. No API download endpoint.

### 6.11 Watch Mode — Low

**Legacy files:** `features/server.py` — `watchdog`-based file monitoring, triggers re-run on `.py` file change.

**v3 state:** not present anywhere.

### 6.12 CLI/Server Conveniences — Low

WSL-aware browser auto-launch, OSC 8 clickable terminal links, ASCII startup banner. None present in v3.

---

## 7. Recommended Integration Roadmap

| Phase | Items | Rationale |
|---|---|---|
| 1 — Make audit correct | §6.2 boundary config, §6.3 cycle detection | Cheapest, highest trust impact. v3 findings cannot be trusted until these are done. |
| 2 — Restore intelligence | §6.1 AI engine, §6.4 Config Health, §6.5 Dependency Vault | Highest effort, highest value. |
| 3 — Surface existing backend | §6.7 Coupling UI, §6.8 Trends UI, §6.9 Fix Queue API+UI | Backend already done. Pure wiring and frontend work. |
| 4 — Visualization & polish | §6.6 Graph, §6.10 Reports, §6.11 Watch mode, §6.12 conveniences | Graph is substantial effort; sequenced last. |

---

## 8. Risk Notes

- Treat legacy files as a reference for behavior, not code to copy-paste. Legacy is bug-prone.
- v3's clean rewrite is not automatically safer — §6.3 proves this.
- Write tests for every feature ported, using v3's existing `tests/engines/` convention.
- Confirm `default_action` in `BoundaryEngine` before trusting "0 violations" results.

---

## Appendix: Legacy Source Map

| Area | File(s) |
|---|---|
| CLI / orchestration | `pulse.py`, `nexus_audit/main.py` |
| Config / PyPI / OSV | `nexus_audit/config.py` |
| Boundary, scoring, cycles, git | `nexus_audit/audit_engine.py` |
| Scanners | `nexus_audit/scanners.py` |
| Config Health | `nexus_audit/config_health.py` |
| Dependency cache | `nexus_audit/dep_cache.py` |
| Key rotation | `nexus_audit/key_pool.py` |
| AI backend | `nexus_audit/ai/backend.py` |
| AI prompts | `nexus_audit/ai/prompts.py` |
| AI recommendations | `nexus_audit/ai/recommendations.py` |
| Coupling matrix | `nexus_audit/features/coupling_map.py` |
| Fix queue | `nexus_audit/features/fix_queue.py` |
| Timeline | `nexus_audit/features/timeline.py` |
| Server / watch mode | `nexus_audit/features/server.py` |
| Markdown reports | `nexus_audit/report/markdown_report.py` |
| Dashboard SPA | `visuals/index.html`, `visuals/css/styles.css` |
| Graph visualization | `visuals/js/components/graph.js`, `visuals/js/physics.worker.js` |
| Dashboard tabs | `visuals/js/components/tabs.js` |
| Recommendations UI | `visuals/js/components/recommendations.js` |
| Trends chart | `visuals/js/components/trends.js` |
