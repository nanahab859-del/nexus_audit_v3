import pytest
from pathlib import Path
from datetime import datetime, timezone
from core.engines.scoring_engine import calculate_scores, _resolve_app
from core.primitives.models import ProjectDNA, Finding, ModuleEntry, Category, Severity, Persistence, FixStatus, create_finding
from core.primitives.events import EventBus

@pytest.fixture
def dna():
    # Helper to build a simple DNA
    def create_mod(path, app, imports, lines):
        return ModuleEntry(
            module_path=path.replace("/", "."),
            file_path=Path(path),
            relative_path=path,
            app=app,
            imports={imp: 1 for imp in imports},
            defined_names=[],
            is_test=False,
            lines_of_code=lines,
            language="python",
            parse_status="ok",
            has_wildcard_imports=False
        )
    return ProjectDNA(
        modules={
            "app1.__init__": create_mod("app1/__init__.py", "app1", [], 10),
        },
        apps=["app1"],
        physical_files=["app1/__init__.py"],
        built_at=datetime.now(timezone.utc),
        project_root=Path("/")
    )

def test_perfect_score(dna):
    bus = EventBus()
    scores, avg = calculate_scores(dna, [], set(), {}, bus)
    assert scores["app1"].score == 100

def test_violation_penalty(dna):
    bus = EventBus()
    findings = [
        Finding("1", "rule1", "s1", "app1/__init__.py", 1, 1, Severity.MEDIUM, Category.ARCHITECTURE, "T", "D")
    ]
    scores, avg = calculate_scores(dna, findings, set(), {"violation_default": 5.0}, bus)
    assert scores["app1"].score == 95

def test_clamp_to_zero(dna):
    bus = EventBus()
    # Massive penalty
    findings = [
        Finding(str(i), "r", "s", "app1/__init__.py", 1, 1, Severity.CRITICAL, Category.ARCHITECTURE, "T", "D")
        for i in range(100)
    ]
    scores, avg = calculate_scores(dna, findings, set(), {"violation_default": 5.0}, bus)
    assert scores["app1"].score == 0

def test_fleet_average_weighted(tmp_path):
    # Two apps with different LOC
    dna = ProjectDNA(
        modules={
            "app1.__init__": ModuleEntry("app1.__init__", Path("app1/__init__.py"), "app1/__init__.py", "app1", {}, [], False, 100, "python", "ok", False),
            "app2.__init__": ModuleEntry("app2.__init__", Path("app2/__init__.py"), "app2/__init__.py", "app2", {}, [], False, 10, "python", "ok", False),
        },
        apps=["app1", "app2"],
        physical_files=["app1/__init__.py", "app2/__init__.py"],
        built_at=datetime.now(timezone.utc),
        project_root=Path("/")
    )
    
    # app1 score = 100, app2 score = 0
    # Average = (100 * 100 + 0 * 10) / (100 + 10) = 10000 / 110 = 90.9 -> 91
    
    findings = [
        Finding("1", "r", "s", "app2/modB.py", 1, 1, Severity.CRITICAL, Category.ARCHITECTURE, "T", "D")
        for _ in range(100) # massive penalty for app2
    ]
    
    bus = EventBus()
    scores, avg = calculate_scores(dna, findings, set(), {"violation_default": 5.0}, bus)
    
    assert scores["app1"].score == 100
    assert scores["app2"].score == 0
    assert avg == 91

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
    f1 = create_finding("vulture", "r", "app/f.py", 1, 1, Severity.MEDIUM, Category.QUALITY, "Unused code", "d")
    f2 = create_finding("s", "r", "app/f.py", 1, 1, Severity.MEDIUM, Category.QUALITY, "dead function", "d")
    
    # Complexity: scanner="radon" or title="complexity"
    radon_findings = [create_finding("radon", "r", "app/f.py", 1, 1, Severity.MEDIUM, Category.QUALITY, "C", "d") for _ in range(25)]
    
    class DummyBus: pass
    scores, fleet = calculate_scores(dna, [f1, f2] + radon_findings, set(), {}, DummyBus())
    
    # Dead code: 3.0 * 2 = 6.0
    assert scores["app"].penalty_breakdown["dead_code"] == 6.0
    
    # Complexity: dna complexity = 0 + 0.5 = 0.5. radon = 25 * 0.5 = 12.5. Total 13.0
    # penalty = (13.0 - 10.0) * 2.0 = 6.0
    assert scores["app"].penalty_breakdown["complexity"] == 6.0
