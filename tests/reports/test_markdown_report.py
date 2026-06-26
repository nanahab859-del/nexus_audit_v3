"""
Tests for Markdown report generator (core/reports/markdown_report.py).

Coverage: Markdown formatting, health emoji calculation, app scoring table,
penalty breakdown, findings filtering, and edge cases.
"""
import pytest
from pathlib import Path

from core.reports.markdown_report import generate_markdown_report, _health_emoji


class TestHealthEmoji:
    """Test _health_emoji() function."""
    
    def test_health_emoji_excellent(self):
        """Test emoji for excellent health (90+)."""
        assert _health_emoji(100) == "🟢"
        assert _health_emoji(90) == "🟢"
    
    def test_health_emoji_good(self):
        """Test emoji for good health (70-89)."""
        assert _health_emoji(89) == "🟡"
        assert _health_emoji(70) == "🟡"
        assert _health_emoji(79) == "🟡"
    
    def test_health_emoji_warning(self):
        """Test emoji for warning health (50-69)."""
        assert _health_emoji(69) == "🟠"
        assert _health_emoji(50) == "🟠"
        assert _health_emoji(60) == "🟠"
    
    def test_health_emoji_critical(self):
        """Test emoji for critical health (<50)."""
        assert _health_emoji(49) == "🔴"
        assert _health_emoji(0) == "🔴"
        assert _health_emoji(1) == "🔴"


