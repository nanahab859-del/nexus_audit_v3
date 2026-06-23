# Summary — MCP Server + SQLite Audit Index

**Branch:** `feature/mcp-server-sqlite-index`
**Worktree:** `/home/yusupha/my_tools/nexus_audit_v3-mcp-sqlite` (separate from the
main working directory — created via `git worktree`, so it never disturbs
whatever branch is checked out there)
**Base:** `main` @ `b6b4d78`
**Status:** Planning only. No code written yet.

This branch will never be merged, pushed, or marked into `main` by me.
Verification and merge are done by the repo owner once the work is reviewed.

---

## What we are trying to do

Two additions to Nexus Audit V3, both derived from specifications already
written for this project:

1. **A SQLite index alongside the existing JSON audit archive.** Today,
   every audit run writes `audit_data_complete.json` and
   `audit_summary.json` under `~/.nexus_audit/projects/<id>/jobs/<job_id>/`.
   That's the entire storage layer — there is no database. This branch adds
   a thin, queryable SQLite index (`nexus_state.db`) that's always
   rebuildable from those JSON files. The JSON archive remains the source
   of truth; SQLite is a performance/query convenience layered on top,
   never a dependency anything else relies on for correctness.

2. **A read-only MCP (Model Context Protocol) server.** This lets an
   external AI coding agent (Claude Desktop, Cursor, or similar) get
   structured, surgical context about audit findings — without that agent
   ever touching `~/.nexus_audit/` directly, and without Nexus Audit ever
   writing to the agent's codebase. The server only reads; the agent does
   all code mutation with its own tools.

## What problem this solves

- **For the SQLite index:** trend-style queries currently require
  globbing and parsing every `audit_summary.json` file in a project's
  history. That's fine at low run counts and starts to hurt past a few
  hundred runs. A SQLite index turns "read every file" into "one indexed
  query," with zero risk, since it's always regenerable from the JSON
  that remains the real record.

- **For the MCP server:** right now, the only way an AI agent can use
  Nexus Audit's findings is by being told about them manually, or by an
  agent shelling out to the CLI and parsing text output. A proper MCP
  server gives the agent typed, paginated, sandboxed tool calls instead —
  the same pattern used by every serious local-first dev tool that wants
  to be usable by an agent host.

## What is explicitly NOT in scope on this branch

The trend, diff, and fix-queue ranking logic (`get_trend`, `diff_runs`,
`get_fix_queue` on the Orchestrator, and the CLI commands that would call
them) is being implemented separately, by the repo owner, on their own
branch. This branch does not touch that work, does not duplicate it, and
does not depend on guessing what it will look like.

Three of the nine MCP tools described in the MCP Server Specification —
`get_fix_queue`, `get_trend`, `diff_runs` — call directly into that
not-yet-built Orchestrator surface. They are scaffolded (schema defined)
but **not wired** in this branch. Wiring them is a short, mechanical
follow-up once the owner's Orchestrator methods exist — not new design
work, just plumbing.

## Source documents this work is grounded in

- The MCP Server Technical Specification (protocol revision 2025-06-18,
  nine read-only tools, STDIO transport, security/sandboxing model)
- The Storage Architecture section of the Nexus Audit V3 spec (the
  JSON + SQLite hybrid design, schema, WAL pragmas, rebuild-index
  guarantee)

Both were validated earlier against this exact codebase — real file
paths, the real `audit_summary.json` schema, the real job-directory
structure (UUID job IDs, not timestamp-sortable names) — not against the
original speculative drafts.

## How this branch is meant to be used

- All code changes for this work happen only here, in this worktree.
- `main` is never checked out, merged into, or modified by me as part of
  this effort.
- Other branches in this repo (`feature/audit-trend-diff-fixqueue`,
  `feature/trend-diff-fixqueue-mcp`, `feature/f01-cycle-detection-grimp`,
  `feature/legacy-feature-integration`) are left exactly as they are —
  not deleted, not merged from, not depended on.
- See `IMPLEMENTATION_PLAN.md` in this same branch for the concrete,
  file-by-file plan.
