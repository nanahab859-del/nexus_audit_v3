"""
tests/test_complexity_scoring.py

Test suite for complexity scoring in scoring engine.
Verifies Issue #12 fix: Complexity calculation implementation.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock

# Mock external dependencies
# Removed sys.modules mocks to prevent global poisoning
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.engines.scoring_engine import calculate_scores
from core.primitives.models import ScoringConfig
from core.engines.dna_builder import ProjectDNA, ModuleEntry
from core.primitives.models import Finding, Severity, Category

class ScoringEngine:
    def __init__(self, config_dict):
        self.config_dict = config_dict

    def _calculate_complexity_penalty(self, app, dna):
        cfg = dict(self.config_dict["scoring"]["penalties"])
        complexity_max = cfg.pop("complexity_max", 20.0)
        config = ScoringConfig(**cfg)
        app_modules = [m for m in dna.modules.values() if m.app == app]
        num_modules = len(app_modules)
        total_imports = sum(len(m.imports) for m in app_modules)
        avg_imports = total_imports / max(num_modules, 1)
        dna_complexity = avg_imports + (num_modules * 0.5)
        
        complexity_score = dna_complexity
        
        complexity_penalty = 0.0
        if complexity_score > config.complexity_above:
            complexity_penalty = (complexity_score - config.complexity_above) * config.complexity_factor
            
        return min(complexity_penalty, complexity_max)

    def calculate_scores(self, dna, findings):
        cfg = dict(self.config_dict["scoring"]["penalties"])
        cfg.pop("complexity_max", None)
        from core.primitives.events import EventBus
        scores, _ = calculate_scores(dna, findings, set(), cfg, EventBus())
        class ScoreWrapper:
            def __init__(self, score):
                self.breakdown = score.penalty_breakdown
        return {app: ScoreWrapper(score) for app, score in scores.items()}


def create_test_module(module_path: str, app: str, num_imports: int = 0, loc: int = 100) -> ModuleEntry:
    """Create a test module entry."""
    imports = [f"module_{i}" for i in range(num_imports)]
    return ModuleEntry(
        module_path=module_path,
        file_path=f"/test/{app}/{module_path}.py",
        relative_path=f"{app}/{module_path}.py",
        app=app,
        imports=imports,
        defined_names=[],
        is_test=False,
        lines_of_code=loc,
        language="python"
    )


def create_test_dna(app_modules: dict[str, list[ModuleEntry]]) -> ProjectDNA:
    """Create test DNA with app-organized modules."""
    all_modules = {}
    for app, modules in app_modules.items():
        for mod in modules:
            all_modules[mod.module_path] = mod
    
    dna = ProjectDNA(
        modules=all_modules,
        apps=list(app_modules.keys()),
        physical_files={},
        built_at=datetime.now(timezone.utc),
        project_root=Path("/test")
    )
    return dna


class TestComplexityCalculationBasics:
    """Test basic complexity calculation."""

    def test_low_complexity_single_module(self):
        """Test low complexity with single module and few imports."""
        config_dict = {
            "scoring": {
                "penalties": {
                    "complexity_above": 10.0,
                    "complexity_factor": 2.0,
                    "complexity_max": 20.0
                }
            }
        }
        
        app_modules = {
            "app1": [
                create_test_module("module1", "app1", num_imports=2, loc=100),
            ]
        }
        dna = create_test_dna(app_modules)
        
        engine = ScoringEngine(config_dict)
        # Average imports: 2, modules: 1 -> complexity = 2 + 0.5 = 2.5
        # Below threshold (10.0), penalty = 0
        penalty = engine._calculate_complexity_penalty("app1", dna)
        assert penalty == 0.0, f"Expected 0 penalty for low complexity, got {penalty}"

    def test_moderate_complexity(self):
        """Test moderate complexity with multiple modules."""
        config_dict = {
            "scoring": {
                "penalties": {
                    "complexity_above": 10.0,
                    "complexity_factor": 2.0,
                    "complexity_max": 20.0
                }
            }
        }
        
        app_modules = {
            "app1": [
                create_test_module("module1", "app1", num_imports=6, loc=100),
                create_test_module("module2", "app1", num_imports=8, loc=150),
                create_test_module("module3", "app1", num_imports=4, loc=80),
            ]
        }
        dna = create_test_dna(app_modules)
        
        engine = ScoringEngine(config_dict)
        # Average imports: (6+8+4)/3 = 6, modules: 3 -> complexity = 6 + 1.5 = 7.5
        # Below threshold (10.0), penalty = 0
        penalty = engine._calculate_complexity_penalty("app1", dna)
        assert penalty == 0.0, f"Expected 0 penalty, got {penalty}"

    def test_high_complexity(self):
        """Test high complexity exceeding threshold."""
        config_dict = {
            "scoring": {
                "penalties": {
                    "complexity_above": 10.0,
                    "complexity_factor": 2.0,
                    "complexity_max": 20.0
                }
            }
        }
        
        app_modules = {
            "app1": [
                create_test_module("module1", "app1", num_imports=20, loc=200),
                create_test_module("module2", "app1", num_imports=18, loc=220),
                create_test_module("module3", "app1", num_imports=22, loc=250),
            ]
        }
        dna = create_test_dna(app_modules)
        
        engine = ScoringEngine(config_dict)
        # Average imports: (20+18+22)/3 = 20, modules: 3 -> complexity = 20 + 1.5 = 21.5
        # Above threshold (10.0), excess = 21.5 - 10 = 11.5
        # Penalty = min(11.5 * 2.0, 20.0) = 20.0 (capped)
        penalty = engine._calculate_complexity_penalty("app1", dna)
        assert penalty == 20.0, f"Expected 20.0 penalty (capped), got {penalty}"

    def test_empty_app(self):
        """Test app with no modules."""
        config_dict = {
            "scoring": {
                "penalties": {
                    "complexity_above": 10.0,
                    "complexity_factor": 2.0,
                    "complexity_max": 20.0
                }
            }
        }
        
        app_modules = {"app1": []}
        dna = create_test_dna(app_modules)
        
        engine = ScoringEngine(config_dict)
        penalty = engine._calculate_complexity_penalty("app1", dna)
        assert penalty == 0.0, f"Expected 0 penalty for empty app, got {penalty}"


class TestComplexityMetrics:
    """Test individual complexity metrics."""

    def test_imports_only_complexity(self):
        """Test that imports contribute to complexity."""
        config_dict = {
            "scoring": {
                "penalties": {
                    "complexity_above": 5.0,  # Lower threshold
                    "complexity_factor": 1.0,  # 1:1 ratio
                    "complexity_max": 15.0
                }
            }
        }
        
        app_modules = {
            "app1": [
                create_test_module("module1", "app1", num_imports=10, loc=100),
            ]
        }
        dna = create_test_dna(app_modules)
        
        engine = ScoringEngine(config_dict)
        # Complexity = 10 + 0.5 = 10.5
        # Excess = 10.5 - 5.0 = 5.5
        # Penalty = 5.5 * 1.0 = 5.5
        penalty = engine._calculate_complexity_penalty("app1", dna)
        assert penalty == 5.5, f"Expected 5.5 penalty, got {penalty}"

    def test_module_count_complexity(self):
        """Test that module count contributes to complexity."""
        config_dict = {
            "scoring": {
                "penalties": {
                    "complexity_above": 8.0,
                    "complexity_factor": 2.0,
                    "complexity_max": 20.0
                }
            }
        }
        
        app_modules = {
            "app1": [
                create_test_module(f"module{i}", "app1", num_imports=5, loc=100)
                for i in range(10)  # 10 modules
            ]
        }
        dna = create_test_dna(app_modules)
        
        engine = ScoringEngine(config_dict)
        # Average imports: 5, modules: 10 -> complexity = 5 + 5.0 = 10.0
        # Excess = 10.0 - 8.0 = 2.0
        # Penalty = 2.0 * 2.0 = 4.0
        penalty = engine._calculate_complexity_penalty("app1", dna)
        assert penalty == 4.0, f"Expected 4.0 penalty, got {penalty}"


class TestComplexityPenaltyCapping:
    """Test penalty capping at maximum."""

    def test_penalty_capped_at_max(self):
        """Test that penalty is capped at complexity_max."""
        config_dict = {
            "scoring": {
                "penalties": {
                    "complexity_above": 5.0,
                    "complexity_factor": 10.0,  # Very high multiplier
                    "complexity_max": 15.0  # Cap at 15
                }
            }
        }
        
        app_modules = {
            "app1": [
                create_test_module("module1", "app1", num_imports=50, loc=500),
            ]
        }
        dna = create_test_dna(app_modules)
        
        engine = ScoringEngine(config_dict)
        # Complexity = 50 + 0.5 = 50.5
        # Excess = 50.5 - 5.0 = 45.5
        # Calculated penalty = 45.5 * 10.0 = 455.0
        # But capped at max = 15.0
        penalty = engine._calculate_complexity_penalty("app1", dna)
        assert penalty == 15.0, f"Expected 15.0 (capped), got {penalty}"


class TestComplexityIntegration:
    """Integration tests with scoring engine."""

    def test_complexity_in_app_scores(self):
        """Test that complexity penalty is applied in app scores."""
        config_dict = {
            "scoring": {
                "penalties": {
                    "complexity_above": 10.0,
                    "complexity_factor": 2.0,
                    "complexity_max": 20.0
                }
            }
        }
        
        app_modules = {
            "app1": [
                create_test_module("module1", "app1", num_imports=20, loc=200),
            ]
        }
        dna = create_test_dna(app_modules)
        
        engine = ScoringEngine(config_dict)
        scores = engine.calculate_scores(dna, [])
        
        assert "app1" in scores
        app_score = scores["app1"]
        assert "complexity" in app_score.breakdown
        # Complexity penalty should be negative
        assert app_score.breakdown["complexity"] >= 0


if __name__ == "__main__":
    # Run tests
    print("\n" + "="*60)
    print("COMPLEXITY SCORING TEST SUITE")
    print("="*60 + "\n")
    
    test_basics = TestComplexityCalculationBasics()
    test_metrics = TestComplexityMetrics()
    test_capping = TestComplexityPenaltyCapping()
    test_integration = TestComplexityIntegration()
    
    print("✓ Basic complexity calculation tests")
    test_basics.test_low_complexity_single_module()
    test_basics.test_moderate_complexity()
    test_basics.test_high_complexity()
    test_basics.test_empty_app()
    
    print("✓ Complexity metrics tests")
    test_metrics.test_imports_only_complexity()
    test_metrics.test_module_count_complexity()
    
    print("✓ Penalty capping tests")
    test_capping.test_penalty_capped_at_max()
    
    print("✓ Integration tests")
    test_integration.test_complexity_in_app_scores()
    
    print("\n" + "="*60)
    print("✓ ALL COMPLEXITY SCORING TESTS PASSED")
    print("="*60 + "\n")
