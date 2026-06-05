from dataclasses import dataclass, field
from typing import Any
import math

from core.dna_builder import ProjectDNA
from core.models import Finding, Severity, Category
from core.boundary_engine import BoundaryEngine

@dataclass
class ScoringConfig:
    violation_default: float = 5.0
    violation_hub: float = 3.0
    security_high: float = 12.0
    security_medium: float = 6.0
    security_low: float = 3.0
    complexity_above: float = 10.0
    complexity_factor: float = 2.0
    complexity_max: float = 20.0
    dead_code_per: float = 3.0
    dead_code_max: float = 15.0
    ghost_file_per: float = 2.0
    ghost_file_max: float = 10.0
    hub_bonus: float = 10.0
    exclude_tests: bool = True

@dataclass
class AppScore:
    app: str
    score: float
    breakdown: dict[str, float]
    is_hub: bool
    finding_counts: dict[str, int]

class ScoringEngine:
    def __init__(self, raw_config: dict[str, Any] | None) -> None:
        self.raw_config = raw_config or {}
        scoring_data = self.raw_config.get("scoring", {})
        penalties = scoring_data.get("penalties", {})
        bonuses = scoring_data.get("bonuses", {})
        
        self.config = ScoringConfig(
            violation_default=float(penalties.get("violation_default", 5.0)),
            violation_hub=float(penalties.get("violation_hub", 3.0)),
            security_high=float(penalties.get("security_high", 12.0)),
            security_medium=float(penalties.get("security_medium", 6.0)),
            security_low=float(penalties.get("security_low", 3.0)),
            complexity_above=float(penalties.get("complexity_above", 10.0)),
            complexity_factor=float(penalties.get("complexity_factor", 2.0)),
            complexity_max=float(penalties.get("complexity_max", 20.0)),
            dead_code_per=float(penalties.get("dead_code_per", 3.0)),
            dead_code_max=float(penalties.get("dead_code_max", 15.0)),
            ghost_file_per=float(penalties.get("ghost_file_per", 2.0)),
            ghost_file_max=float(penalties.get("ghost_file_max", 10.0)),
            hub_bonus=float(bonuses.get("hub_app", 10.0)),
            exclude_tests=bool(scoring_data.get("exclude_tests", True))
        )
        self.boundary_engine = BoundaryEngine(raw_config)
        
    def _get_app_for_finding(self, finding: Finding, dna: ProjectDNA) -> str | None:
        """Resolve which app a finding belongs to."""
        for mod in dna.modules.values():
            if mod.relative_path == finding.file:
                return mod.app
                
        # If not found exactly, try matching by prefix
        for app in dna.apps:
            if finding.file.startswith(f"{app}/"):
                return app
                
        return None

    def calculate_scores(
        self,
        dna: ProjectDNA,
        findings: list[Finding]
    ) -> dict[str, AppScore]:
        app_scores: dict[str, AppScore] = {}
        
        # Initialize scores for all apps
        for app in dna.apps:
            is_hub = False
            if app in self.boundary_engine.apps:
                is_hub = self.boundary_engine.apps[app].hub
                
            app_scores[app] = AppScore(
                app=app,
                score=100.0,
                breakdown={
                    "violations": 0.0,
                    "security": 0.0,
                    "complexity": 0.0,
                    "dead_code": 0.0,
                    "ghost_files": 0.0,
                    "bonus": self.config.hub_bonus if is_hub else 0.0
                },
                is_hub=is_hub,
                finding_counts={
                    "violations": 0,
                    "security_high": 0,
                    "security_medium": 0,
                    "security_low": 0,
                    "dead_code": 0,
                    "ghost_files": 0
                }
            )
            
        # Distribute findings to apps
        for finding in findings:
            if self.config.exclude_tests and ("test_" in finding.file or "_test.py" in finding.file or "/tests/" in finding.file):
                continue
                
            app = self._get_app_for_finding(finding, dna)
            if app is None or app not in app_scores:
                continue
            
            app_name: str = app
            score_data = app_scores[app_name]
            
            if finding.category == Category.ARCHITECTURE and finding.title == "Direct cross-app import":
                score_data.finding_counts["violations"] += 1
            elif finding.category == Category.SECURITY:
                if finding.severity >= Severity.HIGH:
                    score_data.finding_counts["security_high"] += 1
                elif finding.severity == Severity.MEDIUM:
                    score_data.finding_counts["security_medium"] += 1
                else:
                    score_data.finding_counts["security_low"] += 1
            elif finding.title == "Ghost file" or "Ghost file" in (finding.description or ""):
                score_data.finding_counts["ghost_files"] += 1
            elif finding.category == Category.QUALITY and "dead code" in (finding.description or "").lower():
                score_data.finding_counts["dead_code"] += 1
                
        # Calculate scores
        for app, score_data in app_scores.items():
            violations = score_data.finding_counts["violations"]
            violation_penalty = violations * (self.config.violation_hub if score_data.is_hub else self.config.violation_default)
            score_data.breakdown["violations"] = -violation_penalty
            
            security_penalty = (
                score_data.finding_counts["security_high"] * self.config.security_high +
                score_data.finding_counts["security_medium"] * self.config.security_medium +
                score_data.finding_counts["security_low"] * self.config.security_low
            )
            score_data.breakdown["security"] = -security_penalty
            
            ghost_penalty = min(score_data.finding_counts["ghost_files"] * self.config.ghost_file_per, self.config.ghost_file_max)
            score_data.breakdown["ghost_files"] = -ghost_penalty
            
            dead_code_penalty = min(score_data.finding_counts["dead_code"] * self.config.dead_code_per, self.config.dead_code_max)
            score_data.breakdown["dead_code"] = -dead_code_penalty
            
            # TODO: complexity calculation
            
            total = 100.0 + sum(score_data.breakdown.values())
            score_data.score = max(0.0, min(100.0, total))
            
        # Add fleet_average
        if app_scores:
            fleet_avg = sum(s.score for s in app_scores.values()) / len(app_scores)
            app_scores["fleet_average"] = AppScore(
                app="fleet_average",
                score=fleet_avg,
                breakdown={},
                is_hub=False,
                finding_counts={}
            )
            
        return app_scores
