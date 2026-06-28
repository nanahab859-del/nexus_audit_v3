# nexus_audit_v3 — Full Working Workflow

**This document is the single source of truth for how every session
runs and how every feature gets built. Read this before doing anything
else. If something in another document contradicts this, this wins.**

---

## What This Project Is

nexus_audit_v3 is a **language-agnostic code auditing tool**. It audits
codebases written in any language — Python, JavaScript, TypeScript, Go,
and more. It is not a Python tool. It is not a Django tool. Any document,
spec, rule, or implementation that assumes a specific language or framework
is wrong and must be corrected before it is used.

---

## The Three People Working on This

| Person | Works in | Branch |
|---|---|---|
| Yusupha | `~/my_tools/nexus_audit_v3/` | `main` |
| Other developer | `~/my_tools/nexus_audit_v3-mcp-sqlite/` | `feature/mcp-server-sqlite-index` |
| Claude | `~/my_tools/nexus_audit_v3_features/` | `feature/legacy-feature-integration` |

Claude never touches Yusupha's folder. Claude never touches the other
developer's folder. All of Claude's work goes in the features worktree.

---

## Session Startup — Every Single Session, No Exceptions

Before responding to anything, run these five commands and read the output:

```
1. git -C ~/my_tools/nexus_audit_v3 worktree list
2. cat ~/my_tools/nexus_audit_v3/docs/PROJECT_STATE.md
3. cat ~/my_tools/nexus_audit_v3/docs/AUDITOR_STANDING_INSTRUCTIONS.md
4. find ~/my_tools/nexus_audit_v3_features/SPECS -name '*HANDOVER*' | sort -r | head -1
   then read that file
5. cat ~/my_tools/nexus_audit_v3_features/SPECS/ROADMAP.md
```

After reading all five, tell Yusupha in plain language:
- Which feature is currently active
- What state it is in (waiting for research / spec ready / implementing / verifying)
- What happened last session
- What to do next

Then stop and wait for direction.

---

## The File Structure

```
SPECS/                          ← all .md files live here, nothing scattered
  WORKFLOW.md                   ← this file
  ROADMAP.md                    ← feature list and status only, no detail
  SESSION_HANDOVER.md           ← updated at the end of every session
  LEGACY_FEATURE_INTEGRATION_PLAN.md  ← reference: what legacy had
  features/
    01_feature_name/
      01_WHAT.md                ← document 1
      02_RESEARCH.md            ← document 2 (written after Yusupha provides research)
      03_SPEC.md                ← document 3 (written after document 2 exists)
    02_feature_name/
      ...
  architecture/                 ← system-level docs
  CLI/                          ← CLI reference
  storage/                      ← storage docs
```

Every feature gets its own subfolder. The three documents inside it are
numbered so the sequence is always clear.

---

## How Every Feature Gets Built — The Exact Sequence

### Stage 0 — Feature is on the roadmap
The roadmap lists the feature name and status. Nothing else. No detail.
Status: `not started`

---

### Stage 1 — Write Document 1: WHAT

Claude reads the legacy tool source code and writes one document:
`SPECS/features/NN_feature_name/01_WHAT.md`

This document contains:
- What the feature does, described in plain language
- Why it matters
- What the legacy tool had (behavior only — not the code, not the approach)
- What v3 currently has or does not have
- What languages and project types this feature applies to

**Rules for this document:**
- No implementation detail
- No tool suggestions
- No library names
- No language-specific assumptions
- No "this is how we will build it"
- Just what it does and what the gap is

Status becomes: `what written — waiting for research`

---

### Stage 2 — Yusupha Provides Research

Yusupha goes and researches how to implement the feature. He decides
what to look for. He brings back whatever he found — articles, docs,
tool comparisons, benchmarks, his own notes. He pastes or uploads it.

Claude does not tell Yusupha what to research.
Claude does not do the research itself.
Claude waits.

When Yusupha provides the research, Claude reads it carefully and
writes document 2.

---

### Stage 3 — Write Document 2: RESEARCH

`SPECS/features/NN_feature_name/02_RESEARCH.md`

Claude reads everything Yusupha provided and writes a synthesis:
- What the research says
- What options exist
- Trade-offs between options
- Which option fits v3's architecture and why
- What is still unknown or needs a decision from Yusupha

This document ends with a clear recommendation and any open questions
for Yusupha to decide before implementation begins.

Status becomes: `research written — waiting for Yusupha decision`

---

### Stage 4 — Yusupha Makes Decisions

Yusupha reads document 2, answers the open questions, makes the call
on which direction to go. He tells Claude.

Claude does not proceed to document 3 until this happens.

---

### Stage 5 — Write Document 3: SPEC

`SPECS/features/NN_feature_name/03_SPEC.md`

Claude writes the full implementation specification:
- Exact files that change and why
- Exact files that do not change and why
- Pseudocode or logic description (not final code)
- Language-agnostic design — works for any supported language
- Test cases with exact names and what each asserts
- Verification checklist
- Merge conditions

