import pytest
import asyncio
from pathlib import Path
from core.infra.git_context import get_git_context, _convert_ssh_to_https

@pytest.mark.asyncio
async def test_get_git_context_valid(monkeypatch):
    async def mock_run_git(path, *args):
        cmd = " ".join(args)
        if "remote get-url origin" in cmd: return "git@github.com:user/repo.git"
        if "branch --show-current" in cmd: return "main"
        if "log -1 --format=%H|%an|%aI" in cmd: return "abc123def456|John Doe|2023-01-01T00:00:00Z"
        return ""
    monkeypatch.setattr("core.infra.git_context._run_git", mock_run_git)
    
    ctx = await get_git_context(Path("/tmp"))
    assert ctx["remote_url"] == "https://github.com/user/repo"
    assert ctx["raw_remote_url"] == "git@github.com:user/repo.git"
    assert ctx["branch"] == "main"
    assert ctx["commit"] == "abc123def456"
    assert ctx["author"] == "John Doe"
    assert ctx["commit_timestamp"] == "2023-01-01T00:00:00Z"

@pytest.mark.asyncio
async def test_get_git_context_detached_head(monkeypatch):
    async def mock_run_git(path, *args):
        cmd = " ".join(args)
        if "remote get-url origin" in cmd: return "https://github.com/user/repo"
        if "branch --show-current" in cmd: return ""
        return "val"
    monkeypatch.setattr("core.infra.git_context._run_git", mock_run_git)
    
    ctx = await get_git_context(Path("/tmp"))
    assert ctx["branch"] is None

def test_convert_ssh_to_https():
    assert _convert_ssh_to_https("git@github.com:user/repo.git") == "https://github.com/user/repo"
    assert _convert_ssh_to_https("https://github.com/user/repo") == "https://github.com/user/repo"

@pytest.mark.asyncio
async def test_get_git_context_not_repo(monkeypatch):
    async def mock_run_git(path, *args):
        return None
    monkeypatch.setattr("core.infra.git_context._run_git", mock_run_git)
    assert await get_git_context(Path("/tmp")) == {}

@pytest.mark.asyncio
async def test_get_git_context_timeout(monkeypatch):
    async def mock_create_subprocess_exec(*args, **kwargs):
        class MockProc:
            returncode = 0
            async def communicate(self):
                pass
            def terminate(self): pass
            async def wait(self): pass
        return MockProc()
    monkeypatch.setattr("asyncio.create_subprocess_exec", mock_create_subprocess_exec)
    
    def mock_wait_for(aw, timeout):
        raise asyncio.TimeoutError()
    monkeypatch.setattr(asyncio, "wait_for", mock_wait_for)
    
    # We test the _run_git directly to hit the timeout line
    from core.infra.git_context import _run_git
    res = await _run_git(Path("/tmp"), "status")
    assert res is None

@pytest.mark.asyncio
async def test_get_git_context_git_not_installed(monkeypatch):
    async def mock_create_subprocess_exec(*args, **kwargs):
        raise FileNotFoundError()
    monkeypatch.setattr("asyncio.create_subprocess_exec", mock_create_subprocess_exec)
    
    from core.infra.git_context import _run_git
    res = await _run_git(Path("/tmp"), "status")
    assert res is None

@pytest.mark.asyncio
async def test_get_git_context_general_exception(monkeypatch):
    async def mock_create_subprocess_exec(*args, **kwargs):
        raise Exception("general error")
    monkeypatch.setattr("asyncio.create_subprocess_exec", mock_create_subprocess_exec)
    
    from core.infra.git_context import _run_git
    res = await _run_git(Path("/tmp"), "status")
    assert res is None

@pytest.mark.asyncio
async def test_get_git_context_non_zero_exit(monkeypatch):
    async def mock_create_subprocess_exec(*args, **kwargs):
        class MockProc:
            returncode = 1
            async def communicate(self):
                return b"", b"error"
        return MockProc()
    monkeypatch.setattr("asyncio.create_subprocess_exec", mock_create_subprocess_exec)
    monkeypatch.setattr(asyncio, "wait_for", lambda aw, timeout: aw)
    
    from core.infra.git_context import _run_git
    res = await _run_git(Path("/tmp"), "status")
    assert res is None

@pytest.mark.asyncio
async def test_run_git_success(monkeypatch):
    async def mock_create_subprocess_exec(*args, **kwargs):
        class MockProc:
            returncode = 0
            async def communicate(self):
                return b"success output\n", b""
        return MockProc()
    monkeypatch.setattr("asyncio.create_subprocess_exec", mock_create_subprocess_exec)
    
    from core.infra.git_context import _run_git
    res = await _run_git(Path("/tmp"), "status")
    assert res == "success output"

@pytest.mark.asyncio
async def test_run_git_timeout_exception_handling(monkeypatch):
    async def mock_create_subprocess_exec(*args, **kwargs):
        class MockProc:
            returncode = 0
            async def communicate(self):
                raise asyncio.TimeoutError()
            def terminate(self): pass
            async def wait(self):
                raise Exception("wait failed")
        return MockProc()
    monkeypatch.setattr("asyncio.create_subprocess_exec", mock_create_subprocess_exec)
    
    from core.infra.git_context import _run_git
    res = await _run_git(Path("/tmp"), "status")
    assert res is None
