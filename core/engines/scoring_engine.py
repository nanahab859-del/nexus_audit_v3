from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Dict, Set, Tuple
from core.primitives.models import ProjectDNA, Finding, AppScore, ScoringConfig, Severity, Category
from core.primitives.events import EventBus

def _resolve_app(finding: Finding, dna: ProjectDNA) -> str:
    # If finding.file exists in dna.modules, use that module's app.
    for mod in dna.modules.values():
        if mod.relative_path == finding.file:
            return mod.app
            
    # Fallback: matching the first path segment against dna.apps
    path_parts = finding.file.split("/")
    if path_parts and path_parts[0] in dna.apps:
        return path_parts[0]
        
    return "unknown"

def calculate_scores(
    dna: ProjectDNA,
    all_findings: List[Finding],
    hub_apps: Set[str],
    scoring_config: dict,
    bus: EventBus
) -> Tuple[Dict[str, AppScore], int]:
    
    config = ScoringConfig(**scoring_config)
    
    # 1. Group DNA by app
    app_loc: Dict[str, int] = {app: 0 for app in dna.apps + ["unknown"]}
    app_modules: Dict[str, List[str]] = {app: [] for app in app_loc}
    
    for mod_path, mod in dna.modules.items():
        if config.exclude_tests and mod.is_test:
            continue
        app = mod.app
        if app not in app_loc: app = "unknown"
        app_loc[app] += mod.lines_of_code
        app_modules[app].append(mod_path)
    
    # 2. Group findings by app
    app_findings: Dict[str, List[Finding]] = {app: [] for app in app_loc}
    for f in all_findings:
        # If test exclusion, skip test file findings
        if config.exclude_tests:
            mod = next((m for m in dna.modules.values() if m.relative_path == f.file), None)
            if mod and mod.is_test:
                continue
                
        app = _resolve_app(f, dna)
        if app not in app_findings: app = "unknown"
        app_findings[app].append(f)
    
    # 3. Calculate scores per app
    scores_dict: Dict[str, AppScore] = {}
    
    for app in app_loc:
        findings = app_findings[app]
        is_hub = app in hub_apps
        
        # Penalties
        violation_penalty = 0.0
        security_penalty = 0.0
        complexity_penalty = 0.0
        dead_code_penalty = 0.0
        ghost_file_penalty = 0.0
        finding_counts: Dict[str, int] = {}
        
        for f in findings:
            finding_counts[f.category.value] = finding_counts.get(f.category.value, 0) + 1
            
            # Violation (Architecture)
            if f.category == Category.ARCHITECTURE:
                multiplier = config.violation_hub if is_hub else config.violation_default
                violation_penalty += multiplier
                
            # Security
            if f.category == Category.SECURITY:
                if f.severity in [Severity.CRITICAL, Severity.HIGH]:
                    security_penalty += config.security_high
                elif f.severity == Severity.MEDIUM:
                    security_penalty += config.security_medium
                else:
                    security_penalty += config.security_low
            
            # Dead code
            if "vulture" in f.scanner.lower() or "dead" in f.title.lower():
                dead_code_penalty += config.dead_code_per
        
        # Complexity (heuristic + radon)
        # Note: dna heuristic is per app
        num_modules = len(app_modules[app])
        total_imports = sum(len(dna.modules[m].imports) for m in app_modules[app])
        avg_imports = total_imports / max(num_modules, 1)
        dna_complexity = avg_imports + (num_modules * 0.5)
        
        complexity_score = dna_complexity
        # Add radon findings
        for f in findings:
            if "radon" in f.scanner.lower() or "complexity" in f.title.lower():
                complexity_score += 0.5
        
        if complexity_score > config.complexity_above:
            complexity_penalty = (complexity_score - config.complexity_above) * config.complexity_factor
            
        # Ghost files
        ghost_files = 0
        for mod_path in app_modules[app]:
            mod = dna.modules[mod_path]
            # Ghost: ok status, zero imports, zero imported-by
            if mod.parse_status == "ok" and len(mod.imports) == 0:
                # Need to check imported_by (this would need the graph)
                # For now assume ghost logic is handled or placeholder
                pass
        ghost_file_penalty = ghost_files * config.ghost_file_per
        
        raw_score = 100 - (violation_penalty + security_penalty + complexity_penalty + dead_code_penalty + ghost_file_penalty)
        score = max(0, min(100, int(round(raw_score))))
        
        scores_dict[app] = AppScore(
            app=app,
            score=score,
            is_hub=is_hub,
            lines_of_code=app_loc[app],
            finding_counts=finding_counts,
            penalty_breakdown={
                "violation": violation_penalty,
                "security": security_penalty,
                "complexity": complexity_penalty,
                "dead_code": dead_code_penalty,
                "ghost_file": ghost_file_penalty
            }
        )
        
    # 4. Fleet average (exclude "unknown")
    total_weighted_score = 0.0
    total_loc = 0
    
    for app, score_obj in scores_dict.items():
        if app == "unknown":
            continue
        total_weighted_score += score_obj.score * score_obj.lines_of_code
        total_loc += score_obj.lines_of_code
        
    fleet_average = int(round(total_weighted_score / max(total_loc, 1)))
    
    return scores_dict, fleet_average
