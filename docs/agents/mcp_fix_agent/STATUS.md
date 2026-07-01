# MCP Fix Agent — Status
**Last updated by:** (agent fills this in)
**Branch:** `feature/mcp-infrastructure-fixes`

---

## Phase A

| Fix | Status | Notes |
|---|---|---|
| A0: Install scanner binaries | ⬜ Not started | |
| A1: `_build_summary()` strips severity/category/file | ⬜ Not started | |
| A2: Sub-scores hardcoded to 0.0 | ⬜ Not started | |
| A3: `git_commit` hardcoded to `"?"` | ⬜ Not started | |
| Test suite (651+ passing) | ⬜ Not started | |
| Live audit verification | ⬜ Not started | |
| **Auditor verified** | ⬜ Pending | Lead Auditor must sign off before Phase B |

## Phase B

| Fix | Status | Notes |
|---|---|---|
| B1: `duration_ms: 0` hardcoded | ⬜ Not started | |
| B2: Ghost-file false positives | ⬜ Not started | Touch `rules_engine.py` only — NOT `default_rules.yaml` |
| B3: Duplicate project registration | ⬜ Not started | |
| B4: Ambiguous error messages | ⬜ Not started | |
| B5: Snippet column + population | ⬜ Not started | |
| Test suite (651+ passing) | ⬜ Not started | |
| Live audit verification | ⬜ Not started | |
| **Auditor verified** | ⬜ Pending | Lead Auditor must sign off before Phase C |

## Phase C

| Tool group | WHAT.md | Council | Verdict | Implemented | Auditor verified |
|---|---|---|---|---|---|
| C1: Audit Health Check | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| C2: Code Intelligence | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| C3: Secret Detection | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| C4: Git Tracking | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| C5: Sub-Score Engine | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| C6: Audit Log Access | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| C7: Finding Suppression | ⬜ Check journal first | ⬜ | ⬜ | ⬜ | ⬜ |
| C8: API Contract Validation | ⬜ Defer if no contracts | ⬜ | ⬜ | ⬜ | ⬜ |

---

## Files touched (fill in as you go — integration agent reads this)

| File | Phase | What changed |
|---|---|---|
| (none yet) | | |
