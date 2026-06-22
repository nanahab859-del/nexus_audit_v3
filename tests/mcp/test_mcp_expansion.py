import pytest
from pydantic import ValidationError
from core.mcp.schemas import ScannerToggleInput, ReportGenerationInput

def test_scanner_toggle_reasoning_validation():
    # Valid input
    valid = ScannerToggleInput(
        project_path="test-project",
        scanner_names=["bandit"],
        reasoning="This scanner is required for python security."
    )
    assert valid.scanner_names == ["bandit"]
    
    # Invalid reasoning length (< 15)
    with pytest.raises(ValidationError):
        ScannerToggleInput(
            project_path="test-project",
            scanner_names=["bandit"],
            reasoning="Too short"
        )

def test_report_generation_input_format():
    # Valid
    valid = ReportGenerationInput(
        project_path="test-project",
        output_path="report.md",
        format="md"
    )
    assert valid.format == "md"
    
    # Invalid format
    with pytest.raises(ValidationError):
        ReportGenerationInput(
            project_path="test-project",
            output_path="report.md",
            format="pdf"
        )
