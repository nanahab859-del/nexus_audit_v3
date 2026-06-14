import pytest
from pathlib import Path
from datetime import datetime, timezone
from core.engines.coupling import build_coupling_matrix
from core.primitives.models import ProjectDNA, ModuleEntry, Finding, Severity, Category

@pytest.fixture
def dna():
    def create_mod(path, app, imports):
        return ModuleEntry(
            module_path=path.replace("/", "."),
            file_path=Path(path),
            relative_path=path,
            app=app,
            imports={imp: 1 for imp in imports},
            defined_names=[],
            is_test=False,
            lines_of_code=10,
            language="python",
            parse_status="ok",
            has_wildcard_imports=False
        )
        
    return ProjectDNA(
        modules={
            "app1.modA": create_mod("app1/modA.py", "app1", ["app2.modC"]),
            "app2.modC": create_mod("app2/modC.py", "app2", []),
        },
        apps=["app1", "app2"],
        physical_files=["app1/modA.py", "app2/modC.py"],
        built_at=datetime.now(timezone.utc),
        project_root=Path("/")
    )

def test_builds_matrix(dna):
    result = build_coupling_matrix(dna, [])
    
    assert result["apps"] == ["app1", "app2"]
    # app1 -> app2 (1 import)
    assert result["matrix"][0][1] == 1
    assert result["matrix"][1][0] == 0

def test_violations_populated(dna):
    finding = Finding("1", "boundary-violation", "boundary_engine", "app1/modA.py", 1, 1, Severity.MEDIUM, Category.ARCHITECTURE, "T", "D")
    result = build_coupling_matrix(dna, [finding])
    
    assert len(result["violations"]) == 1
    assert result["violations"][0]["from"] == "app1"
    assert result["violations"][0]["to"] == "app2"

def test_allowed_populated(dna):
    result = build_coupling_matrix(dna, [])
    
    assert len(result["allowed"]) == 1
    assert result["allowed"][0]["from"] == "app1"
    assert result["allowed"][0]["to"] == "app2"

def test_bidirectional_detected(dna):
    # Make app2 import app1 too
    dna.modules["app2.modC"].imports = {"app1.modA": 1}
    result = build_coupling_matrix(dna, [])
    
    assert result["summary"]["two_way_pairs"] == 1
    assert result["allowed"][0]["is_bidirectional"] is True


def test_coupling_edge_cases(dna):
    # Add unknown app
    dna.apps.append("unknown")
    
    # Add internal import (app1 -> app1)
    dna.modules["app1.modA"].imports["app1.modB"] = 10
    
    # Add framework/external import (app1 -> some_external_lib)
    dna.modules["app1.modA"].imports["os.path"] = 15
    
    # Setup bidirectional with a violation
    # app2 imports app1
    dna.modules["app2.modC"].imports["app1.modA"] = 2
    
    # And a violation on app1 -> app2
    finding = Finding("1", "boundary-violation", "boundary_engine", "app1/modA.py", 1, 1, Severity.MEDIUM, Category.ARCHITECTURE, "T", "D")
    
    result = build_coupling_matrix(dna, [finding])
    
    assert "unknown" in result["apps"]
    
    # The violation should be marked as bidirectional
    assert result["violations"][0]["is_bidirectional"] is True