class TestMarkdownReportGeneration:
    """Test generate_markdown_report() function."""
    
    def test_generate_markdown_basic(self, sample_result_data, tmp_path):
        """Test basic markdown report generation."""
        output_path = tmp_path / "report.md"
        
        generate_markdown_report(sample_result_data, "Test Project", output_path)
        
        assert output_path.exists()
        content = output_path.read_text()
        assert "Test Project" in content
        assert "# Nexus Audit Report" in content
    
    def test_markdown_includes_header_section(self, sample_result_data, tmp_path):
        """Test markdown includes header section."""
        output_path = tmp_path / "report.md"
        
        generate_markdown_report(sample_result_data, "My Audit Project", output_path)
        
        content = output_path.read_text()
        assert "# Nexus Audit Report: My Audit Project" in content
        assert "**Date**:" in content
    
    def test_markdown_includes_git_context(self, sample_result_data, tmp_path):
        """Test markdown includes git context when available."""
        output_path = tmp_path / "report.md"
        
        generate_markdown_report(sample_result_data, "Test Project", output_path)
        
        content = output_path.read_text()
        git_ctx = sample_result_data["git_context"]
        commit = git_ctx["commit"][:8]
        branch = git_ctx["branch"]
        
        assert f"`{commit}`" in content
        assert f"`{branch}`" in content
    
    def test_markdown_fleet_health_section(self, sample_result_data, tmp_path):
        """Test markdown includes fleet health section."""
        output_path = tmp_path / "report.md"
        
        generate_markdown_report(sample_result_data, "Test Project", output_path)
        
        content = output_path.read_text()
        fleet_avg = sample_result_data["fleet_average"]
        
        assert "## Fleet Health" in content
        assert str(fleet_avg) in content
        assert "🟡" in content  # emoji for score 78
    
    def test_markdown_app_scores_table(self, sample_result_data, tmp_path):
        """Test markdown includes app scores table."""
        output_path = tmp_path / "report.md"
        
        generate_markdown_report(sample_result_data, "Test Project", output_path)
        
        content = output_path.read_text()
        
        # Check table header
        assert "| App | Score | Architecture | Security | Quality |" in content
        
        # Check apps are listed
        assert "app1" in content
        assert "app2" in content
        assert "85" in content  # app1 score
        assert "72" in content  # app2 score
    
    def test_markdown_hub_marker(self, sample_result_data, tmp_path):
        """Test markdown marks hub applications."""
        output_path = tmp_path / "report.md"
        
        generate_markdown_report(sample_result_data, "Test Project", output_path)
        
        content = output_path.read_text()
        
        # app2 is marked as hub
        assert "app2 *(hub)*" in content
        # app1 is not
        assert "app1 *(hub)*" not in content
    
    def test_markdown_penalty_breakdown_section(self, sample_result_data, tmp_path):
        """Test markdown includes penalty breakdown section."""
        output_path = tmp_path / "report.md"
        
        generate_markdown_report(sample_result_data, "Test Project", output_path)
        
        content = output_path.read_text()
        
        assert "<details>" in content
        assert "<summary>Penalty Breakdown</summary>" in content
        assert "| App | Violations | Security | Complexity | Dead Code | Ghost Files |" in content
        assert "app1" in content
        assert "app2" in content
    
    def test_markdown_key_findings_section(self, sample_result_data, tmp_path):
        """Test markdown includes key findings section."""
        output_path = tmp_path / "report.md"
        
        generate_markdown_report(sample_result_data, "Test Project", output_path)
        
        content = output_path.read_text()
        
        assert "## Key Findings" in content
        
        # Critical/High findings should be included
        assert "Type error" in content  # CRITICAL finding
        assert "Use of assert detected" in content  # HIGH finding
    
    def test_markdown_findings_filtering(self, sample_result_data, tmp_path):
        """Test markdown filters findings (CRITICAL/HIGH + ARCHITECTURE)."""
        output_path = tmp_path / "report.md"
        
        generate_markdown_report(sample_result_data, "Test Project", output_path)
        
        content = output_path.read_text()
        
        # CRITICAL should be included
        assert "Type error" in content
        
        # HIGH should be included
        assert "Use of assert detected" in content
        
        # Medium quality finding should NOT be included
        assert "Unused variable" not in content
    
    def test_markdown_finding_details(self, sample_result_data, tmp_path):
        """Test markdown includes finding details."""
        output_path = tmp_path / "report.md"
        
        generate_markdown_report(sample_result_data, "Test Project", output_path)
        
        content = output_path.read_text()
        
        # Check finding details are present
        assert "**CRITICAL | ARCHITECTURE**" in content
        assert "**Location**:" in content
        assert "handlers.py:88" in content
        assert "**Description**:" in content
        assert "**Suggestion**:" in content
    
    def test_markdown_cwe_reference(self, sample_result_data, tmp_path):
        """Test markdown includes CWE references when available."""
        output_path = tmp_path / "report.md"
        
        generate_markdown_report(sample_result_data, "Test Project", output_path)
        
        content = output_path.read_text()
        
        # First finding has CWE
        assert "**CWE**: CWE-390" in content
    
    def test_markdown_footer_with_job_id(self, sample_result_data, tmp_path):
        """Test markdown includes footer with job ID."""
        output_path = tmp_path / "report.md"
        
        generate_markdown_report(sample_result_data, "Test Project", output_path)
        
        content = output_path.read_text()
        job_id = sample_result_data["metadata"]["job_id"]
        
        assert "*Generated by Nexus Audit" in content or "Generated by Nexus Audit" in content
        assert job_id[:8] in content


