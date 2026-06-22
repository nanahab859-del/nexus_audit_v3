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
    run_id TEXT PRIMARY KEY,
    project_id TEXT,
    timestamp INTEGER,
    job_dir TEXT,
    score_overall REAL,
    score_security REAL,
    score_quality REAL,
    findings_count INTEGER,
    HIGH_count INTEGER,
    CRITICAL_count INTEGER
);

CREATE TABLE IF NOT EXISTS findings (
    fingerprint TEXT,
    run_id TEXT,
    category TEXT,
    severity TEXT,
    file_path TEXT,
    first_seen_run TEXT,
    last_seen_run TEXT,
    status TEXT
);

CREATE INDEX IF NOT EXISTS idx_findings_fingerprint ON findings(fingerprint);
CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id, timestamp);
"""

def _get_db_path() -> Path:
    return Path.home() / ".nexus_audit" / "index.db"

async def open_index() -> sqlite3.Connection:
    def _open():
        db_path = _get_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.executescript(_PRAGMAS)
        conn.executescript(_SCHEMA_SQL)
        return conn
    return await asyncio.to_thread(_open)

async def upsert_run(project_id: str, summary: dict, job_dir: Path) -> None:
    def _upsert():
        db_path = _get_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False)
        conn.executescript(_PRAGMAS)
        conn.executescript(_SCHEMA_SQL)
        
        try:
            conn.execute("BEGIN TRANSACTION")
            run_id = summary.get("job_id")
            
            # Using timestamp as an integer proxy (Unix timestamp) or just saving string if not parsing
            # The spec says INTEGER for timestamp. Let's try to convert ISO to int, else fallback.
            ts_str = summary.get("timestamp", "")
            try:
                import datetime
                ts_int = int(datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp())
            except Exception:
                ts_int = 0
                
            score_overall = summary.get("fleet_average", 0.0)
            app_scores = summary.get("app_scores", {})
            # In V3 models, security/quality are inside app_scores or scores.
            # But the orchestrator might put fleet_average. Let's just grab what we can.
            
            findings_count = summary.get("findings_count", 0)
            
            # Calculate counts and detailed scores from complete data if available
            high_count = 0
            critical_count = 0
            score_security = 0.0
            score_quality = 0.0
            
            complete_path = job_dir / "audit_data_complete.json"
            complete_data = {}
            if complete_path.exists():
                try:
                    with open(complete_path, "r") as f:
                        complete_data = json.load(f)
                except Exception:
                    pass
            
            for f in summary.get("findings", []):
                sev = f.get("severity", "").upper()
                if sev == "CRITICAL":
                    critical_count += 1
                elif sev == "HIGH":
                    high_count += 1
                    
            # Upsert Run
            conn.execute('''
                INSERT OR REPLACE INTO runs (
                    run_id, project_id, timestamp, job_dir, score_overall, 
                    score_security, score_quality, findings_count, HIGH_count, CRITICAL_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                run_id, project_id, ts_int, str(job_dir), score_overall, 
                score_security, score_quality, findings_count, high_count, critical_count
            ))
            
            # Upsert Findings
            current_findings = set()
            for f in summary.get("findings", []):
                fingerprint = f.get("fingerprint")
                if not fingerprint:
                    continue
                    
                current_findings.add(fingerprint)
                category = f.get("category", "")
                severity = f.get("severity", "")
                file_path = f.get("file", "")
                
                # Check if finding exists
                row = conn.execute("SELECT first_seen_run FROM findings WHERE fingerprint = ?", (fingerprint,)).fetchone()
                
                if row:
                    first_seen = row[0]
                    conn.execute('''
                        UPDATE findings 
                        SET last_seen_run = ?, status = ?, run_id = ?, severity = ?, category = ?, file_path = ?
                        WHERE fingerprint = ?
                    ''', (run_id, "open", run_id, severity, category, file_path, fingerprint))
                else:
                    conn.execute('''
                        INSERT INTO findings (
                            fingerprint, run_id, category, severity, file_path, 
                            first_seen_run, last_seen_run, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        fingerprint, run_id, category, severity, file_path, 
                        run_id, run_id, "new"
                    ))
            
            # Resolve findings no longer present
            # We want to find findings that were previously seen in this project but not in this run
            # To do this safely, we find all findings whose last_seen_run is in a run belonging to this project
            # This requires joining with runs
            conn.execute('''
                UPDATE findings 
                SET status = 'resolved' 
                WHERE fingerprint NOT IN ({}) 
                AND fingerprint IN (
                    SELECT f.fingerprint FROM findings f
                    JOIN runs r ON f.last_seen_run = r.run_id
                    WHERE r.project_id = ?
                )
            '''.format(','.join('?' * len(current_findings)) if current_findings else 'NULL'),
                (*current_findings, project_id) if current_findings else (project_id,)
            )
            
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
    
    await asyncio.to_thread(_upsert)

async def rebuild_index(project_id: str = None) -> Dict[str, Any]:
    # Rebuild the global index
    def _rebuild():
        db_path = _get_db_path()
        if db_path.exists():
            db_path.unlink()
        
        conn = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False)
        conn.executescript(_PRAGMAS)
        conn.executescript(_SCHEMA_SQL)
        
        runs_indexed = 0
        try:
            conn.execute("BEGIN TRANSACTION")
            
            projects_dir = Path.home() / ".nexus_audit" / "projects"
            if projects_dir.exists():
                for p_dir in projects_dir.iterdir():
                    if not p_dir.is_dir():
                        continue
                    
                    pid = p_dir.name
                    jobs_dir = p_dir / "jobs"
                    if not jobs_dir.exists():
                        continue
                        
                    # We must process jobs chronologically for first_seen/last_seen to work correctly
                    job_dirs = sorted([d for d in jobs_dir.iterdir() if d.is_dir()], key=lambda d: d.stat().st_mtime)
                    
                    for job_dir in job_dirs:
                        summary_path = job_dir / "audit_summary.json"
                        if not summary_path.exists():
                            continue
                            
                        with open(summary_path, "r") as f:
                            try:
                                summary = json.load(f)
                            except json.JSONDecodeError:
                                continue
                                
                        run_id = summary.get("job_id")
                        if not run_id:
                            continue
                            
                        ts_str = summary.get("timestamp", "")
                        try:
                            import datetime
                            ts_int = int(datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp())
                        except Exception:
                            ts_int = 0
                            
                        score_overall = summary.get("fleet_average", 0.0)
                        findings_count = summary.get("findings_count", 0)
                        
                        high_count = 0
                        critical_count = 0
                        
                        for f_obj in summary.get("findings", []):
                            sev = f_obj.get("severity", "").upper()
                            if sev == "CRITICAL":
                                critical_count += 1
                            elif sev == "HIGH":
                                high_count += 1
                                
                        conn.execute('''
                            INSERT OR REPLACE INTO runs (
                                run_id, project_id, timestamp, job_dir, score_overall, 
                                score_security, score_quality, findings_count, HIGH_count, CRITICAL_count
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            run_id, pid, ts_int, str(job_dir), score_overall, 
                            0.0, 0.0, findings_count, high_count, critical_count
                        ))
                        
                        current_findings = set()
                        for f_obj in summary.get("findings", []):
                            fingerprint = f_obj.get("fingerprint")
                            if not fingerprint:
                                continue
                                
                            current_findings.add(fingerprint)
                            category = f_obj.get("category", "")
                            severity = f_obj.get("severity", "")
                            file_path = f_obj.get("file", "")
                            
                            row = conn.execute("SELECT first_seen_run FROM findings WHERE fingerprint = ?", (fingerprint,)).fetchone()
                            
                            if row:
                                conn.execute('''
                                    UPDATE findings 
                                    SET last_seen_run = ?, status = ?, run_id = ?, severity = ?, category = ?, file_path = ?
                                    WHERE fingerprint = ?
                                ''', (run_id, "open", run_id, severity, category, file_path, fingerprint))
                            else:
                                conn.execute('''
                                    INSERT INTO findings (
                                        fingerprint, run_id, category, severity, file_path, 
                                        first_seen_run, last_seen_run, status
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                ''', (
                                    fingerprint, run_id, category, severity, file_path, 
                                    run_id, run_id, "new"
                                ))
                        
                        # Resolve absent findings
                        conn.execute('''
                            UPDATE findings 
                            SET status = 'resolved' 
                            WHERE fingerprint NOT IN ({}) 
                            AND fingerprint IN (
                                SELECT f.fingerprint FROM findings f
                                JOIN runs r ON f.last_seen_run = r.run_id
                                WHERE r.project_id = ?
                            )
                        '''.format(','.join('?' * len(current_findings)) if current_findings else 'NULL'),
                            (*current_findings, pid) if current_findings else (pid,)
                        )
                        
                        runs_indexed += 1
                        
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
            
        return {"runs_indexed": runs_indexed}

    return await asyncio.to_thread(_rebuild)

async def get_trend(project_id: str, limit: int = 30) -> list:
    def _query():
        db_path = _get_db_path()
        if not db_path.exists():
            return []
            
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        
        cursor = conn.execute('''
            SELECT run_id, timestamp, score_overall, score_security, score_quality, 
                   findings_count, HIGH_count, CRITICAL_count
            FROM runs
            WHERE project_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (project_id, limit))
        
        return [dict(row) for row in cursor.fetchall()]
        
    return await asyncio.to_thread(_query)

async def get_fix_queue(project_id: str) -> list:
    def _query():
        db_path = _get_db_path()
        if not db_path.exists():
            return []
            
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        
        # Join findings with runs to get the run timestamp
        cursor = conn.execute('''
            SELECT f.fingerprint, f.category, f.severity, f.file_path, f.status,
                   f.first_seen_run, f.last_seen_run,
                   r_first.timestamp as first_seen_ts,
                   r_last.timestamp as last_seen_ts
            FROM findings f
            JOIN runs r_last ON f.last_seen_run = r_last.run_id
            LEFT JOIN runs r_first ON f.first_seen_run = r_first.run_id
            WHERE r_last.project_id = ?
            AND f.status IN ('open', 'new')
            ORDER BY 
                CASE f.severity 
                    WHEN 'CRITICAL' THEN 1 
                    WHEN 'HIGH' THEN 2 
                    WHEN 'MEDIUM' THEN 3 
                    WHEN 'LOW' THEN 4 
                    ELSE 5 
                END,
                r_first.timestamp ASC
        ''', (project_id,))
        
        return [dict(row) for row in cursor.fetchall()]
        
    return await asyncio.to_thread(_query)

async def diff_runs(project_id: str, base_run_id: str, head_run_id: str) -> dict:
    def _query():
        db_path = _get_db_path()
        if not db_path.exists():
            return {}
            
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        
        base_findings = conn.execute(
            "SELECT fingerprint, severity, category FROM findings WHERE run_id = ?", 
            (base_run_id,)
        ).fetchall()
        
        head_findings = conn.execute(
            "SELECT fingerprint, severity, category FROM findings WHERE run_id = ?", 
            (head_run_id,)
        ).fetchall()
        
        base_set = {f['fingerprint']: dict(f) for f in base_findings}
        head_set = {f['fingerprint']: dict(f) for f in head_findings}
        
        new_fingerprints = set(head_set.keys()) - set(base_set.keys())
        resolved_fingerprints = set(base_set.keys()) - set(head_set.keys())
        persistent_fingerprints = set(base_set.keys()) & set(head_set.keys())
        
        return {
            "new": [head_set[fp] for fp in new_fingerprints],
            "resolved": [base_set[fp] for fp in resolved_fingerprints],
            "persistent": [head_set[fp] for fp in persistent_fingerprints]
        }
        
    return await asyncio.to_thread(_query)
