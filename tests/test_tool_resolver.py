import pytest
from core.tool_resolver import is_tool_available, get_tool_version

def test_is_tool_available():
    # Python should be available
    assert is_tool_available("python") or is_tool_available("python3")
    
    # A fake tool should not be available
    assert not is_tool_available("this_is_a_fake_tool_name_12345")

def test_get_tool_version():
    # For python we expect some version string to be parsed
    version = get_tool_version("python") or get_tool_version("python3")
    assert version is not None
    assert isinstance(version, str)

    # Fake tool
    assert get_tool_version("this_is_a_fake_tool_name_12345") is None
