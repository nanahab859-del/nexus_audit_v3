# Nexus Audit Report: nexus_audit_v3
**Date**: 2026-06-02T23:17:34.031030+00:00
**Commit**: a4f0dcea3b97b1743ba63c3882aabd496c331a21 on main

## Fleet Health: 97.5/100

## Application Scores
| App | Score | Violations | Security (H/M/L) |
|-----|-------|------------|------------------|
| ai | 100.0 | 0 | 0 / 0 / 0 |
| api | 100.0 | 0 | 0 / 0 / 0 |
| auto_ignore | 91.0 | 0 | 0 / 0 / 3 |
| core | 82.0 | 0 | 0 / 0 / 6 |
| diagnostic_test | 100.0 | 0 | 0 / 0 / 0 |
| docs | 100.0 | 0 | 0 / 0 / 0 |
| fix_mypy | 100.0 | 0 | 0 / 0 / 0 |
| fix_typing | 100.0 | 0 | 0 / 0 / 0 |
| frontend | 100.0 | 0 | 0 / 0 / 0 |
| orchestrator | 100.0 | 0 | 0 / 0 / 0 |
| plugins | 100.0 | 0 | 0 / 0 / 0 |
| proper_fix | 100.0 | 0 | 0 / 0 / 0 |
| server | 100.0 | 0 | 0 / 0 / 0 |
| test_pipeline | 100.0 | 0 | 0 / 0 / 0 |
| test_run | 100.0 | 0 | 0 / 0 / 0 |
| tests | 100.0 | 0 | 0 / 0 / 0 |
| verify_fast | 82.0 | 0 | 0 / 0 / 6 |
| verify_systems | 100.0 | 0 | 0 / 0 / 0 |

## Key Findings
### R001
**MEDIUM | ARCHITECTURE**
**Location**: `ai/prompts.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `api/middleware.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `api/routes_data.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `api/routes_fixqueue.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `api/routes_report.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `api/routes_rules.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `api/routes_run.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `api/routes_stream.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `api/routes_trends.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `api/server.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `auto_ignore.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `core/__main__.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `core/atomic.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `core/boundary_engine.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `core/coupling.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `core/dep_cache.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `core/dna_builder.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `core/events.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `core/fast_check.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `core/file_discovery.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `core/fix_queue.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `core/git_context.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `core/key_pool.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `core/models.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `core/registry.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `core/reports/markdown_report.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `core/rules_engine.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `core/scoring_engine.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `core/security.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `core/source_sync.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `core/timeline.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `diagnostic_test.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `docs/frontend/js/dashboard.js:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `docs/frontend/js/main.js:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `docs/frontend/js/stream.js:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `fix_mypy.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `fix_typing.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `frontend/js/api.js:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `frontend/js/command-palette.js:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `frontend/js/dashboard.js:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `frontend/js/main.js:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `frontend/js/router.js:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `frontend/js/state.js:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `frontend/js/stream.js:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `frontend/js/utils.js:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `frontend/js/views.js:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `orchestrator.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `plugins/architecture/lizard_plugin.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `plugins/base.py:1`
**Description**: Detect files that are never imported

### R001
**MEDIUM | ARCHITECTURE**
**Location**: `plugins/dependency/safety_plugin.py:1`
**Description**: Detect files that are never imported
