from collections import defaultdict
from core.primitives.models import ProjectDNA, Finding

def build_coupling_matrix(
    dna: ProjectDNA,
    boundary_findings: list[Finding]
) -> dict:
    """
    Build the N×N cross‑app coupling matrix.
    """
    # 1. Index findings
    findings_index = {}
    for f in boundary_findings:
        findings_index[(f.file, f.line)] = f

    # 2. Build app list
    apps = sorted([app for app in dna.apps if app != "unknown"])
    if "unknown" in dna.apps:
        apps.append("unknown")

    # 3. Initialize matrix
    n = len(apps)
    matrix = [[0] * n for _ in range(n)]

    # Precompute lookup dict for O(1) index lookups inside the loop
    app_to_idx: dict[str, int] = {app: i for i, app in enumerate(apps)}

    # 4. Collect raw data
    violation_pairs = defaultdict(list)   # (from_app, to_app) -> [details]
    allowed_pairs = defaultdict(lambda: {"count": 0, "reason": "default_allow"})
    cross_app_tracker = {}               # (i, j) -> count for bidirectional check

    for mod in dna.modules.values():
        from_app = mod.app
        from_idx = app_to_idx.get(from_app, -1)
        if from_idx == -1: continue

        for import_path, line_number in mod.imports.items():
            # Identify target app
            target_mod = dna.modules.get(import_path)
            target_app = target_mod.app if target_mod else None
            
            # If target_app is None, it's external/framework - skip per contract
            if not target_app or target_app not in app_to_idx:
                continue

            to_idx = app_to_idx[target_app]
            matrix[from_idx][to_idx] += 1
            cross_app_tracker[(from_idx, to_idx)] = cross_app_tracker.get((from_idx, to_idx), 0) + 1

            if from_app == target_app:
                continue   # internal

            # Check if this import is a violation
            finding = findings_index.get((mod.relative_path, line_number))
            if finding:
                violation_pairs[(from_app, target_app)].append({
                    "file": mod.relative_path,
                    "line": line_number,
                    "target_module": import_path,
                    "severity": finding.severity.name,
                    "rule_id": finding.rule_id or "boundary-violation"
                })
            else:
                allowed_pairs[(from_app, target_app)]["count"] += 1

    # 5. Detect bidirectional
    # A pair (from, to) is bidirectional if both (from_idx, to_idx) and (to_idx, from_idx) are in cross_app_tracker
    bidirectional_pairs = set()
    for (f_idx, t_idx) in cross_app_tracker:
        if (t_idx, f_idx) in cross_app_tracker:
            bidirectional_pairs.add(frozenset((f_idx, t_idx)))
            
    # Mark in violations
    for (from_app, to_app), details in violation_pairs.items():
        from_idx = app_to_idx.get(from_app, -1)
        to_idx = app_to_idx.get(to_app, -1)
        if from_idx == -1 or to_idx == -1:
            continue
        if frozenset((from_idx, to_idx)) in bidirectional_pairs:
            for v in details:
                v["is_bidirectional"] = True
    
    # Mark in allowed
    for (from_app, to_app), data in allowed_pairs.items():
        from_idx = app_to_idx.get(from_app, -1)
        to_idx = app_to_idx.get(to_app, -1)
        if from_idx == -1 or to_idx == -1:
            continue
        if frozenset((from_idx, to_idx)) in bidirectional_pairs:
            data["is_bidirectional"] = True

    # 6. Build output
    violations = []
    for (from_app, to_app), details in violation_pairs.items():
        is_bidir = any(d.get("is_bidirectional", False) for d in details)
        violations.append({
            "from": from_app,
            "to": to_app,
            "count": len(details),
            "is_bidirectional": is_bidir,
            "details": details
        })

    allowed = []
    for (from_app, to_app), data in allowed_pairs.items():
        if data["count"] > 0:
            allowed.append({
                "from": from_app,
                "to": to_app,
                "count": data["count"],
                "reason": data["reason"],
                "is_bidirectional": data.get("is_bidirectional", False)
            })

    two_way_count = len(bidirectional_pairs)
    total_cross = sum(matrix[i][j] for i in range(n) for j in range(n) if i != j)

    summary = {
        "total_apps": n,
        "total_cross_app_imports": total_cross,
        "violation_pairs": len(violations),
        "allowed_pairs": len(allowed),
        "two_way_pairs": two_way_count
    }

    return {
        "apps": apps,
        "matrix": matrix,
        "violations": violations,
        "allowed": allowed,
        "summary": summary
    }
