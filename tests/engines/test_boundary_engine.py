import pytest
from pathlib import Path
from core.engines.boundary_engine import BoundaryEngine, Classification
from core.primitives.models import ModuleEntry, ProjectDNA, Category, Severity
from core.primitives.events import EventBus
from datetime import datetime, timezone

def create_test_module(module_path: str, app: str, imports: list[str], is_test: bool = False) -> ModuleEntry:
    return ModuleEntry(
        module_path=module_path,
        file_path=Path(f"/{app}/{module_path.replace('.', '/')}.py"),
        relative_path=f"{module_path.replace('.', '/')}.py",
        app=app,
        imports={imp: 1 for imp in imports},
        defined_names=[],
        is_test=is_test,
        lines_of_code=10,
        language="python",
        parse_status="ok",
        has_wildcard_imports=False
    )

@pytest.fixture
def dna():
    return ProjectDNA(
        modules={
            "app1.modA": create_test_module("app1.modA", "app1", ["app1.modB", "app2.modC"]),
            "app1.modB": create_test_module("app1.modB", "app1", []),
            "app2.modC": create_test_module("app2.modC", "app2", []),
            "hub.modH": create_test_module("hub.modH", "hub", []),
        },
        apps=["app1", "app2", "hub"],
        physical_files=["app1/modA.py", "app1/modB.py", "app2/modC.py", "hub/modH.py"],
        built_at=datetime.now(timezone.utc),
        project_root=Path("/")
    )

def test_internal_import_ignored(dna):
    engine = BoundaryEngine({"default_action": "allow"})
    # app1.modA imports app1.modB (Internal)
    classification = engine.classify_import(dna.modules["app1.modA"], "app1.modB", dna, set())
    assert classification == Classification.INTERNAL

def test_hub_app_allowed(dna):
    engine = BoundaryEngine({"default_action": "deny"})
    # app1.modA imports hub.modH (Hub app)
    classification = engine.classify_import(dna.modules["app1.modA"], "hub.modH", dna, {"hub"})
    assert classification == Classification.HUB_APP

def test_default_deny_flags(dna):
    engine = BoundaryEngine({"default_action": "deny"})
    # app1.modA imports app2.modC (Violation in strict mode)
    bus = EventBus()
    findings = engine.evaluate(dna, set(), bus)
    assert len(findings) == 1
    assert findings[0].rule_id == "boundary-violation"
    assert "app1 → app2" in findings[0].title
    assert findings[0].line == 1

def test_framework_import(dna):
    engine = BoundaryEngine({"default_action": "deny"})
    classification = engine.classify_import(dna.modules["app1.modA"], "requests", dna, set())
    assert classification == Classification.FRAMEWORK

def test_bootstrap_file(dna):
    engine = BoundaryEngine({
        "default_action": "deny",
        "bootstrap_files": ["modA"]
    })
    classification = engine.classify_import(dna.modules["app1.modA"], "app2.modC", dna, set())
    assert classification == Classification.BOOTSTRAP

def test_allowed_pattern(dna):
    engine = BoundaryEngine({
        "default_action": "deny",
        "allowed_patterns": [{"import_pattern": "*.modC"}]
    })
    classification = engine.classify_import(dna.modules["app1.modA"], "app2.modC", dna, set())
    assert classification == Classification.ALLOWED

def test_test_cross_app_import(dna):
    engine = BoundaryEngine({"default_action": "deny"})
    test_mod = create_test_module("app1.test_modA", "app1", ["app2.modC"], is_test=True)
    classification = engine.classify_import(test_mod, "app2.modC", dna, set())
    assert classification == Classification.TEST_CROSS_APP

def test_default_action_allow(dna):
    engine = BoundaryEngine({"default_action": "allow"})
    classification = engine.classify_import(dna.modules["app1.modA"], "app2.modC", dna, set())
    assert classification == Classification.ALLOWED

def test_violation_severity_fallback(dna):
    engine = BoundaryEngine({
        "default_action": "deny",
        "violation_severity": "UNKNOWN_SEVERITY"
    })
    bus = EventBus()
    findings = engine.evaluate(dna, set(), bus)
    assert len(findings) == 1
    assert findings[0].severity == Severity.MEDIUM
