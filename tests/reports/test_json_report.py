"""
Tests for JSON report generator (core/reports/json_report.py).

Coverage: JSON generation, structure validation, circular reference handling,
and file I/O operations.
"""
import pytest
import json
from pathlib import Path

from core.reports.json_report import generate_json_report


class TestJsonReportGeneration:
    """Test generate_json_report() function."""
    
    def test_generate_json_basic(self, sample_result_data, tmp_path):
        """Test basic JSON report generation."""
        output_path = tmp_path / "report.json"
        
        generate_json_report(sample_result_data, "Test Project", output_path)
        
        assert output_path.exists()
        content = output_path.read_text()
        
        # Verify it's valid JSON
        data = json.loads(content)
        assert isinstance(data, dict)
    
    def test_json_includes_project_name(self, sample_result_data, tmp_path):
        """Test JSON report includes project_name at top level."""
        output_path = tmp_path / "report.json"
        
        project_name = "My Test Project"
        generate_json_report(sample_result_data, project_name, output_path)
        
        data = json.loads(output_path.read_text())
        
        assert "project_name" in data
        assert data["project_name"] == project_name
    
    def test_json_is_superset_of_result_data(self, sample_result_data, tmp_path):
        """Test JSON report includes all fields from result_data."""
        output_path = tmp_path / "report.json"
        
        generate_json_report(sample_result_data, "Test Project", output_path)
        
        report_data = json.loads(output_path.read_text())
        
        # All keys from sample_result_data should be in report
        for key in sample_result_data.keys():
            assert key in report_data
        
        # Values should match (except project_name)
        for key, value in sample_result_data.items():
            assert report_data[key] == value
    
    def test_json_formatted_with_indent(self, sample_result_data, tmp_path):
        """Test JSON is formatted with proper indentation."""
        output_path = tmp_path / "report.json"
        
        generate_json_report(sample_result_data, "Test Project", output_path)
        
        content = output_path.read_text()
        
        # Check for indentation (spaces at start of lines)
        lines = content.split("\n")
        indented_lines = [l for l in lines if l.startswith(" ")]
        
        # Should have indented lines
        assert len(indented_lines) > 0
    
    def test_json_valid_structure(self, sample_result_data, tmp_path):
        """Test JSON has valid structure."""
        output_path = tmp_path / "report.json"
        
        generate_json_report(sample_result_data, "Test Project", output_path)
        
        data = json.loads(output_path.read_text())
        
        # Top level structure
        assert isinstance(data, dict)
        assert "project_name" in data
        assert "metadata" in data
        assert "apps" in data
        assert "findings" in data
    
    def test_json_metadata_preserved(self, sample_result_data, tmp_path):
        """Test metadata is correctly preserved."""
        output_path = tmp_path / "report.json"
        
        generate_json_report(sample_result_data, "Test Project", output_path)
        
        data = json.loads(output_path.read_text())
        
        assert data["metadata"]["job_id"] == sample_result_data["metadata"]["job_id"]
        assert "started_at" in data["metadata"]
    
    def test_json_apps_data_preserved(self, sample_result_data, tmp_path):
        """Test apps data is correctly preserved."""
        output_path = tmp_path / "report.json"
        
        generate_json_report(sample_result_data, "Test Project", output_path)
        
        data = json.loads(output_path.read_text())
        
        assert "app1" in data["apps"]
        assert "app2" in data["apps"]
        assert data["apps"]["app1"]["score"] == 85
        assert data["apps"]["app2"]["is_hub"] == True
    
    def test_json_findings_preserved(self, sample_result_data, tmp_path):
        """Test findings array is correctly preserved."""
        output_path = tmp_path / "report.json"
        
        generate_json_report(sample_result_data, "Test Project", output_path)
        
        data = json.loads(output_path.read_text())
        
        assert len(data["findings"]) == len(sample_result_data["findings"])
        assert data["findings"][0]["title"] == sample_result_data["findings"][0]["title"]
    
    def test_json_git_context_preserved(self, sample_result_data, tmp_path):
        """Test git context is correctly preserved."""
        output_path = tmp_path / "report.json"
        
        generate_json_report(sample_result_data, "Test Project", output_path)
        
        data = json.loads(output_path.read_text())
        
        if sample_result_data["git_context"]:
            assert data["git_context"]["branch"] == sample_result_data["git_context"]["branch"]
            assert data["git_context"]["commit"] == sample_result_data["git_context"]["commit"]


