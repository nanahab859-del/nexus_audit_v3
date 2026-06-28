# Session Handover — Nexus Audit V3, MCP Server + SQLite Index

Paste this entire document as the first message in a new session. It
replaces the need to read the prior conversation.

---

## 1. What This Project Is

Nexus Audit V3: a local-first code audit tool. Runs scans, tracks score
history, manages a fix queue, and exposes an MCP server so an external AI
agent (Claude Desktop, Cursor) can query audit findings directly.

**Repository:** `/home/yusupha/my_tools/nexus_audit_v3` (WSL Ubuntu-22.04,
accessed from Windows via `\\wsl.localhost\Ubuntu-22.04\home\yusupha\...`)

**You need PC access to do anything here** — filesystem access to read/
write files on this machine, and shell access (PowerShell → `wsl -d
Ubuntu-22.04 -- bash -lc "..."`) for git and test commands. Confirm both
are connected before doing anything else. If either drops mid-session
(it has happened repeatedly — multi-minute timeouts with no result), wait
and retry once; if it persists, tell the user rather than guessing at
state.

## 2. The Rules — Non-Negotiable, Established Over a Long Prior Session

1. **`main` is never touched.** Never checked out, never merged into,
   never committed to. The project owner reviews and merges everything
   themselves, when they're satisfied — not before, not by you.
2. **Other branches and worktrees are never touched, merged from, or
   deleted.** Several exist for other work the owner is doing themselves
   (`feature/trend-diff-fixqueue-mcp` is their own, separate work on
   audit trend/diff/fix-queue features — explicitly **not** your scope).
   There's also `feature/f01-cycle-detection-grimp` in its own worktree —
   also not yours.
3. **Nothing gets deleted, ever — archive instead.** Documents that are
   superseded get a status banner added at the top explaining what
   changed and pointing to the current version. The original content
   stays, in full, below the banner.
4. **Verify against real files before trusting any report, handover
   document, or status claim — including this one.** This rule exists
   because it caught real, consequential mistakes multiple times:
   reports describing things as "not implemented" when they were, a
   strategy document making a factually wrong claim about Pydantic, an
   architecture doc claiming global SQLite when the original spec
   explicitly argued for per-project. Read the actual file. Don't assume
   a doc is current just because nothing says otherwise.
5. **Check git sync at every checkpoint.** `git status`, `git log
   --oneline`, compare against what you expect. More than once this
   session, branches moved or files moved underneath an in-progress task
   because the owner was working in a parallel window on the same
   checkout. Catch it, don't silently work around it or absorb it into
   your own commits.
