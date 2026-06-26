# Nexus Audit V3 — Storage Architecture & Competitive Research
**Prepared for:** Nexus Audit V3 team  
**Date:** June 2026  
**Scope:** Data storage patterns across 4 incumbent tools, assessment of the JSON-only approach, SQLite hybrid recommendation, and differentiation ideas.

---

## 1. How Incumbent Tools Handle Storage & Trends

### SonarQube (Enterprise / Self-Hosted)
SonarQube is the closest architectural comparison—it is also a local server. Its stack is **PostgreSQL + embedded Elasticsearch**. PostgreSQL is the system of record: every issue, metric, analysis timestamp, and quality gate result lives there. Elasticsearch sits alongside it as a queryable search index. The Compute Engine (the background analysis processor) writes issues to PostgreSQL first, then asynchronously updates the Elasticsearch index so the dashboard can do fast full-text and faceted searches.

The practical consequence for operators is steep: you need a running PostgreSQL instance (SonarQube starts with an embedded H2 but the docs tell you it is "only for evaluation"), JVM heap tuning, and Elasticsearch disk-usage monitoring (indices lock read-only at 95% disk capacity). A team member described in a community post from August 2025 that SonarQube "is more of an in-the-moment tool"—historical trend queries across 50,000 issues "don't seem like something SonarQube is really set up to do." That gap is real: trend data lives in PostgreSQL tables, but the UI only exposes coarse time-series charts, not arbitrary historical queries.

**Setup cost:** High. Provisioning takes days, not minutes.  
**Trend capability:** Limited by design—optimised for current state, not deep history.  
**Data portability:** Near-zero without a PostgreSQL dump.

---

### Semgrep (Open-Source CLI / SaaS)
Semgrep is deliberately **stateless at the CLI layer**. A scan runs, produces output, and disappears. Results can be emitted as JSON, SARIF, GitLab SAST format, JUnit XML, or plain text, directed to stdout or a file. There is no database, no index, no history. If you run `semgrep scan --json-output=findings.json`, you get a JSON file for that run only. The next run produces a new file and the old one is forgotten unless you wire up your own archival logic.

Historical trends and fix-queue management are a **paid cloud feature** (Semgrep AppSec Platform). The CLI uploads results to Semgrep's servers; the SaaS layer maintains the history and surfaces trend dashboards. Offline developers or air-gapped environments get no trend analysis at all with the open-source tool.

**Setup cost:** Zero (CLI install). Cloud history requires an account.  
**Trend capability:** None locally; full-featured in the paid SaaS tier.  
**Data portability:** Excellent—JSON/SARIF output is yours.

---

### Trivy / Grype (Container & Dependency Scanning)
Both tools separate *vulnerability reference data* from *scan output*:

- **Reference data:** Trivy maintains its own binary vulnerability database (rebuilt every 6 hours, cached locally after first download). Grype downloads and caches its vulnerability database as **SQLite archives** via Anchore's Vunnel ETL pipeline—it uses SQLite specifically because it enables fast offline lookups.
- **Scan output:** Both emit JSON, SARIF, or table to stdout/file. No scan history is stored. Each invocation is independent.

Neither tool maintains historical trends or a fix queue. They are fire-and-forget scanners designed to slot into CI pipelines where the CI system owns history (artifacts, test reports, dashboards). Notably, Grype already knows the answer to your SQLite question: it chose SQLite for its *reference* database precisely because it is zero-setup, portable, and enables structured offline queries—then deliberately kept scan *output* as flat JSON because that is all CI needs.

**Setup cost:** Minimal (single binary download).  
**Trend capability:** None—delegated entirely to the CI/CD layer.  
**Data portability:** Excellent.

---

### Snyk (Cloud-First, SaaS + Local Engine)
Snyk's default model is **cloud-first**: scan results are posted to Snyk's servers. The platform stores only file/line pointers and issue IDs after analysis—not source code—but all meaningful history and trend analysis lives in Snyk's cloud database. The CLI can run locally for speed and privacy but only becomes useful for trends and fix queues when it phones home (`--report` flag).

For air-gapped or strict data-residency environments, Snyk offers a "Local Engine"—but this requires a **Kubernetes cluster** with significant CPU and RAM. It is not something a solo developer spins up for a single project.