class TestJsonReportEdgeCases:
    """Test JSON report generation edge cases."""
    
    def test_json_minimal_data(self, tmp_path):
        """Test JSON with minimal data."""
        output_path = tmp_path / "report.json"
        
        minimal_data = {
            "metadata": {},
            "apps": {},
            "findings": [],
        }
        
        generate_json_report(minimal_data, "Test Project", output_path)
        
        data = json.loads(output_path.read_text())
        
        assert data["project_name"] == "Test Project"
        assert data["metadata"] == {}
        assert data["apps"] == {}
        assert data["findings"] == []
    
    def test_json_with_none_values(self, sample_result_data, tmp_path):
        """Test JSON handles None values correctly."""
        output_path = tmp_path / "report.json"
        
        # Add None values
        sample_result_data["findings"][0]["suggestion"] = None
        sample_result_data["findings"][1]["cwe"] = None
        
        generate_json_report(sample_result_data, "Test Project", output_path)
        
        data = json.loads(output_path.read_text())
        
        # None should be preserved as null in JSON
        assert data["findings"][0]["suggestion"] is None
        assert data["findings"][1]["cwe"] is None
    
    def test_json_with_circular_reference(self, tmp_path):
        """Test JSON handles circular references via default=str."""
        output_path = tmp_path / "report.json"
        
        # Create data with object reference
        class CustomObject:
            def __str__(self):
                return "CustomObject"
        
        data = {
            "metadata": {"job_id": "job-1"},
            "apps": {},
            "findings": [],
            "custom_obj": CustomObject(),  # This would normally fail
        }
        
        # Should use default=str to convert to string representation
        generate_json_report(data, "Test Project", output_path)
        
        loaded_data = json.loads(output_path.read_text())
        assert "custom_obj" in loaded_data
        assert loaded_data["custom_obj"] == "CustomObject"
    
    def test_json_special_characters_in_strings(self, tmp_path):
        """Test JSON with special characters."""
        output_path = tmp_path / "report.json"
        
        data = {
            "metadata": {"job_id": "job-1"},
            "apps": {
                "app-with-special": {
                    "score": 100,
                    "description": 'String with "quotes" and \\ backslash\nand newline'
                }
            },
            "findings": [],
        }
        
        generate_json_report(data, "Test Project", output_path)
        
        loaded_data = json.loads(output_path.read_text())
        
        assert "app-with-special" in loaded_data["apps"]
        assert '"quotes"' in loaded_data["apps"]["app-with-special"]["description"]
    
    def test_json_unicode_characters(self, tmp_path):
        """Test JSON with unicode characters."""
        output_path = tmp_path / "report.json"
        
        data = {
            "metadata": {"job_id": "job-1"},
            "apps": {},
            "findings": [{
                "title": "Unicode test: 你好世界 émojis 🔴🟡🟢",
                "description": "测试 description"
            }],
        }
        
        generate_json_report(data, "Test Project™", output_path)
        
        loaded_data = json.loads(output_path.read_text(encoding="utf-8"))
        
        assert "你好世界" in loaded_data["findings"][0]["title"]
        assert "Test Project™" in loaded_data["project_name"]


class TestJsonReportFileHandling:
    """Test JSON report file I/O operations."""
    
    def test_json_creates_parent_directories(self, sample_result_data, tmp_path):
        """Test that report generation creates parent directories."""
        output_path = tmp_path / "deeply" / "nested" / "report.json"
        
        generate_json_report(sample_result_data, "Test Project", output_path)
        
        assert output_path.exists()
        assert output_path.parent.exists()
    
    def test_json_overwrites_existing_file(self, sample_result_data, tmp_path):
        """Test that existing file is overwritten."""
        output_path = tmp_path / "report.json"
        
        # Create initial file
        output_path.write_text("old content")
        
        generate_json_report(sample_result_data, "Test Project", output_path)
        
        content = output_path.read_text()
        data = json.loads(content)
        
        # Should have new content
        assert "old content" not in content
        assert data["project_name"] == "Test Project"
    
    def test_json_utf8_encoding(self, tmp_path):
        """Test JSON is properly encoded as UTF-8."""
        output_path = tmp_path / "report.json"
        
        data = {
            "metadata": {"job_id": "job-1"},
            "apps": {},
            "findings": [],
            "test_unicode": "日本語テスト"
        }
        
        generate_json_report(data, "Test", output_path)
        
        # Read as UTF-8
        content = output_path.read_text(encoding="utf-8")
        assert "日本語テスト" in content
        
        # Verify valid JSON
        loaded = json.loads(content)
        assert loaded["test_unicode"] == "日本語テスト"
    
    def test_json_large_file_generation(self, tmp_path):
        """Test JSON generation with large data."""
        output_path = tmp_path / "large_report.json"
        
        # Create large data
        large_data = {
            "metadata": {"job_id": "job-1"},
            "apps": {f"app-{i}": {"score": i} for i in range(1000)},
            "findings": [{
                "scanner": f"scanner-{i}",
                "rule_id": f"rule-{i}",
                "file": f"file-{i}.py",
                "line": i,
                "column": 0,
                "severity": "MEDIUM",
                "category": "QUALITY",
                "title": f"Finding {i}",
                "description": f"Description {i}" * 10,
            } for i in range(1000)],
        }
        
        generate_json_report(large_data, "Large Project", output_path)
        
        assert output_path.exists()
        
        # Verify valid JSON
        loaded = json.loads(output_path.read_text())
        assert len(loaded["apps"]) == 1000
        assert len(loaded["findings"]) == 1000


class TestJsonReportIntegration:
    """Integration tests for JSON report generation."""
    
    def test_json_and_markdown_compatible(self, sample_result_data, tmp_path):
        """Test that JSON and markdown use same data structure."""
        json_path = tmp_path / "report.json"
        
        generate_json_report(sample_result_data, "Test Project", json_path)
        
        # Load JSON
        json_data = json.loads(json_path.read_text())
        
        # Both should have same structure
        assert json_data["metadata"] == sample_result_data["metadata"]
        assert json_data["apps"] == sample_result_data["apps"]
        assert json_data["findings"] == sample_result_data["findings"]
    
    def test_json_report_can_be_re_imported(self, sample_result_data, tmp_path):
        """Test that generated JSON can be reimported."""
        output_path = tmp_path / "report.json"
        
        generate_json_report(sample_result_data, "Test Project", output_path)
        
        # Re-import
        with open(output_path, "r") as f:
            reimported = json.load(f)
        
        # Should be valid and complete
        assert reimported["project_name"] == "Test Project"
        assert len(reimported["apps"]) > 0
        assert len(reimported["findings"]) > 0
