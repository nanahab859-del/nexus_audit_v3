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

def create_mock_dna(modules_dict: dict[str, list[str]]) -> ProjectDNA:
    from core.primitives.models import ModuleEntry, ProjectDNA
    from datetime import datetime
    from pathlib import Path
    
    modules = {}
    for name, imports in modules_dict.items():
        app = name.split(".")[0]
        modules[name] = ModuleEntry(
            module_path=name,
            file_path=Path(f"{name.replace('.', '/')}.py"),
            relative_path=f"{name.replace('.', '/')}.py",
            app=app,
            imports={imp: 1 for imp in imports},
            defined_names=[],
            is_test=False,
            lines_of_code=10,
            language="python",
            parse_status="ok",
            has_wildcard_imports=False,
        )
    return ProjectDNA(
        modules=modules,
        apps=list({m.app for m in modules.values()}),
        physical_files=[m.relative_path for m in modules.values()],
        built_at=datetime.now(),
        project_root=Path("/")
    )

@pytest.mark.asyncio
async def test_cycle_detected():
    engine = RulesEngine(Path("nonexistent"))
    rule = RuleDefinition(id="import-cycle", name="Cycle", type="cycle", severity="HIGH", category="ARCHITECTURE", languages=["python"], description="", suggestion="")
    dna = create_mock_dna({
        "app.a": ["app.b"],
        "app.b": ["app.c"],
        "app.c": ["app.a"],
        "app.d": []
    })
    findings = engine._evaluate_cycle(rule, dna)
    assert len(findings) == 1
    assert "app.a → app.b → app.c → app.a" in findings[0].description or "app.b → app.c → app.a → app.b" in findings[0].description or "app.c → app.a → app.b → app.c" in findings[0].description

@pytest.mark.asyncio
async def test_no_false_positive_on_clean_graph():
    engine = RulesEngine(Path("nonexistent"))
    rule = RuleDefinition(id="import-cycle", name="Cycle", type="cycle", severity="HIGH", category="ARCHITECTURE", languages=["python"], description="", suggestion="")
    dna = create_mock_dna({
        "app.a": ["app.b"],
        "app.b": ["app.c"],
        "app.c": []
    })
    findings = engine._evaluate_cycle(rule, dna)
    assert len(findings) == 0

@pytest.mark.asyncio
async def test_deep_chain_no_recursion_error():
    engine = RulesEngine(Path("nonexistent"))
    rule = RuleDefinition(id="import-cycle", name="Cycle", type="cycle", severity="HIGH", category="ARCHITECTURE", languages=["python"], description="", suggestion="")
    
    modules = {f"app.m{i}": [f"app.m{i+1}"] for i in range(2000)}
    modules["app.m2000"] = []
    
    dna = create_mock_dna(modules)
    findings = engine._evaluate_cycle(rule, dna)
    assert len(findings) == 0

@pytest.mark.asyncio
async def test_long_cycle_no_recursion_error():
    engine = RulesEngine(Path("nonexistent"))
    rule = RuleDefinition(id="import-cycle", name="Cycle", type="cycle", severity="HIGH", category="ARCHITECTURE", languages=["python"], description="", suggestion="")
    
    modules = {f"app.m{i}": [f"app.m{i+1}"] for i in range(2000)}
    modules["app.m2000"] = ["app.m0"]
    
    dna = create_mock_dna(modules)
    findings = engine._evaluate_cycle(rule, dna)
    assert len(findings) == 1

@pytest.mark.asyncio
async def test_django_models_cycle_is_informational():
    engine = RulesEngine(Path("nonexistent"))
    rule = RuleDefinition(id="import-cycle", name="Cycle", type="cycle", severity="HIGH", category="ARCHITECTURE", languages=["python"], description="", suggestion="")
    dna = create_mock_dna({
        "my_app.models.a": ["my_app.models.b"],
        "my_app.models.b": ["my_app.models.a"]
    })
    findings = engine._evaluate_cycle(rule, dna)
    assert len(findings) == 1
    assert findings[0].severity == Severity.INFO
    assert "informational" in findings[0].description

@pytest.mark.asyncio
async def test_cycle_rule_not_in_yaml_means_no_findings():
    engine = RulesEngine(Path("nonexistent"))
    engine._rules = [
        RuleDefinition(id="ghost", name="Ghost", type="ghost", severity="HIGH", category="ARCHITECTURE", languages=["python"], description="", suggestion="")
    ]
    dna = create_mock_dna({
        "app.a": ["app.b"],
        "app.b": ["app.a"]
    })
    class DummyBus: pass
    findings = await engine.evaluate(dna, [], DummyBus())
    assert len(findings) == 0 # no ghost findings because file is imported, and no cycle finding because no cycle rule