**Setup cost:** Zero for cloud; significant for Local Engine.  
**Trend capability:** Full in SaaS; none locally without the enterprise option.  
**Data portability:** Poor—historical data is locked in Snyk's platform.

---

## 2. Assessment of Your JSON-Only Approach

### What You Gain

**Zero friction installation.** Every tool above either requires a server (SonarQube, Snyk Local Engine), an account (Snyk SaaS, Semgrep SaaS, DeepSource), or both. Your approach requires neither. A developer runs the tool once and history starts accumulating automatically. This is the correct instinct for a developer-first tool in 2026.

**Full data sovereignty.** The audit history is plain files in a directory the developer owns. It can be inspected in any editor, committed to git, backed up with rsync, or copied to a new machine in a `cp -r`. No cloud vendor can sunset their API and take your history with them.

**Portability as a feature.** The two-file design (full payload + lightweight summary) is clever. Most tools don't bother splitting; you can already answer "what was the fleet score 30 runs ago?" by reading only the 4KB summary files without touching the multi-MB full payloads.

**Human-readable audit trails.** If a compliance auditor asks "what did the security scan find on March 14th?" you hand them a JSON file. No database dump required.

### What You Lose

**Efficient cross-run querying.** Trend queries today require Python/shell to glob the summary files, parse each one, and aggregate. For 30 runs that's fast. For 500 runs it's slower. For queries that need data from the full payload (e.g., "show me all SQLi findings that appeared in run 200 and were still present in run 250") it becomes materially slow.

**Concurrent write safety.** If two audit workers write to the same project directory simultaneously, you have no isolation guarantee. JSON files are not atomic. This is low risk for a developer tool today but matters if you add watch-mode or CI parallelism.

**Ad-hoc query flexibility.** Right now, someone who wants "show me all findings in `auth/` that are severity HIGH and were first seen more than 60 days ago" has to write Python. A database makes that a single SQL query.

### At What Scale Does JSON Become a Problem?

| Dimension | Comfortable | Starting to hurt | Clear ceiling |
|-----------|-------------|-----------------|---------------|
| Findings per run | < 5,000 | 10,000–30,000 | > 50,000 (full JSON > 50MB) |
| Historical runs | < 100 | 200–500 | > 1,000 (summary glob gets slow) |
| Concurrent writers | 1 | 2 (unsafe) | Any parallel writes |
| Full-payload size | < 5MB | 10–30MB | > 100MB (parse latency noticeable) |

For a typical Python project with a few hundred files, your current design works comfortably through the entire product lifecycle. The wall appears for monorepos (millions of lines, tens of thousands of findings) or teams running automated audits on 50+ microservices with long retention windows.

---

## 3. Recommendation: The JSON + SQLite Hybrid

**Stick with JSON as the archive format. Add SQLite as a queryable index.** This is the right architecture for a local-first developer tool and maps to what Grype itself does (SQLite for structured reference data, JSON for scan output).

### How It Works in Practice

On every audit run:
1. Write `audit_data_complete.json` and `audit_summary.json` as today (no change).
2. After writing, upsert into `~/.nexus_audit/index.db` (a single SQLite file).

The SQLite schema is thin—just the data you need for queries:

```sql
-- Runs
CREATE TABLE runs (
  run_id TEXT PRIMARY KEY,
  project_id TEXT,
  timestamp INTEGER,
  job_dir TEXT,      -- pointer back to the JSON files
  score_overall REAL,
  score_security REAL,
  score_quality REAL,
  findings_count INTEGER,
  HIGH_count INTEGER,
  CRITICAL_count INTEGER
);

-- Individual findings (for trend queries)
CREATE TABLE findings (
  fingerprint TEXT,
  run_id TEXT,
  category TEXT,
  severity TEXT,
  file_path TEXT,
  first_seen_run TEXT,
  last_seen_run TEXT,
  status TEXT  -- open / resolved / suppressed
);

CREATE INDEX idx_findings_fingerprint ON findings(fingerprint);
CREATE INDEX idx_runs_project ON runs(project_id, timestamp);
```

The full detail (DNA, coupling matrix, fix suggestions) stays in the JSON. SQLite only stores what you'd put in a `SELECT` clause.

### The Result

