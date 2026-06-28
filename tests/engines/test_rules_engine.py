import pytest
from pathlib import Path
from core.engines.rules_engine import RulesEngine
from core.primitives.models import ProjectDNA, Finding
import yaml

@pytest.mark.asyncio
async def test_loads_valid_rules(tmp_path):
    rules_path = tmp_path / "audit_rules.yaml"
    rules = {
        "rules": [
            {"id": "r1", "name": "Rule 1", "type": "ghost", "severity": "HIGH", "category": "ARCHITECTURE", "languages": [], "description": "", "suggestion": ""},
            {"id": "r2", "name": "Rule 2", "type": "cycle", "severity": "CRITICAL", "category": "ARCHITECTURE", "languages": [], "description": "", "suggestion": ""}
        ]
    }
    with open(rules_path, "w") as f:
        yaml.dump(rules, f)
        
    engine = RulesEngine(rules_path)
    pass
    
@pytest.mark.asyncio
async def test_missing_file():
    engine = RulesEngine(Path("nonexistent.yaml"))
    assert engine.rule_count == 0

@pytest.mark.asyncio
async def test_malformed_yaml(tmp_path):
    rules_path = tmp_path / "bad.yaml"
    with open(rules_path, "w") as f:
        f.write("invalid: : yaml")
        
    engine = RulesEngine(rules_path)
    assert engine.rule_count == 0


from core.primitives.models import ModuleEntry, Severity, Category, RuleDefinition
from datetime import datetime

def test_properties(tmp_path):
    rules_path = tmp_path / "audit_rules.yaml"
    with open(rules_path, "w") as f:
        yaml.dump({
            "scoring_config": {"x": 1},
            "communication_config": {"y": 2},
            "app_definitions": [{"z": 3}],
            "rules": [{"id": "r1", "name": "Rule 1", "type": "ghost", "severity": "HIGH", "category": "ARCHITECTURE", "languages": [], "description": "", "suggestion": ""}]
        }, f)
    engine = RulesEngine(rules_path)
    print("RULES ENGINE VARS:", vars(engine)); assert engine.rules[0].id == "r1"
    assert engine.scoring_config == {"x": 1}
    assert engine.communication_config == {"y": 2}
    assert engine.app_definitions == [{"z": 3}]

def test_parse_severity_category():
    engine = RulesEngine(Path("nonexistent"))
    assert engine._parse_severity("CRITICAL") == Severity.CRITICAL
    assert engine._parse_severity("UNKNOWN_SEV") == Severity.MEDIUM
    assert engine._parse_category("SECURITY") == Category.SECURITY
    assert engine._parse_category("UNKNOWN_CAT") == Category.ARCHITECTURE

def test_invalid_rule_format(tmp_path, caplog):
    rules_path = tmp_path / "audit_rules.yaml"
    with open(rules_path, "w") as f:
        yaml.dump({
            "rules": [
                {"name": "No ID rule"}, # missing id
                {"id": "r1", "name": "Rule 1", "type": "ghost", "severity": "HIGH", "category": "ARCHITECTURE", "languages": [], "description": "", "suggestion": ""} # valid
            ]
        }, f)
    engine = RulesEngine(rules_path)
    assert engine.rule_count == 1
    assert "Invalid rule format" in caplog.text

@pytest.mark.asyncio
async def test_evaluate_ghost():
    engine = RulesEngine(Path("nonexistent"))
    engine._rules = [RuleDefinition(id="r1", name="Ghost", type="ghost", severity="HIGH", category="ARCHITECTURE", languages=["python"], description="d", suggestion="s")]
    engine._communication_config = {"bootstrap_files": ["manage.py"]}
    
    dna = ProjectDNA(
        modules={
            "src.app.used": ModuleEntry("src.app.used", Path("src/app/used.py"), "src/app/used.py", "app", {}, [], False, 10, "python"),
            "src.app.ghost": ModuleEntry("src.app.ghost", Path("src/app/ghost.py"), "src/app/ghost.py", "app", {}, [], False, 10, "python"),
            "src.app.wrong_lang": ModuleEntry("src.app.wrong_lang", Path("src/app/wrong_lang.js"), "src/app/wrong_lang.js", "app", {}, [], False, 10, "javascript"),
            "src.main": ModuleEntry("src.main", Path("src/main.py"), "src/main.py", "main", {"src.app.used": 1}, [], False, 10, "python")
        },
        apps=["app", "main"],
        physical_files=[
            "src/manage.py",
            "src/app/__init__.py",
            "src/app/used.py",
            "src/app/ghost.py",
            "src/app/wrong_lang.js",
            "src/main.py"
        ],
        built_at=datetime.now(),
        project_root=Path("/")
    )
    
    class DummyBus: pass
    findings = await engine.evaluate(dna, [], DummyBus())
    assert len(findings) == 2
    assert findings[0].file == "src/app/ghost.py"
    assert findings[1].file == "src/main.py"

