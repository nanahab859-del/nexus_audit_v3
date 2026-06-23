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

**Practical implication:** every gap below should be re-implemented as a new phase/engine/route inside v3's existing pipeline and command pattern, not dropped in as a ported legacy file. Several gaps already have a natural home called out in §6 (e.g., a new `core/engines/ai_engine.py` invoked from a new orchestrator phase, mirroring how `scoring_engine.py` or `coupling.py` are already wired in).

---

## 4. What v3 Already Does Better

For balance, since the rewrite is not a regression across the board:

- **Scanner breadth.** Nine scanner types with no legacy equivalent: Semgrep (SAST pattern matching), TruffleHog and Secretscrub (credential/secret scanning), Ruff, Pylint, Mypy, ESLint (legacy has no JS/TS support at all), djLint (Django template linting), and Lizard as a first-class architecture-category plugin rather than a complexity fallback.
- **Real test suite.** 51 test files under `tests/`, including dedicated tests for the boundary engine and rules engine. Legacy has one ad hoc script (`test_md.py`).
- **VEX suppression support.** `api/routes_config.py` exposes `GET/POST/DELETE /api/vex`, an industry-standard vulnerability-exploitability-exchange suppression format legacy never had.
- **Privilege levels.** `READONLY` / `OPERATOR` / `ADMIN` / `SYSTEM` gating per command — legacy has no access control concept at all.
- **More robust SSE.** `routes_stream.py` supports `Last-Event-ID`-based event replay on reconnect via `EventBus.get_history()`; legacy's SSE stream has no reconnect/replay handling.
- **Scanner self-management API.** `/api/scanners/status` and `/api/scanners/install` let the tool report and install missing external tools (e.g. missing `bandit` binary) — legacy just fails the scan silently or with a raw error.
- **Extensible custom rules.** v3's `rules_engine.py` supports a generic tree-sitter-style `pattern` rule type (see `default_rules.yaml`'s `no-eval` rule) — a more general mechanism than legacy's hardcoded Bandit-only security checks.

---

## 5. Confirmed Feature Parity (no action needed)

| Legacy capability | Legacy location | v3 equivalent |
|---|---|---|
| Bandit / Vulture / Radon scanning | `nexus_audit/scanners.py` | `plugins/security/bandit_plugin.py`, `plugins/quality/vulture_plugin.py`, `plugins/quality/radon_plugin.py` |
| Ghost file detection | `audit_engine.py::is_ghost_file` | `core/engines/scoring_engine.py` (via `imported_by` graph) |
| App-level scoring | `audit_engine.py::calculate_app_score` | `core/engines/scoring_engine.py::calculate_scores` (config-driven via `ScoringConfig`) |
| Cross-app boundary classification | `audit_engine.py::classify_connection` | `core/engines/boundary_engine.py::BoundaryEngine` (generalized, config-driven — see §6.1) |
| Fast/changed-file-only scanning | `features/quick_check.py` | `core/infra/fast_check.py` + `Orchestrator.start_job(fast_mode=True)` |
| Git context (branch/commit/remote) | `audit_engine.py::get_git_context` | `core/infra/git_context.py` |
| Atomic JSON writes | `main.py` (tmp + `os.replace`) | `core/primitives/atomic.py::write_json` |
| Per-run history | timestamped files in legacy's history dir | `~/.nexus_audit/projects/{id}/jobs/{job_id}/` per-job directories |
| Run / Cancel control | `features/server.py` `/api/run`, `/api/cancel` | `api/routes_run.py::start_run`, `cancel_run` |
| Live log streaming | `features/server.py` SSE | `api/routes_stream.py::stream` (more robust — see §4) |

---

## 6. Feature Gaps — Detailed Inventory

### 6.1 AI-Powered Recommendation Engine — **CRITICAL**

**Legacy:** `nexus_audit/ai/backend.py`, `ai/recommendations.py`, `ai/prompts.py`, `key_pool.py` (combined ~1,800 lines)

This is legacy's signature feature and the single largest gap. It is a five-layer system:

1. **Per-violation refactoring analysis** — deep, structured fix recommendations for the top 5 violations by impact, with best-of-2 sampling (two model calls, the more complete response wins) for the top 2.
2. **Per-app health narratives** — for any app scoring below 90%, a plain-language explanation of what's dragging the score down.
3. **Shared-utility extraction plans** — for modules imported cross-app by 2+ apps (a signal computed in legacy's `main.py`, not currently computed anywhere in v3), a structured plan for extracting them into a shared location.
4. **Outdated-package upgrade advisor** — migration guidance for stale dependencies.
5. **CVE security advisor** — remediation guidance for the top critical CVEs found.

Supporting infrastructure, all specific to making this reliable on a free-tier API budget:

- **Backend priority chain:** Ollama (free/local) → Gemini (free tier, 19 models) → Claude API (paid fallback) → deterministic templates.
- **Task-specialized routing:** 6 task types, each with its own ranked model preference list (`ai/prompts.py::TASK_MODELS`).
- **`KeyPool`** (`key_pool.py`): rotates up to 20 Gemini API keys round-robin, prefers the first/most-reliable key for heavy tasks, tracks per-key RPM cooldowns (65s) and daily exhaustion independently.
- **Pre-flight quota probing:** sends a 1-token probe to every candidate model before the real run so the engine knows what's actually available, rather than discovering exhaustion mid-run.
- **Best-of-N sampling:** scores candidate responses by structural completeness (required fields present, before/after code included, etc.) and keeps the best one.
- **Robust JSON extraction** from LLM output: strips markdown fences, recovers from brace-depth-truncated responses.
- **Rate-limit governance:** 4s inter-call pacing, a 5-call cap on violation analysis per run, abort after 2 consecutive 429s.
- **Tier-1 template fallback** (`ai/recommendations.py::generate_recommendations`): when no AI backend is available at all, produces deterministic, still-useful recommendations for every violation type (cross-app import, security sub-types, complexity, ghost files, cycles) so the tool is never silent.
- **Violation-persistence-aware prompting:** feeds `timeline.py`'s new/persistent/intermittent/resolved classification into the prompt so the AI knows if a violation has been ignored across runs.

**v3 current state:** `core/primitives/commands/handlers/ai.py` registers `ai:status`, `ai:test`, `ai:recommend` as literal stub handlers (`"[TODO] ... not yet implemented."`). `api/routes_ai.py` implements something narrower and different in purpose: a single `diagnose-scanner-error` endpoint that asks one configured provider (Claude/Gemini/Ollama/custom — selected in Settings, no fallback chain) to explain why a *scanner itself failed to run*, with canned `STUB_ADVICE` strings for three scanner names when no key is configured. There is no violation-recommendation generation, no multi-model fallback, no key rotation, no quota probing, no best-of-N, and no template fallback. `orchestrator.py` confirms this explicitly: `recommendations: List[Any] = []` with the inline comment `# AI Recommendations (STUB — not yet implemented)`.

**Integration note:** the persistence data this engine depends on (`compute_violation_persistence`) already exists and is already wired into the v3 orchestrator (`core/engines/timeline.py`), so that dependency is solved. The natural home is a new `core/engines/recommendation_engine.py` (5-layer logic, ported conceptually rather than line-for-line given legacy's bug history), reusing v3's existing `ai_provider`/`ai_model` settings plumbing from `routes_ai.py`, invoked as a new orchestrator phase, and surfaced through a real `ai:recommend` handler and the `recommendations` frontend view (currently a placeholder — §6.6).

### 6.2 Django/Celery-Aware Boundary Configuration — **HIGH**

**Legacy:** `audit_engine.py::classify_connection` — hardcoded `BOOTSTRAP_LEAVES` (asgi.py, wsgi.py, settings.py, celery.py, manage.py, routing.py, apps.py, admin.py), Signal-module and Celery-task-module exemptions, hub-app bonus treatment.

**v3 current state:** `core/engines/boundary_engine.py::BoundaryEngine` is a clean, generalized reimplementation of the same classification policy (`INTERNAL` / `HUB_APP` / `FRAMEWORK` / `BOOTSTRAP` / `ALLOWED` pattern / `TEST_CROSS_APP` / `VIOLATION`), driven entirely by a `communication_config` dict (`bootstrap_files`, `allowed_patterns` with `fnmatch` globs, `default_action`). The engine itself is good — arguably better-designed than legacy's hardcoded version. The problem: **no project-level config supplying Nexus-specific values exists anywhere in the codebase** (confirmed by grepping for `communication_config`, `hub_apps`, `bootstrap_files`, `allowed_patterns` outside of the engine and its tests). `default_rules.yaml` only contains two unrelated example rules.

This matters more than a typical "missing config" item because of `default_action`'s default value: it defaults to `"allow"`. Without an explicit Nexus configuration, running v3 against the live Nexus codebase today would **not flag real architectural violations as violations** — it would silently allow them, the opposite failure mode from a false-positive flood. Either way, the boundary engine is not usable for its core purpose on this project until configured.

**Integration note:** this is a configuration-authoring task, not a code-porting task — write a `communication_config` (or whatever v3's settings schema calls it) listing Nexus's seven apps as `hub_apps` where appropriate (per project history, `nexus_core`/`nexus_gateway` were treated as hubs), the bootstrap file list ported directly from legacy's `BOOTSTRAP_LEAVES`, and `allowed_patterns` covering the Signal/Celery task exemptions legacy detected by keyword. Cheap to do, high practical impact.

### 6.3 Circular Dependency Detection — Needs Activation + Hardening — **HIGH**

**Legacy:** `audit_engine.py::find_circular_dependencies_accurate` — explicitly rewritten from recursive to **iterative** DFS (per in-code comments) specifically to avoid Python's recursion limit on large/interconnected graphs, plus a special case treating Django's common `models` package self-reference pattern as informational rather than a violation (to avoid noise).

**v3 current state:** cycle detection exists as a rule type inside `core/engines/rules_engine.py::_evaluate_cycle`, but it is implemented with a **recursive** inner `dfs()` function calling itself directly — the exact pattern legacy moved away from. On a large enough import graph this risks a `RecursionError` rather than a clean result. It also has no Django-models self-cycle suppression, so it would likely surface noisy false positives on a Django codebase. On top of that, `default_rules.yaml` defines no `cycle`-type rule at all, so as shipped, this detector never actually runs.

**Integration note:** this is the one place in this report where v3 isn't just "missing a feature" but has reintroduced a specific bug legacy already paid the cost of fixing. Recommend converting `_evaluate_cycle`'s `dfs()` to an explicit stack-based loop (legacy's `audit_engine.py` is a working reference for the iterative approach), adding the Django-models suppression case, then adding an actual `cycle` rule entry to `default_rules.yaml`.

### 6.4 Holistic Config Health Scanner — **HIGH**

**Legacy:** `nexus_audit/config_health.py` (409 lines) — auto-detects the Django config folder, then runs ~20 checks across six file types: `settings.py` (SECRET_KEY sourced from env, DEBUG, ALLOWED_HOSTS, SecurityMiddleware ordering, a Nexus-specific `ENCRYPTION_KEY` check, session/CSRF/SSL cookie flags, INSTALLED_APPS completeness), `asgi.py`/`wsgi.py` (purity — no domain-logic imports), `urls.py` (no direct model/view/serializer imports), `celery.py` (correct bootstrap pattern, `autodiscover_tasks`), and unexpected-file detection. Produces a single weighted 0–100 score with pass/warn/fail detail per check, and the dashboard renders it as an interactive accordion with plain-language explanations per check.

**v3 current state:** `plugins/security/django_settings_plugin.py` (116 lines) covers **only** the `settings.py` portion — SECRET_KEY, DEBUG, ALLOWED_HOSTS, and five SSL/HSTS/cookie flags. It has no equivalent for asgi/wsgi purity, urls.py import discipline, celery.py bootstrap correctness, the Nexus-specific ENCRYPTION_KEY check, or unexpected-file detection. More importantly, it isn't wired into a distinct scored section at all — `orchestrator.py::_build_result` hardcodes `"config_health": []`, so even the partial coverage that exists surfaces only as generic `SECURITY`-category findings mixed in with everything else, not as the dedicated weighted Config Health score legacy's report and dashboard build around.

**Integration note:** extend `django_settings_plugin.py` (or split into per-file-type checks matching legacy's structure) to cover the remaining five check areas, then add a dedicated config-health aggregation step in the orchestrator (a natural new phase between `evaluate_rules` and `score_apps`) that produces the same `{score, checks[], summary}` shape legacy's report/dashboard expect, rather than letting findings disappear into the generic findings list.

### 6.5 Tier 2 Dependency Intelligence (the "Vault") — **HIGH**

**Legacy:** `config.py` (Tier 1/Tier 2 capability detection, PyPI freshness + OSV.dev CVE querying) + `dep_cache.py` (risk-adaptive TTL cache: 24h for CVE-affected packages, 48h for merely-outdated ones, 168h/7 days for clean ones, invalidated on `requirements.txt` hash change or explicit `--force-rescan`).

**v3 current state:** `plugins/dependency/safety_plugin.py` (internally implements a `PipAuditScanner`, despite the filename) shells out to the external `pip-audit` tool for CVE detection only — no PyPI-freshness/outdated-version checking exists anywhere in v3. Separately, `core/infra/dep_cache.py` exists as a near-complete port of the caching mechanism, but it has been simplified to a single flat 24-hour TTL (the risk-tiering logic did not survive the port), and — more importantly — **nothing calls it**. It isn't referenced anywhere in `orchestrator.py` or any plugin; `orchestrator.py::_build_result` hardcodes `"dependency_scan": []` to match. `plugins/dependency/license_plugin.py` adds license-compliance checking, which is a genuinely new capability legacy never had and is worth keeping.

**Integration note:** wire `DepCache` into a new dependency-freshness plugin (PyPI's JSON API, same approach as legacy's `config.py::get_pypi_latest`), restore the three-tier TTL logic, and combine its output with `pip_audit`'s CVE findings into the `dependency_scan` shape the report/dashboard expect. The cache plumbing itself doesn't need to be rebuilt, just connected and risk-tiered.

### 6.6 Interactive Dependency Graph Visualization — **Medium-High**

**Legacy:** `visuals/js/components/graph.js` (788 lines) + `visuals/js/physics.worker.js` — a Web-Worker-driven force-directed graph with three interaction modes: Normal, **Separate Apps** (`toggleSeparation` — spatially clusters nodes by app), and **Inspect Edges** (`toggleInspect` — switches to an SVG bundled-edge overlay with per-bundle hover panels showing individual import details). Includes cycle-path highlighting, a clickable app-filter sidebar, and a dynamic legend. Per project history this was one of the most heavily debugged pieces of the legacy tool (node-overlap, stacking event listeners, variable-shadowing bugs were all fixed here over multiple sessions) — worth treating as nontrivial effort to reproduce, not a quick UI task.

**v3 current state:** `frontend/js/router.js` lists `graph` as one of 12 views; `frontend/js/views/placeholder.js` renders it as a static card reading *"Application dependency graphs will render here in future updates."* No graph rendering code of any kind exists in the v3 frontend. The backend data it would need (modules, imports, app groupings) is already present in `dna_builder.py`'s output, so this is purely a frontend-build task, but a substantial one.

**Integration note:** lowest-risk path is porting `graph.js` and `physics.worker.js` largely as-is (they're self-contained, framework-free JS operating on a generic `{nodes, edges}` shape) and adapting only the data-fetch call to v3's `/api/data` endpoint and `store.js` state shape, rather than rewriting the physics/interaction logic from scratch.

### 6.7 Coupling Map UI — **Medium**

**Legacy:** `nexus_audit/features/coupling_map.py` (violation + allowed-communication 7×7 app matrices with drill-down detail) rendered by `visuals/js/components/tabs.js::generateCouplingMapTab` as a color-coded heatmap with click-through drill-down.

**v3 current state:** the backend computation already exists and is wired in — `core/engines/coupling.py::build_coupling_matrix` runs as orchestrator phase 9 and its output lands in the audit JSON. The frontend `coupling` view, however, is on the `placeholder.js` list. This is a case of the hard part (the matrix-building logic) already being done; only the heatmap rendering needs to be built or ported from `tabs.js`.

### 6.8 Trends / Timeline UI — **Medium**

**Legacy:** `nexus_audit/features/timeline.py::load_score_history` (per-app and fleet-average score history over up to 30 runs) rendered by `visuals/js/components/trends.js`.

**v3 current state:** identical situation to Coupling — `core/engines/timeline.py::load_score_history` is already called from `orchestrator.py` (phase 10) and its output is in the result JSON, but `trends` is on the `placeholder.js` list with no chart rendering built yet.

### 6.9 Fix Queue — Interactive API + UI — **Medium**

**Legacy:** `nexus_audit/features/fix_queue.py` — content-hash-based stable IDs per recommendation, status tracking (open/in_progress/done/snoozed), and regression detection (a recommendation marked "done" reappearing in a later run is flagged `reappeared_done`). Exposed via `GET/PUT /fix-queue` in `features/server.py` and editable from the dashboard.

**v3 current state:** `core/engines/fix_queue.py::FixQueue` exists and is wired into the orchestrator (phase 11, fingerprint-based, the same conceptual approach as legacy). However, grepping `api/*.py` for `fix_queue`/`fix-queue` returns nothing — there is no API endpoint to read or update an individual item's status, and no frontend view consumes it (the `recommendations` view, which is where this would likely surface, is also a placeholder per §6.1). The computation exists; the interactivity layer does not.

**Integration note:** add `GET /api/fix-queue` and `PATCH /api/fix-queue/{id}` routes mirroring legacy's `server.py` handlers, then build the UI once the `recommendations`/issues view is fleshed out.

### 6.10 Downloadable Markdown Reports — **Medium**

**Legacy:** `nexus_audit/report/markdown_report.py` (670 lines) — three generators: a comprehensive full report (capability manifest, executive summary, cycles, ghost files, config health, 15-run trend table, per-app fleet table, test-coverage debt, violations, allowed communications, dependency health, security, complexity with a high-complexity-function table, dead code, recommendations, fix queue, full module manifest), a per-app variant, and a per-category variant (8 categories: complexity, violations, dead_code, security, ghost_files, cycles, config, dependencies) — all downloadable from the dashboard via `/api/download/report/*`.

**v3 current state:** `core/reports/markdown_report.py` (106 lines) exists and is wired to a CLI report-generation command (`core/primitives/commands/handlers/report.py`), but is materially thinner — a fleet score table, a penalty-breakdown table, and the top 50 critical/high or architecture findings. No per-app or per-category variants, no coupling/config-health/dependency/manifest sections, no trend history, and — confirmed by grep — **no API exposure at all**, so there's no dashboard download button equivalent.

**Integration note:** extend `core/reports/markdown_report.py` section-by-section using legacy's `generate_comprehensive_markdown` as the content checklist (noting the caveat in §2 about that function currently being uncalled in legacy itself — review whether legacy's *content structure* is still wanted even though its *invocation* was already dead code), then add the matching `/api/download/report/*` routes.

### 6.11 Watch Mode — **Low**

**Legacy:** `--watch` flag — `watchdog`-based file monitoring (falling back to 30s polling if `watchdog` isn't installed) that triggers a fresh `pulse.py` run whenever a `.py` file changes in the watched root, implemented in `features/server.py`.

**v3 current state:** no equivalent found anywhere in `orchestrator.py`, `cli.py`, or `api/`. Not present in any form.

### 6.12 Minor CLI/Server Conveniences — **Low**

A handful of small quality-of-life features with no v3 equivalent, none individually significant: WSL-aware browser auto-launch on `--serve` startup (tries `cmd.exe /c start` before falling back to Python's `webbrowser` module, since the server runs inside WSL but the browser is on the Windows host), OSC 8 clickable terminal hyperlinks, and the ASCII startup banner. Worth a pass once the higher-priority items are done, not before.

---

## 7. Recommended Integration Roadmap

| Phase | Focus | Items | Rationale |
|---|---|---|---|
| **1** | Make the audit *correct* for Nexus | §6.2 (boundary config), §6.3 (cycle detection fix) | Cheapest items here, and until they're done v3's findings can't be trusted as either complete (boundary) or stable (cycles) on this specific codebase. Do this before anything else. |
| **2** | Restore signature intelligence | §6.1 (AI engine), §6.4 (Config Health), §6.5 (Dependency Vault) | The highest-effort, highest-value items — these are what made legacy worth keeping data from in the first place. |
| **3** | Surface what the backend already computes | §6.7 (Coupling UI), §6.8 (Trends UI), §6.9 (Fix Queue API+UI) | Backend work is done for all three; this phase is close to pure frontend/API-wiring effort with a high value-to-effort ratio. |
| **4** | Visualization & polish | §6.6 (Graph), §6.10 (Reports), §6.11 (Watch mode), §6.12 (conveniences) | Graph is high-value but the most implementation-heavy remaining item; sequenced last because it's the least blocking for day-to-day audit usefulness. |

---

## 8. Risk Notes for Integration

- **Don't port legacy files verbatim.** Legacy is explicitly described as bug-prone, and this review surfaced a concrete example of why: `dependency.py` defines its own `classify_connection` and `find_circular_dependencies_accurate`, duplicating — and silently shadowed by — the versions in `audit_engine.py` that `main.py` actually imports and uses. Treat legacy files as a reference for *behavior*, not a source to copy-paste; re-derive each feature inside v3's plugin/engine pattern.
- **v3's clean rewrite is not automatically safer.** §6.3 is a direct example: the rewrite reintroduced a recursion-limit bug legacy had already fixed. Don't assume v3's newer code is correct by default when porting logic that touches recursive/graph traversal — diff behavior against legacy's fixed version specifically.
- **Write tests as you port.** Legacy has effectively no test coverage; v3 has 51 test files and a real `tests/engines/` convention already established (e.g. `test_boundary_engine.py`, `test_rules_engine.py`). Each ported feature should land with tests in that style rather than reverting to legacy's untested pattern.
- **Confirm `default_action` before relying on boundary results.** As noted in §6.2, an unconfigured `BoundaryEngine` defaults to allowing everything through — a silent false-negative, not a loud false-positive. Verify the Nexus-specific config is actually loaded before trusting a "0 violations" result.

---

## Appendix: Legacy Source Map

For reference when drafting integration prompts.

| Area | File(s) |
|---|---|
| CLI / orchestration | `pulse.py`, `nexus_audit/main.py`, `nexus_audit/__main__.py` |
| Config / capability tiers / PyPI / OSV | `nexus_audit/config.py` |
| Boundary classification, scoring, cycles, git context | `nexus_audit/audit_engine.py` |
| Bandit / Vulture / Radon scanning | `nexus_audit/scanners.py` |
| Legacy (unused) duplicate boundary/cycle logic | `nexus_audit/dependency.py` |
| Config Health (6-file-type scanner) | `nexus_audit/config_health.py` |
| Dependency Vault (risk-tiered TTL cache) | `nexus_audit/dep_cache.py` |
| Multi-key Gemini rotation | `nexus_audit/key_pool.py` |
| Shared app/import constants | `nexus_audit/models.py` |
| AI backend (model chain, JSON parsing, probing) | `nexus_audit/ai/backend.py` |
| AI prompt templates, task routing | `nexus_audit/ai/prompts.py` |
| Five-layer recommendation orchestration + Tier-1 templates | `nexus_audit/ai/recommendations.py` |
| Coupling matrix | `nexus_audit/features/coupling_map.py` |
| Fix queue + regression detection | `nexus_audit/features/fix_queue.py` |
| Fast/changed-file scanning | `nexus_audit/features/quick_check.py` |
| Score history / violation persistence | `nexus_audit/features/timeline.py` |
| `--serve` HTTP server, SSE, watch mode | `nexus_audit/features/server.py` |
| Markdown report generators (full/app/category) | `nexus_audit/report/markdown_report.py` |
| Offline vis.js asset loading | `nexus_audit/report/assets.py` |
| Dashboard SPA shell | `visuals/index.html`, `visuals/css/styles.css` |
| Dashboard state/data fetch | `visuals/js/state.js`, `visuals/js/api.js`, `visuals/js/main.js` |
| Physics graph + 3 interaction modes | `visuals/js/components/graph.js`, `visuals/js/physics.worker.js` |
| Dashboard tabs (all categories) | `visuals/js/components/tabs.js` |
| Recommendations cards UI | `visuals/js/components/recommendations.js` |
| Trends chart | `visuals/js/components/trends.js` |
| Dashboard summary cards | `visuals/js/components/dashboard.js` |