6. **Plan before writing code. Don't write code, run tests, or commit
   anything without an explicit go-ahead** ("do that," "continue," "go
   ahead" — not silence, not "tell me what you think"). The owner has
   pushed back hard, multiple times, when action got ahead of agreement.
   When in doubt, lay out the plan and stop.
7. **Commits are scoped and explained.** Use targeted `git add <file>`,
   not `git add -A`, unless you've checked `git status` first and know
   exactly what's in the working tree. Write commit messages that explain
   *why*, not just *what* — the next reader (possibly a future session
   exactly like this one) needs the reasoning, not just a diff.

## 3. Where Things Actually Stand

**Active branch:** `feature/mcp-server-sqlite-index`
**Worktree:** `/home/yusupha/my_tools/nexus_audit_v3-mcp-sqlite` (separate
directory from the main checkout — created via `git worktree add` so work
here never disturbs whatever the owner has checked out in the primary
working directory)
**Last commit made by this work, confirmed directly:** `d3f5f2f` —
"docs: consolidate MCP specs into one document, fix interrupted file
move." The owner may have committed more after this in their own
parallel session — **check `git log --oneline -10` before doing anything
else.**

**Documentation structure** (the owner reorganized this mid-session —
confirm it still looks like this before assuming):
```
SPCES/
├── SUMMARY.md
├── MPC/
│   ├── MCP_SPECIFICATION.md        ← THE current spec. Read this first.
│   ├── MCP_SPECIFICATION_V2.md     (superseded, banner added)
│   ├── nexus_audit_v3_mcp_specification.md   (original, banner added)
│   ├── Nexus Audit v3 MCP Expansion.md       (superseded, banner added)
│   ├── mcp_capability_expansion_game_report.md (superseded, banner added)
│   ├── mcp_vs_cli_capabilities.md            (banner added)
│   ├── mcp_usage_guide.md                    (banner added)
│   └── nexus_audit_v3_cli_extension.md
├── STORAGE/
│   ├── nexus_audit_v3_storage_research.md
│   ├── nexus_audit_v3_specification.html
│   └── handover_report.md          (banner added — was stale)
└── implementation/
    └── IMPLEMENTATION_PLAN.md      (original Phase 1/2 plan — both
                                       phases below are done now)
```

**What's actually implemented in code (verified directly, not assumed):**
- SQLite index (`core/infra/audit_index.py`) — but built as a **global**
  `~/.nexus_audit/index.db`, not per-project. This contradicts the
  storage spec's own Decision Log, which explicitly argued for
  per-project for portability reasons. Never resolved. Tracked, not
  fixed. Also has two real bugs sitting in it, both confirmed by reading
  the code: `score_security`/`score_quality` are hardcoded to `0.0` on
  every insert, and the `findings` table stores one row per fingerprint
  (mutated in place each run), so it cannot correctly represent a
  fingerprint's state at any run except the most recent one — this
  makes its own `diff_runs`/`get_trend`/`get_fix_queue` functions
  unreliable for anything but the latest run. **These functions are also
  dead code** — `core/mcp/` never imports `audit_index` at all; the MCP
  tools call `Orchestrator.get_trend`/`diff_runs`/`get_fix_queue`
  directly instead (confirmed via `grep`). Don't assume code reaching for
  "the SQLite trend functions" means `audit_index.py` — check which one
  is actually being called.
- MCP server (`core/mcp/`) — 15 tools, registered and confirmed working
  via a live test session through Claude Desktop. Full registry and
  current per-tool behavior is in `MCP_SPECIFICATION.md`, Sections 4–5.
  Do not re-derive this from the original 9-tool spec — that document is
  superseded for tool count and the read-only framing.
- Five of those 15 tools write configuration (`enable_scanners`,
  `disable_scanners`, `set_scanner_config`, `set_project_config`,
  `generate_audit_report`) — added deliberately, after a real
  architecture disagreement, now resolved. See Section 4 below.

**What's specified but NOT yet implemented in code:**
- The direction-gating mechanism (`MCP_SPECIFICATION.md`, Section 5) —
  classifying every config-write tool call as tightening (apply
  immediately) or loosening (write to a pending-approval queue, require
  human approval via new CLI commands before it takes effect). **This is
  the most important next piece of actual code work.** Right now, all
  five Group 4 tools still apply immediately regardless of direction —
  the spec describes the target state, not the current one.
- `pending_changes.json`, `mcp:pending`, `mcp:approve`, `mcp:reject` —
  none of this exists in code yet.
- The `config_patch` allowlist for `set_project_config` — currently
  accepts any key with no restriction; the spec says this needs closing.

## 4. The Architecture Decision, Briefly

Two prior documents disagreed: one said the MCP server must be strictly
read-only (Confused Deputy risk — an agent tricked into a harmful action
through a tool with more permission than it should have directly), the
other argued for letting the agent write its own scanner/project config
(it understands a specific codebase's boundaries better than a static
config file can, and config mutation isn't Remote Code Execution).

Resolution, now written in `MCP_SPECIFICATION.md`: keep the write
capability — the argument for it is real — but every config action has a
direction relative to audit strictness, and only the *tightening*
direction gets to apply without a human. The *loosening* direction
(disabling a scanner, lowering strictness, raising a findings threshold)
queues for explicit human approval. This was arrived at after testing the
finished write-capable tools against a real project and finding that none
of the agent's stated reasons for distrusting the tool were about wanting
more config control — they were all about the *read* side being
unreliable (see Section 5 below). That test result is the actual evidence
behind the decision, not just architectural taste.

## 5. Known Bugs — Confirmed, Explicitly Deferred Until Now

These were found via a live MCP test session, not code reading, and were
deliberately left unfixed while the architecture question above got
settled. The architecture question is now settled. **These are the
natural next thing to work on**, but confirm with the owner before
starting — don't assume "the spec is done" automatically means "go fix
these now" without checking in first, per Rule 6.

- `security`/`quality` sub-scores hardcoded to `0.0` on every run
- `run_project_audit` completing in `duration_ms: 0` — unclear if a real
  scan is happening at all
- `get_fix_queue` returns empty despite confirmed open findings
- Finding `snippet` fields always `null`
- `git_commit` always `"?"` in trend/summary output
- The same project registered seven times under different UUIDs

## 6. Suggested Next Steps, in Order

1. Verify current git/file state matches Section 3 above. If it doesn't,
   stop and figure out why before proceeding — don't paper over it.
2. Confirm with the owner which of Section 3's "not yet implemented"
   items or Section 5's bugs to tackle first. Don't assume.
3. Whichever is chosen: plan it out loud first (per Rule 6), get explicit
   confirmation, then implement on this same branch, with tests, with a
   git sync check before committing.
4. Once the direction-gating mechanism is actually built (not just
   specified), re-run the same kind of live MCP test session that
   produced Section 5's findings, and see whether the agent's own stated
   confidence changes. That's the real test of whether any of this
   mattered — not assuming it from the design alone.