| Query | Without SQLite | With SQLite |
|-------|---------------|-------------|
| "Score trend last 30 runs" | Read 30 summary JSONs, parse, aggregate | `SELECT timestamp, score_overall FROM runs ORDER BY timestamp DESC LIMIT 30` |
| "New HIGH findings this week" | Diff last week's full JSON vs today's | `SELECT * FROM findings WHERE first_seen_run IN (SELECT run_id FROM runs WHERE timestamp > ?)` |
| "Which files regress most often?" | Custom Python script | `SELECT file_path, COUNT(*) FROM findings GROUP BY file_path ORDER BY COUNT(*) DESC` |
| "Full detail on finding X" | Direct (load JSON for that run) | Load JSON for that run (same as before) |

### What About Migrations?

SQLite is addable after the fact. You could ship V3.0 with JSON-only and V3.1 with the index, built by replaying the existing JSON history on first launch. The JSON files are the source of truth; SQLite is always rebuildable from them. This is a key reliability property: if the index gets corrupted, `nexus rebuild-index` regenerates it.

### Why Not PostgreSQL / Redis?

Both require a running server process. For a local-first tool targeting individual developers, that is the exact setup cost you are correctly trying to avoid. SQLite is a file, ships as a single binary embedded in your process, requires zero configuration, and handles the query volumes you will see comfortably. Grype made the same call for the same reasons.

---

## 4. How to Differentiate: Two Ideas

### Idea 1 — "Your Audit Data, Forever Portable"

The biggest pain point with SonarQube, Snyk, and DeepSource is **vendor lock-in on historical data**. When teams switch tools, they lose their trend history. As one analysis from March 2026 put it: "Most SonarQube alternatives do not support direct import of SonarQube historical data. When switching tools, teams typically start with a fresh baseline."

Nexus Audit V3 can make portability a first-class feature:

- Every audit run produces standards-compliant SARIF output alongside your JSON (SARIF is the OASIS standard that GitHub, VS Code, and GitLab all consume natively).
- Publish a documented schema for `audit_summary.json` so third-party tools can read it.
- Ship an `export` command: `nexus export --format sarif --since 90d` that replays history as a SARIF bundle. Any developer who switches to another tool takes their history with them.

The marketing angle is simple: *"We are the only code audit tool where you own your history and can leave whenever you want."* In an era where developers are increasingly sceptical of cloud lock-in, this is a genuine reason to choose you over an entrenched player.

### Idea 2 — "Structural Diff: Audit Your Audit"

Every tool shows you the *current* state of findings. Almost none help you understand *why it changed*. A developer who sees their security score drop from 87 to 71 between this commit and last week's knows the score dropped—but not whether it was one new critical finding or fifty new low-severity ones, or whether it was in a file a colleague touched or in their own PR.

Nexus Audit V3 could ship a `nexus diff <run_a> <run_b>` command that produces a **structural diff of two audit results**:

```
nexus diff job_abc job_xyz

+12 new HIGH findings (auth/login.py +4, api/upload.py +8)
-3 CRITICAL resolved (all in api/legacy.py)
Score delta: -16 (security: -22, quality: +6)
Coupling delta: auth → payments edge ADDED (regression)

Probable cause: 8 files changed in commit a3f9c2b (Alice Chen, 2h ago)
```

The JSON-first architecture makes this trivial to implement—you already have the full payload from both runs. With the SQLite index you can surface the diff instantly even across hundreds of runs. No other local-first tool does this today. It turns the audit from a compliance checkbox into a genuine development feedback loop.

---

## Summary

| Question | Answer |
|----------|--------|
| How do incumbents store data? | SonarQube: PostgreSQL + Elasticsearch (heavy). Semgrep/Trivy/Grype: flat files only, no local history. Snyk: cloud database, no meaningful local history. |
| JSON-only strengths | Zero setup, full data sovereignty, portability, human-readable. |
| JSON-only weaknesses | No efficient trend queries at scale, no concurrent-write safety, no ad-hoc SQL. |
| At what scale does JSON break? | ~500 runs for summary queries, ~50,000 findings per run for full payload size. |
| Recommended architecture | JSON as archive (no change) + SQLite as a thin queryable index, always rebuildable from JSON. |
| Differentiation angle 1 | Full data portability + SARIF export: "you own your history." |
| Differentiation angle 2 | `nexus diff` — structural audit diff that tells developers *why* their score changed, not just that it did. |
