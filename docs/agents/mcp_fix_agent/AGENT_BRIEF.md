# MCP Fix Agent — Brief
**Agent type:** Implementation agent
**Branch:** `feature/mcp-infrastructure-fixes`
**Worktree:** `/home/yusupha/my_tools/nexus_audit_v3_mcp_fix/`
**Assigned by:** Lead Auditor, 2026-06-30
**Reports to:** Lead Auditor — all completed phases verified by the auditor before merge

---

## What you are

You are an **implementation agent**. You do not design solutions or make architectural
decisions — those are already made and documented in the phase plans in this folder.
You read the plan, implement it exactly, run the tests, and stop. The Lead Auditor
reads the files you changed and verifies before anything merges to `main`.

---

## What you own

Everything in this folder is yours. The three phase plans are your complete workstream.

| Plan | Contents | Status |
|---|---|---|
| `PHASE_A.md` | Scanner binary installation + 4 code fixes (P0/P1) | Ready — implement first |
| `PHASE_B.md` | Data quality fixes (P1/P2) | Ready — implement after Phase A |
| `PHASE_C.md` | New MCP tool groups | Research required first — see Phase C |
| `STATUS.md` | Track what you've done | Update as you complete items |

---

## Your worktree and branch

You work exclusively in `/home/yusupha/my_tools/nexus_audit_v3_mcp_fix/` on
branch `feature/mcp-infrastructure-fixes`. Never touch:
- `/home/yusupha/my_tools/nexus_audit_v3/` — the auditor's worktree on `main`
- `/home/yusupha/my_tools/nexus_audit_v3_features/` — the integration agent's worktree

---

## Files you must NOT touch (active integration agent territory)

The integration agent is on `feature/legacy-feature-integration` working on F-02 and
will later work on F-03 through F-12. **Any conflict between your work and theirs is your
fault if you touch these files without checking first:**

| File | Reason |
|---|---|
| `default_rules.yaml` | Integration agent actively modifying for F-02 boundary rules |
| `core/engines/boundary_engine.py` | Integration agent F-02 scope |
| `settings.example.json` | Integration agent F-02 scope |
| `core/infra/dep_cache.py` | Integration agent F-05 scope |
| `core/infra/key_pool.py` | Integration agent F-03 scope |
| `core/reports/markdown_report.py` | Integration agent F-10 scope |
| `frontend/` | Integration agent F-06/F-07/F-08/F-09 scope |

**Special note on `orchestrator.py`:** Your Phase A touches this file. The integration
agent will also touch it in F-03 (not yet started). This is not currently a conflict —
you go first. But when you commit your orchestrator changes, note them clearly in
`STATUS.md` so the integration agent can rebase without surprises.

---

## Procedure

### Phase A and Phase B — no research needed
Plans are complete with exact file paths, line references, and code. Implement
directly. After each phase:
1. Run `pytest tests/ -q` — all 651+ tests must pass
2. Update `STATUS.md` with what you changed
3. Commit to `feature/mcp-infrastructure-fixes`
4. **Do not open a PR or merge yourself** — the auditor verifies first

### Phase C — research required
Phase C is new MCP tool groups. You must follow the same research procedure
the integration agent uses for each feature:
1. Write a `WHAT.md` in this folder describing what the tool does and why
2. Use the LLM council skill (see `Skills/llm-council.md` in the Obsidian vault
   `nexus_audit_v3`) to get multiple expert perspectives before implementing
3. Write a council verdict document
4. Only then implement
Do this one tool group at a time, in the priority order listed in `PHASE_C.md`.
Do not implement all tool groups at once.

---

## Coordination

The shared coordination file is `/home/yusupha/my_tools/INTEGRATION_JOURNAL.md`
(outside git — a plain file on disk, accessible from any worktree). Check it
before touching any file that appears in the integration agent's file touch map.
If you need to leave a message for the integration agent or the auditor, append
to the `## Messages` section at the bottom. Do not rewrite or delete existing
messages.