class TestMarkdownReportEdgeCases:
    """Test markdown report generation edge cases."""
    
    def test_markdown_no_findings(self, sample_result_data, tmp_path):
        """Test markdown when no critical findings exist."""
        output_path = tmp_path / "report.md"
        
        # Remove findings
        sample_result_data["findings"] = [
            {
                "scanner": "linter",
                "rule_id": "L001",
                "file": "app1/file.py",
                "line": 1,
                "column": 0,
                "severity": "INFO",
                "category": "QUALITY",
                "title": "Info message",
                "description": "This is info",
                "suggestion": "No action needed",
            }
        ]
        
        generate_markdown_report(sample_result_data, "Test Project", output_path)
        
        content = output_path.read_text()
        assert "*No critical findings or architectural violations.*" in content
    
    def test_markdown_no_git_context(self, sample_result_data, tmp_path):
        """Test markdown when git_context is missing."""
        output_path = tmp_path / "report.md"
        
        # Remove git context
        sample_result_data["git_context"] = None
        
        generate_markdown_report(sample_result_data, "Test Project", output_path)
        
        content = output_path.read_text()
        
        # Should not have commit/branch lines
        assert "**Commit**:" not in content
        # But should still have the header
        assert "# Nexus Audit Report" in content
    
    def test_markdown_empty_apps_dict(self, sample_result_data, tmp_path):
        """Test markdown with no apps."""
        output_path = tmp_path / "report.md"
        
        sample_result_data["apps"] = {}
        
        generate_markdown_report(sample_result_data, "Test Project", output_path)
        
        content = output_path.read_text()
        
        assert "## Application Scores" in content
        # Table header should exist but no rows
        assert "| App | Score |" in content
    
    def test_markdown_special_characters_in_project_name(self, sample_result_data, tmp_path):
        """Test markdown with special characters in project name."""
        output_path = tmp_path / "report.md"
        
        project_name = "Test & Project [2024] **Special**"
        
        generate_markdown_report(sample_result_data, project_name, output_path)
        
        content = output_path.read_text()
        assert project_name in content
    
    def test_markdown_missing_optional_fields(self, tmp_path):
        """Test markdown with minimal result data."""
        output_path = tmp_path / "report.md"
        
        minimal_data = {
            "metadata": {"job_id": "job-1"},
            "apps": {},
            "findings": [],
            "git_context": None,
            "fleet_average": 50,
        }
        
        generate_markdown_report(minimal_data, "Project", output_path)
        
        content = output_path.read_text()
        assert "# Nexus Audit Report: Project" in content
        assert "## Fleet Health: 50/100" in content
    
    def test_markdown_many_findings(self, sample_result_data, tmp_path):
        """Test markdown with many findings (>50)."""
        output_path = tmp_path / "report.md"
        
        # Add many findings
        for i in range(60):
            sample_result_data["findings"].append({
                "scanner": "scanner",
                "rule_id": f"rule-{i}",
                "file": f"file-{i}.py",
                "line": i,
                "column": 0,
                "severity": "HIGH" if i < 30 else "MEDIUM",
                "category": "SECURITY" if i < 30 else "QUALITY",
                "title": f"Finding {i}",
                "description": f"Description {i}",
                "suggestion": "Fix it",
            })
        
        generate_markdown_report(sample_result_data, "Test Project", output_path)
        
        content = output_path.read_text()
        
        # Should be capped at 50 findings in report
        # Count "###" headers (finding titles)
        finding_count = content.count("###")
        assert finding_count <= 50


class TestMarkdownReportFormatting:
    """Test markdown formatting correctness."""
    
    def test_markdown_creates_parent_directories(self, tmp_path):
        """Test that report generation creates parent directories."""
        output_path = tmp_path / "deeply" / "nested" / "report.md"
        
        sample_data = {
            "metadata": {"job_id": "job-1"},
            "apps": {},
            "findings": [],
            "git_context": None,
            "fleet_average": 75,
        }
        
        generate_markdown_report(sample_data, "Test", output_path)
        
        assert output_path.exists()
        assert output_path.parent.exists()
    
    def test_markdown_utf8_encoding(self, sample_result_data, tmp_path):
        """Test markdown is properly encoded as UTF-8."""
        output_path = tmp_path / "report.md"
        
        generate_markdown_report(sample_result_data, "Test Project™", output_path)
        
        # Read as UTF-8
        content = output_path.read_text(encoding="utf-8")
        assert "Test Project™" in content
    
    def test_markdown_newlines_correct(self, sample_result_data, tmp_path):
        """Test markdown uses correct newline formatting."""
        output_path = tmp_path / "report.md"
        
        generate_markdown_report(sample_result_data, "Test Project", output_path)
        
        content = output_path.read_text()
        
        # Should use \n not \r\n
        assert "\r\n" not in content
        # Should have proper section spacing
        assert "\n\n" in content