@pytest.mark.asyncio
async def test_evaluate_delegations():
    engine = RulesEngine(Path("nonexistent"))
    engine._rules = [
        RuleDefinition(id="m1", name="", type="metric", severity="MEDIUM", category="ARCHITECTURE", languages=[], description="", suggestion=""),
        RuleDefinition(id="p1", name="", type="pattern", severity="MEDIUM", category="ARCHITECTURE", languages=[], description="", suggestion=""),
        RuleDefinition(id="re1", name="", type="regex", severity="MEDIUM", category="ARCHITECTURE", languages=[], description="", suggestion=""),
        RuleDefinition(id="c1", name="", type="cycle", severity="MEDIUM", category="ARCHITECTURE", languages=[], description="", suggestion=""),
        RuleDefinition(id="b1", name="", type="boundary", severity="MEDIUM", category="ARCHITECTURE", languages=[], description="", suggestion=""),
        RuleDefinition(id="d1", name="", type="dependency", severity="MEDIUM", category="ARCHITECTURE", languages=[], description="", suggestion=""),
        RuleDefinition(id="err1", name="", type="error_trigger", severity="MEDIUM", category="ARCHITECTURE", languages=[], description="", suggestion="")
    ]
    
    dna = ProjectDNA({}, [], [], datetime.now(), Path("/"))
    class DummyBus: pass
    
    import sys
    import types
    sys.modules['core.boundary_engine'] = types.ModuleType('core.boundary_engine')
    sys.modules['core.boundary_engine'].BoundaryEngine = type('BoundaryEngine', (), {})
    
    findings = await engine.evaluate(dna, [], DummyBus())
    assert findings == []

# ---------------------------------------------------------------------------
# Feature 01 — spec §6.2: new test cases for cycle detection
# ---------------------------------------------------------------------------

@pytest.fixture
def cycle_engine():
    engine = RulesEngine(Path("nonexistent"))
    engine._rules = [
        RuleDefinition(
            id="import-cycle",
            name="Circular Import",
            type="cycle",
            severity="HIGH",
            category="ARCHITECTURE",
            languages=["python"],
            description="",
            suggestion=""
        )
    ]
    return engine

def _create_mock_dna(modules_data):
    """Helper to build ProjectDNA from dict of {module_path: imports_list}."""
    modules = {}
    for mod_path, imports in modules_data.items():
        modules[mod_path] = ModuleEntry(
            module_path=mod_path,
            file_path=Path(f"{mod_path.replace('.', '/')}.py"),
            relative_path=f"{mod_path.replace('.', '/')}.py",
            app=mod_path.split('.')[0],
            imports={imp: 1 for imp in imports},
            defined_names=[],
            is_test=False,
            lines_of_code=10,
            language="python"
        )
    return ProjectDNA(
        modules=modules,
        apps=list({m.app for m in modules.values()}),
        physical_files=[m.relative_path for m in modules.values()],
        built_at=datetime.now(),
        project_root=Path("/")
    )

def test_cycle_detected(cycle_engine):
    dna = _create_mock_dna({
        "app.a": ["app.b"],
        "app.b": ["app.a"]
    })
    findings = cycle_engine._evaluate_cycle(cycle_engine._rules[0], dna)
    assert len(findings) == 1
    assert findings[0].rule_id == "import-cycle"
    assert "app.a → app.b → app.a" in findings[0].description or "app.b → app.a → app.b" in findings[0].description

def test_no_false_positive_on_clean_graph(cycle_engine):
    dna = _create_mock_dna({
        "app.a": ["app.b"],
        "app.b": ["app.c"],
        "app.c": []
    })
    findings = cycle_engine._evaluate_cycle(cycle_engine._rules[0], dna)
    assert len(findings) == 0

def test_deep_chain_no_recursion_error(cycle_engine):
    # A linear chain of 2000 modules: no cycles, but depth 2000.
    mods = {}
    for i in range(2000):
        mods[f"app.m{i}"] = [f"app.m{i+1}"] if i < 1999 else []
    dna = _create_mock_dna(mods)
    # Should not raise RecursionError
    findings = cycle_engine._evaluate_cycle(cycle_engine._rules[0], dna)
    assert len(findings) == 0

def test_long_cycle_no_recursion_error(cycle_engine):
    # A single cycle of 2000 modules.
    mods = {}
    for i in range(2000):
        mods[f"app.m{i}"] = [f"app.m{(i+1)%2000}"]
    dna = _create_mock_dna(mods)
    # Should not raise RecursionError
    findings = cycle_engine._evaluate_cycle(cycle_engine._rules[0], dna)
    assert len(findings) == 1
    assert findings[0].rule_id == "import-cycle"

def test_django_models_cycle_is_informational(cycle_engine):
    dna = _create_mock_dna({
        "myapp.models": ["myapp.submodels"],
        "myapp.submodels": ["myapp.models"]
    })
    findings = cycle_engine._evaluate_cycle(cycle_engine._rules[0], dna)
    assert len(findings) == 1
    assert findings[0].severity == Severity.INFO
    assert "intra-app models pattern" in findings[0].description

def test_cycle_rule_not_in_yaml_means_no_findings():
    engine = RulesEngine(Path("nonexistent"))
    engine._rules = [
        RuleDefinition(id="other", name="Other", type="ghost", severity="HIGH", category="ARCHITECTURE", languages=["python"], description="", suggestion="")
    ]
    dna = _create_mock_dna({
        "app.a": ["app.b"],
        "app.b": ["app.a"]
    })
    class DummyBus: pass
    import asyncio
    findings = asyncio.run(engine.evaluate(dna, [], DummyBus()))
    assert len(findings) == 0