Status becomes: `spec written — ready to implement`

---

### Stage 6 — Create Feature Branch and Implement

Claude creates a branch from `feature/legacy-feature-integration`:
`feature/fNN-feature-name`

All implementation work goes on that branch. No code is written without
a spec. The spec is the contract.

When implementation is done, Claude verifies against the checklist in
document 3 and runs the test suite.

Status becomes: `implemented — verifying`

---

### Stage 7 — Verify

Claude runs the tests and checks every item on the verification
checklist in document 3. If anything fails, it gets fixed on the
feature branch before merge.

Status becomes: `verified — ready to merge`

---

### Stage 8 — Merge and Clean Up

Claude merges the feature branch into `feature/legacy-feature-integration`.
Claude provides the command for Yusupha to delete the feature branch
himself. Claude updates ROADMAP.md to mark the feature done.
Claude writes the session handover.

Status becomes: `done`

---

## The Roadmap

The roadmap contains exactly this for each feature:

```
Feature N: [name]
Status: [not started / what written / waiting for research /
         research written / waiting for decision / spec written /
         implementing / verifying / done]
```

Nothing else. All detail lives in the three documents per feature.

---

## Rules That Never Change

1. **Language-agnostic always.** If an implementation only works for
   one language, it is incomplete. Every feature must work across all
   supported languages or explicitly document which languages it covers
   and why others are excluded — with a plan to add them.

2. **No code before a spec.** Document 3 must exist before any
   implementation starts.

3. **One feature at a time.** The next feature's Stage 1 does not
   start until the current feature reaches Stage 8.

4. **Legacy is what, not how.** The legacy tool shows what the feature
   should do. It does not show how to build it in v3.

5. **Yusupha provides research. Claude does not.** Claude reads what
   Yusupha brings and synthesises it. Claude never goes looking for
   tools or libraries on its own for implementation decisions.

6. **Nothing scattered.** Every .md file goes inside SPECS/. If a .md
   file exists outside SPECS/, it is in the wrong place.

7. **No assumptions.** If something is unclear, ask. Do not fill in
   gaps with assumptions. Assumptions are what caused the problems
   that made this document necessary.

8. **Read before acting.** Every session starts with the five startup
   commands. Every time Yusupha provides new information, read it
   fully before responding.

---

## WSL Execution Pattern

All commands run through Windows MCP PowerShell:

```
wsl -d Ubuntu-22.04 -- bash -c "full command here"
```

All pipes, redirects, and multi-step commands go inside the quoted
bash string. Never pipe through PowerShell directly.
For long output: redirect to /tmp/ first, then read the file.
For multi-line git commits: write to /tmp/msg.txt, then git commit -F.

Shared venv: `/home/yusupha/my_tools/nexus_audit_v3/.venv/`
Run tests: `/home/yusupha/my_tools/nexus_audit_v3/.venv/bin/python -m pytest`

---

## Session Handover Template

At the end of every session, write SESSION_HANDOVER.md with:

```
# Session Handover
Date: [date]

## What Was Done This Session
[bullet list]

## Current Feature
Feature N: [name]
Status: [status]

## Waiting For
[what Yusupha needs to provide, or "nothing — ready to continue"]

## Branch State
[one line per branch showing latest commit]

## Next Session Starts With
[exactly what to do first, no ambiguity]
```

---

## Project Instructions for Claude Desktop

(Paste this into the Claude Desktop project instructions field)

---

You are working on nexus_audit_v3, a language-agnostic code auditing
tool. It is NOT specific to Python, Django, or any language or framework.

At the start of every session, before doing anything else, run these
commands and read the output:

wsl -d Ubuntu-22.04 -- bash -c "git -C /home/yusupha/my_tools/nexus_audit_v3 worktree list"
wsl -d Ubuntu-22.04 -- bash -c "cat /home/yusupha/my_tools/nexus_audit_v3/docs/PROJECT_STATE.md"
wsl -d Ubuntu-22.04 -- bash -c "cat /home/yusupha/my_tools/nexus_audit_v3/docs/AUDITOR_STANDING_INSTRUCTIONS.md"
wsl -d Ubuntu-22.04 -- bash -c "find /home/yusupha/my_tools/nexus_audit_v3_features/SPECS -name '*HANDOVER*' | sort -r | head -1"
Read whichever file that returns.
wsl -d Ubuntu-22.04 -- bash -c "cat /home/yusupha/my_tools/nexus_audit_v3_features/SPECS/ROADMAP.md"

Then read SPECS/WORKFLOW.md in the features worktree. That document
contains the full working process. Follow it exactly.

Tell Yusupha what feature is active, what state it is in, and what
happened last session. Then stop and wait for his direction.

Never make language-specific assumptions. Never do research on behalf
of Yusupha — he provides research, you read it and synthesise it.
Never write a spec before research is provided. Never write code before
a spec exists.

---
