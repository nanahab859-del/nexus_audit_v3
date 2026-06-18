import os
from datetime import datetime

with open("tests/engines/test_rules_engine.py", "a") as f:
    f.write("""
from core.primitives.models import ModuleEntry, Severity, Category, RuleDefinition
from datetime import datetime

def test_properties(tmp_path):
    rules_path = tmp_path / "audit_rules.yaml"
    with open(rules_path, "w") as f:
        yaml.dump({
            "scoring_config": {"x": 1},
            "communication_config": {"y": 2},
            "app_definitions": [{"z": 3}],
            "rules": [{"id": "r1", "type": "ghost"}]
        }, f)
    engine = RulesEngine(rules_path)
    assert engine.rules[0].id == "r1"
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
                {"id": "r1", "type": "ghost"} # valid
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
            "src/app/used.py": ModuleEntry("src.app.used", Path("src/app/used.py"), "src/app/used.py", "app", {}, [], False, 10, "python"),
            "src/app/ghost.py": ModuleEntry("src.app.ghost", Path("src/app/ghost.py"), "src/app/ghost.py", "app", {}, [], False, 10, "python"),
            "src/app/wrong_lang.js": ModuleEntry("src.app.wrong_lang", Path("src/app/wrong_lang.js"), "src/app/wrong_lang.js", "app", {}, [], False, 10, "javascript"),
            "src/main.py": ModuleEntry("src.main", Path("src/main.py"), "src/main.py", "main", {"src.app.used": 1}, [], False, 10, "python")
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
    assert len(findings) == 1
    assert findings[0].file == "src/app/ghost.py"

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
    
    findings = await engine.evaluate(dna, [], DummyBus())
    assert findings == []
""")
