import sqlite3
import json
import asyncio
from pathlib import Path
from typing import Dict, Any

_PRAGMAS = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA busy_timeout=5000;
"""

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    job_id TEXT PRIMARY KEY,
    timestamp TEXT,
    fleet_average REAL,
    app_scores TEXT,
    findings_count INTEGER,
    git_commit TEXT,
    git_branch TEXT
);

CREATE TABLE IF NOT EXISTS findings (
    fingerprint TEXT,
    run_id TEXT,
    rule_id TEXT,
    PRIMARY KEY (fingerprint, run_id),
    FOREIGN KEY(run_id) REFERENCES runs(job_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_findings_run_id ON findings(run_id);
"""

def _get_db_path(project_id: str) -> Path:
    return Path.home() / ".nexus_audit" / "projects" / project_id / "nexus_state.db"

async def open_index(project_id: str) -> sqlite3.Connection:
    def _open():
        db_path = _get_db_path(project_id)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.executescript(_PRAGMAS)
        conn.executescript(_SCHEMA_SQL)
        return conn
    return await asyncio.to_thread(_open)

async def upsert_run(project_id: str, summary: dict, job_dir: Path) -> None:
    def _upsert():
        db_path = _get_db_path(project_id)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False)
        conn.executescript(_PRAGMAS)
        conn.executescript(_SCHEMA_SQL)
        
        try:
            conn.execute("BEGIN TRANSACTION")
            job_id = summary.get("job_id")
            timestamp = summary.get("timestamp")
            fleet_average = summary.get("fleet_average")
            app_scores = json.dumps(summary.get("app_scores", {}))
            findings_count = summary.get("findings_count", 0)
            
            git_commit = None
            git_branch = None
            complete_path = job_dir / "audit_data_complete.json"
            if complete_path.exists():
                with open(complete_path, "r") as f:
                    try:
                        complete_data = json.load(f)
                        git_ctx = complete_data.get("metadata", {}).get("git_context") or {}
                        git_commit = git_ctx.get("commit")
                        git_branch = git_ctx.get("branch")
                    except json.JSONDecodeError:
                        pass
            
            conn.execute('''
                INSERT OR REPLACE INTO runs (job_id, timestamp, fleet_average, app_scores, findings_count, git_commit, git_branch)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (job_id, timestamp, fleet_average, app_scores, findings_count, git_commit, git_branch))
            
            findings = summary.get("findings", [])
            for f in findings:
                fingerprint = f.get("fingerprint")
                rule_id = f.get("rule_id")
                if fingerprint:
                    conn.execute('''
                        INSERT OR REPLACE INTO findings (fingerprint, run_id, rule_id)
                        VALUES (?, ?, ?)
                    ''', (fingerprint, job_id, rule_id))
            
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
    
    await asyncio.to_thread(_upsert)

async def rebuild_index(project_id: str) -> Dict[str, Any]:
    def _rebuild():
        db_path = _get_db_path(project_id)
        if db_path.exists():
            db_path.unlink()
        
        conn = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False)
        conn.executescript(_PRAGMAS)
        conn.executescript(_SCHEMA_SQL)
        
        runs_indexed = 0
        try:
            conn.execute("BEGIN TRANSACTION")
            jobs_dir = Path.home() / ".nexus_audit" / "projects" / project_id / "jobs"
            if jobs_dir.exists():
                for job_dir in jobs_dir.iterdir():
                    if not job_dir.is_dir():
                        continue
                    
                    summary_path = job_dir / "audit_summary.json"
                    if not summary_path.exists():
                        continue
                        
                    with open(summary_path, "r") as f:
                        try:
                            summary = json.load(f)
                        except json.JSONDecodeError:
                            continue
                            
                    job_id = summary.get("job_id")
                    if not job_id:
                        continue
                        
                    timestamp = summary.get("timestamp")
                    fleet_average = summary.get("fleet_average")
                    app_scores = json.dumps(summary.get("app_scores", {}))
                    findings_count = summary.get("findings_count", 0)
                    
                    git_commit = None
                    git_branch = None
                    complete_path = job_dir / "audit_data_complete.json"
                    if complete_path.exists():
                        with open(complete_path, "r") as f:
                            try:
                                complete_data = json.load(f)
                                git_ctx = complete_data.get("metadata", {}).get("git_context") or {}
                                git_commit = git_ctx.get("commit")
                                git_branch = git_ctx.get("branch")
                            except json.JSONDecodeError:
                                pass
                                
                    conn.execute('''
                        INSERT OR REPLACE INTO runs (job_id, timestamp, fleet_average, app_scores, findings_count, git_commit, git_branch)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (job_id, timestamp, fleet_average, app_scores, findings_count, git_commit, git_branch))
                    
                    findings = summary.get("findings", [])
                    for f in findings:
                        fingerprint = f.get("fingerprint")
                        rule_id = f.get("rule_id")
                        if fingerprint:
                            conn.execute('''
                                INSERT OR REPLACE INTO findings (fingerprint, run_id, rule_id)
                                VALUES (?, ?, ?)
                            ''', (fingerprint, job_id, rule_id))
                    
                    runs_indexed += 1
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
            
        return {"runs_indexed": runs_indexed}

    return await asyncio.to_thread(_rebuild)
