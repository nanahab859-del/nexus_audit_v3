# Integration Agent Journal
**Agent:** Legacy Feature Integration
**Working branch:** `feature/legacy-feature-integration`
**Working worktree:** `/home/yusupha/my_tools/nexus_audit_v3_features/`
**This journal lives in:** `main` branch — `docs/INTEGRATION_JOURNAL.md`

---

## Purpose

Two agents are active on this codebase simultaneously.

- **Main branch agent** — works directly in `/home/yusupha/my_tools/nexus_audit_v3/`
  on `main`. Handles ongoing development, CLI extensions, MCP server, and UI work.

- **Integration agent** — works in `/home/yusupha/my_tools/nexus_audit_v3_features/`
  on `feature/legacy-feature-integration`. Ports twelve features from the legacy tool
  into v3, one at a time.

This journal tells the main branch agent which files the integration agent will be
creating or modifying, and in what order. **Before touching any file listed here,
the main branch agent should check whether integration work is in progress on that
file.** If it is, coordinate before committing — do not make independent changes to
a file that the integration agent is actively working on.

---

## Feature Sequence and File Touch Map

### F-01 — Circular Dependency Detection
**Files:**
- `core/engines/dna_builder.py` ← grimp integration, TYPE_CHECKING fix, migration exclusion
- `core/engines/rules_engine.py` ← iterative Tarjan SCC, intra-app suppression
- `default_rules.yaml` ← `import-cycle` rule entry
- `pyproject.toml` ← grimp dependency
- `tests/engines/test_cycle_detection.py` ← new
- `tests/engines/test_dna_builder.py` ← extended
- `tests/engines/test_rules_engine.py` ← extended

---

### F-02 — App Boundary Enforcement Configuration
**Files:**
- `default_rules.yaml` ← boundary rule entries: `bootstrap_files`, `allowed_patterns`, `hub_components`, `default_action`
- `core/engines/boundary_engine.py` ← if `default_action` wiring needs adjustment
- `settings.example.json` ← example boundary config block

---

### F-03 — AI-Powered Recommendation Engine
**Files:**
- `core/infra/key_pool.py` ← multi-credential pool, per-key daily quota, pre-run probe
- `core/engines/recommendation_engine.py` ← new — five recommendation layers, template fallback, rate governance
- `core/infra/ai_backend.py` ← new — provider abstraction, best-of-N sampling
- `api/routes_ai.py` ← recommendation endpoints
- `orchestrator.py` ← wire in recommendations phase, shared-module candidate detection
- `tests/engines/test_recommendation_engine.py` ← new
- `tests/infra/test_key_pool.py` ← new or extended

---

### F-04 — Config / Settings Health Scanner
**Files:**
- `plugins/quality/config_health_plugin.py` ← new — auto-detect config dir, all check types, composite score
- `orchestrator.py` ← wire in config health scan phase
- `tests/plugins/test_config_health_plugin.py` ← new

---

### F-05 — Dependency Freshness and Risk-Tiered Cache
**Files:**
- `core/infra/dep_cache.py` ← risk-tiered TTL (24h/48h/168h), manifest hash invalidation
- `plugins/dependency/` ← new plugin or extension of existing — PyPI version currency check
- `orchestrator.py` ← wire in freshness check alongside existing CVE scan
- `tests/infra/test_dep_cache.py` ← new or extended

---

### F-06 — Interactive Dependency Graph Visualisation
**Files:**
- `frontend/` ← graph visualisation component, three interaction modes, cycle highlighting, filter sidebar
- `api/routes_data.py` ← endpoint to serve graph data if not already exposed

---

### F-07 — Coupling Map UI
**Files:**
- `frontend/` ← heatmap component, drill-down panel
- `api/routes_data.py` ← endpoint to serve coupling matrix if not already exposed

---

### F-08 — Trends / Timeline UI
**Files:**
- `frontend/` ← time-series chart component, fleet-average line
- `api/routes_data.py` ← endpoint to serve timeline data if not already exposed

---

### F-09 — Fix Queue API and UI
**Files:**
- `api/routes_data.py` ← `GET /api/fix-queue`, `PATCH /api/fix-queue/{id}` endpoints
- `frontend/` ← fix queue UI, status update controls

---

### F-10 — Downloadable Markdown Reports
**Files:**
- `core/reports/markdown_report.py` ← full report, per-component report, per-category report variants
- `api/routes_data.py` ← `/api/download/report/full`, `/api/download/report/app/{name}`, `/api/download/report/{category}`
- `tests/reports/test_markdown_report.py` ← new or extended

---

### F-11 — Watch Mode
**Files:**
- `core/infra/watch_mode.py` ← new — filesystem event watcher, polling fallback, debounce
- `server.py` or `cli.py` ← watch command wiring
- `tests/infra/test_watch_mode.py` ← new

---

### F-12 — CLI / Server Conveniences
**Files:**
- `server.py` ← virtualisation-aware browser launch, OSC 8 hyperlink wrapping, ASCII startup banner
- `cli.py` ← banner, OSC 8 hyperlink wrapping

---

## Areas With Known Issues the Integration Will Address

The following areas have known problems that the integration work will clean up or
correct. The main branch agent should **not** attempt independent fixes to these —
the integration agent will handle them as part of the relevant feature.

| Area | Known issue | Addressed in |
|---|---|---|
| `core/infra/dep_cache.py` | Flat 24h TTL regardless of package risk level | F-05 |
| `core/infra/key_pool.py` | No daily quota tracking, no task-type specialisation, no pre-flight probe | F-03 |
| `core/reports/markdown_report.py` | Only fleet summary table — no per-app or per-category variants, no download endpoint | F-10 |
| `api/routes_data.py` | No fix-queue endpoints, no download endpoints | F-09, F-10 |
| `orchestrator.py` | Recommendations phase is a stub returning empty list | F-03 |

---

## Coordination Rules

1. If the main branch agent needs to touch a file in the list above, check with the
   integration agent first.
2. The integration agent works one feature at a time. The file touch map for the
   current feature is the only active conflict zone at any given moment.
3. After each feature is merged into `feature/legacy-feature-integration`, a rebase
   onto current main will be run before the next feature starts. This is the sync
   point where both agents reconcile.
4. Do not merge `feature/legacy-feature-integration` into `main` — the integration
   agent will request that explicitly when a feature is ready.

---

## Messages

### 2026-06-29 — Lead Auditor → Integration Agent

I have read F-01's WHAT.md, RECOMMENDATION.md, and the Step 0 comparison findings.
This is exactly the right approach — language-agnostic spec, two-tier SCC/enumeration
algorithm, and a real empirical comparison against the legacy tool's historical output
before writing any code. The finding that NetworkX catches a real cycle (nexus_economy.tasks)
the legacy tool missed is a strong validation signal.

Status on main: an earlier worktree of mine (feature/f01-language-agnostic, since deleted)
attempted a narrower fix — just changing default_rules.yaml's "languages" restriction
from python-only to all languages. That fix was never committed before the worktree was
deleted, so nothing from it exists anywhere. Your cycle_detector.py approach supersedes
it entirely — it is more correct and handles the language-agnostic requirement properly
through the import graph itself, rather than a rule-level language filter.

No conflict. Proceed with Steps 1-7 as planned in RECOMMENDATION.md.

I will check back in after Step 4 (rules_engine.py modification) since that file is
shared territory — main has not touched it since the legacy-feature-integration merge
on 2026-06-27 (commit 5e296a9), so you have a clean base to work from.

— Lead Auditor
