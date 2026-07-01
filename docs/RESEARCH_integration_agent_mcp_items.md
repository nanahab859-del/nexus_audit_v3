# Research Note: MCP Items in Integration Agent Scope
**Written by:** Lead Code Auditor, 2026-06-30
**Audience:** Integration agent on `feature/legacy-feature-integration`
**Deposited in:** `docs/` (git-tracked, auditor's worktree). A copy of this note will also be left in `/home/yusupha/my_tools/INTEGRATION_JOURNAL.md` as a coordination message.

---

## Why this note exists

The Technical Review (`Nexus_Audit_MCP_Technical_Review.md`) and Capability Gap Specification
identified a set of gaps. During triage I mapped every issue against F-01..F-12 in your
`SPECS/FEATURE_INVENTORY.md`. Several map directly to features you are either implementing now
or will implement soon. Rather than assign those to a separate agent (which would cause two agents
to touch the same files), I am documenting them here and asking you to add them to your own
research and implementation backlog.

**What I am NOT doing:** I am not writing implementation plans for these items, and I am not
assigning them to another agent. They are yours.

**What you should do:** Read the gap evidence below. When you reach the relevant feature in your
sequence (F-02, F-05, F-06, F-07, F-09), incorporate the specific gaps described here into your
research phase before writing `WHAT.md` and council documents, following your existing procedure.

---

## Item R1 — Boundary violation not detected (maps to your F-02)

**Gap from Technical Review §5.6 and §6 (P1 HIGH):**

`audit_rules.yaml` in NexusTestBed explicitly defines:
```
boundary: users/ must not import from billing/
```

`users/auth.py` contains a direct import from `billing/payment`. This is planted issue #14.
The `rules_engine` correctly detected the circular import (planted issue #23), proving it parses
the rules file. But the boundary rule evaluation is either not implemented or not being evaluated
against the import graph.

**What the Technical Review found (§4, row #14):**
- Status: 🔴 MISSED
- Expected scanner: `rules_engine`
- No finding produced

**Proposed new MCP tools for this gap (from Technical Review §7 and Capability Gap §4.11):**
- `get_boundary_violations` — returns all open boundary rule violations for a project
- `list_boundary_rules` — returns the configured boundary rules from `audit_rules.yaml`

**Your F-02 context:** Your F-02 is "App Boundary Enforcement Configuration" — authoring the
configuration block that tells the boundary engine which cross-component import patterns are
violations. The gap above (rule not triggering) is directly connected: the boundary evaluation
engine may not be consuming the configuration correctly, or the rule evaluation step is missing.
When you move from config authoring to verifying that the engine uses the config, the test case
is planted issue #14. Confirm that `users/auth.py → billing/payment` produces a finding after
F-02 is implemented.

---

## Item R2 — Dependency CVE scanning not producing findings (maps to your F-05)

**Gap from Technical Review §9.8 and §7:**

`pip_audit` is listed as a configured scanner but produced zero output during all 8 test runs.
No dependency CVE data is appearing in findings. `cvss_score` is `null` on every finding.

**Proposed new MCP tools for this gap (from Technical Review §7, T5):**
- `scan_dependencies` — explicitly triggers dependency CVE scan and returns results
- `get_cve_report` — returns CVE findings grouped by package
- `get_cvss_scores` — returns CVSS scoring for current findings

**Your F-05 context:** F-05 is "Dependency Freshness and Risk-Tiered Cache" — it extends the
existing CVE scan with version currency checking and cache TTL management. The gap above (pip_audit
silent) is a prerequisite for F-05 to be meaningful. When you research F-05, confirm whether the
`pip_audit` silence is a binary-missing issue (Group A plan in `docs/PLAN_MCP_A_infrastructure_repairs.md`
covers scanner binary installation) or a findings-parsing issue in the `pip_audit` plugin. You may
need to wait until Group A is implemented and verify pip_audit output before beginning F-05.

---

## Item R3 — Cross-service dependency graph missing (maps to your F-06 and F-07)

**Gap from Technical Review §7, T6:**

No MCP tool currently returns a cross-service import dependency graph. A shared library
vulnerability cannot be tracked across all services that depend on it. The proposed tools are:
- `get_dependency_graph` — returns the module import graph for a project
- `list_shared_modules` — returns modules imported cross-boundary by two or more components
- `get_service_impact` — for a given module, returns all components/services that import it

**Your F-06 and F-07 context:** F-06 is "Interactive Dependency Graph Visualisation" and F-07
is "Coupling Map UI". Both consume the module import graph and coupling matrix that are already
computed during an audit run and stored in `audit_data_complete.json`. The MCP tool gap above
(no API access to the dependency graph data) is the backend prerequisite for F-06's visualisation
and for any agent that needs to query cross-service impact through the MCP. When you design the
F-06 API layer, consider whether `get_dependency_graph` and `list_shared_modules` should be
MCP tools exposed now, ahead of the UI work.

---

## Item R4 — Fix queue API surface (maps to your F-09)

**Gap from Technical Review §6, P0:**

The MCP tool `get_fix_queue` always returns `{"total":0,"queue":[]}`. The code bug causing this
is being fixed by the Group A plan (`docs/PLAN_MCP_A_infrastructure_repairs.md` Fix 2). However,
the full API surface for fix queue management (status updates, snoozing, patch endpoint) is in
your scope as F-09.

**Your F-09 context:** F-09 is "Fix Queue API and UI". It specifies:
- `GET /api/fix-queue` — returns the full queue for the current project
- `PATCH /api/fix-queue/{id}` — updates item status: `{status: open|in_progress|done|snoozed, notes}`

The underlying `FixQueue` engine (`core/engines/fix_queue.py`) already has `update_status()` and
`sync()`. What's missing is the HTTP API layer and the MCP tool wrapping it. When you reach F-09,
note that the Group A plan fixes the read side (empty queue bug) — F-09 implements the write side
(status updates) and the HTTP surface.

**Also relevant — Finding Suppression Management:** The Technical Review proposed `suppress_finding`,
`list_suppressions`, `get_suppression_reason` tools (T10 in the triage). These overlap with
F-09's status update mechanism. If F-09 implements `PATCH /api/fix-queue/{id}` with status options
including a `suppressed` state, the suppression tools are a natural extension of that. Consider
whether to bundle suppression into F-09 or treat it as a sub-feature.

---

## Summary of items handed to you

| Item | Technical Review ref | Your feature |
|---|---|---|
| Boundary violation not detected | §5.6, §6 P1, planted issue #14 | F-02 |
| `get_boundary_violations`, `list_boundary_rules` tools | §7 T11 | F-02 |
| pip_audit silent / CVE scanning | §9.8, §7 T5 | F-05 |
| `scan_dependencies`, `get_cve_report`, `get_cvss_scores` tools | §7 T5 | F-05 |
| Cross-service dependency graph | §7 T6 | F-06, F-07 |
| `get_dependency_graph`, `list_shared_modules` tools | §7 T6 | F-06 |
| Fix queue API/UI surface | §5.2, §6 P0 | F-09 |
| Finding suppression management | §7 T10 | F-09 (possibly) |

No other agent will be assigned these items. They are reserved for you.
