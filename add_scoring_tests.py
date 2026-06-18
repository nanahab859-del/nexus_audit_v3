import os
from datetime import datetime

with open("tests/engines/test_scoring_engine.py", "a") as f:
    f.write("""
from core.primitives.models import ModuleEntry, Severity, Category, RuleDefinition

def test_resolve_app_fallback():
    dna = ProjectDNA(
        modules={},
        apps=["my_app"],
        physical_files=[],
        built_at=datetime.now(),
        project_root=Path("/")
    )
    
    f1 = create_finding("s", "r", "my_app/f.py", 1, 1, Severity.HIGH, Category.SECURITY, "t", "d")
    assert _resolve_app(f1, dna) == "my_app"
    
    f2 = create_finding("s", "r", "other_app/f.py", 1, 1, Severity.HIGH, Category.SECURITY, "t", "d")
    assert _resolve_app(f2, dna) == "unknown"

def test_test_file_exclusion():
    dna = ProjectDNA(
        modules={
            "app/test_foo.py": ModuleEntry("app.test_foo", Path("app/test_foo.py"), "app/test_foo.py", "app", {}, [], True, 100, "python")
        },
        apps=["app"],
        physical_files=[],
        built_at=datetime.now(),
        project_root=Path("/")
    )
    f = create_finding("s", "r", "app/test_foo.py", 1, 1, Severity.HIGH, Category.SECURITY, "t", "d")
    
    class DummyBus: pass
    scores, fleet = calculate_scores(dna, [f], set(), {}, DummyBus())
    # Should be excluded, so lines of code should be 0, penalty 0
    assert scores["app"].lines_of_code == 0
    assert sum(scores["app"].penalty_breakdown.values()) == 0

def test_security_penalties():
    dna = ProjectDNA(
        modules={
            "app/f.py": ModuleEntry("app.f", Path("app/f.py"), "app/f.py", "app", {}, [], False, 10, "python")
        },
        apps=["app"],
        physical_files=[],
        built_at=datetime.now(),
        project_root=Path("/")
    )
    # CRITICAL, MEDIUM, LOW
    f1 = create_finding("s", "r", "app/f.py", 1, 1, Severity.CRITICAL, Category.SECURITY, "t", "d")
    f2 = create_finding("s", "r", "app/f.py", 1, 1, Severity.MEDIUM, Category.SECURITY, "t", "d")
    f3 = create_finding("s", "r", "app/f.py", 1, 1, Severity.LOW, Category.SECURITY, "t", "d")
    
    class DummyBus: pass
    scores, fleet = calculate_scores(dna, [f1, f2, f3], set(), {}, DummyBus())
    # security penalties: 12 + 6 + 3 = 21
    assert scores["app"].penalty_breakdown["security"] == 21.0

def test_dead_code_and_complexity():
    dna = ProjectDNA(
        modules={
            "app/f.py": ModuleEntry("app.f", Path("app/f.py"), "app/f.py", "app", {}, [], False, 10, "python")
        },
        apps=["app"],
        physical_files=[],
        built_at=datetime.now(),
        project_root=Path("/")
    )
    
    # Dead code: title="dead code" or scanner="vulture"
    f1 = create_finding("vulture", "r", "app/f.py", 1, 1, Severity.MEDIUM, Category.MAINTAINABILITY, "Unused code", "d")
    f2 = create_finding("s", "r", "app/f.py", 1, 1, Severity.MEDIUM, Category.MAINTAINABILITY, "dead function", "d")
    
    # Complexity: scanner="radon" or title="complexity"
    radon_findings = [create_finding("radon", "r", "app/f.py", 1, 1, Severity.MEDIUM, Category.MAINTAINABILITY, "C", "d") for _ in range(25)]
    
    class DummyBus: pass
    scores, fleet = calculate_scores(dna, [f1, f2] + radon_findings, set(), {}, DummyBus())
    
    # Dead code: 3.0 * 2 = 6.0
    assert scores["app"].penalty_breakdown["dead_code"] == 6.0
    
    # Complexity: dna complexity = 0 + 0.5 = 0.5. radon = 25 * 0.5 = 12.5. Total 13.0
    # penalty = (13.0 - 10.0) * 2.0 = 6.0
    assert scores["app"].penalty_breakdown["complexity"] == 6.0
""")
