import asyncio
import pytest
import subprocess
from pathlib import Path
from core.infra.fast_check import get_changed_files

@pytest.mark.asyncio
async def test_changed_tracked_files(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True)
    
    # Create committed file
    f1 = repo_dir / "committed.txt"
    f1.write_text("initial")
    subprocess.run(["git", "add", "committed.txt"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_dir, check=True)
    
    # Modify it
    f1.write_text("modified")
    
    changed = await get_changed_files(repo_dir)
    assert changed is not None
    assert any(p.name == "committed.txt" for p in changed)

@pytest.mark.asyncio
async def test_untracked_files(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=repo_dir, check=True)
    
    # Create untracked file
    f1 = repo_dir / "untracked.txt"
    f1.write_text("hello")
    
    changed = await get_changed_files(repo_dir)
    # The requirement says "return None if Git is unavailable, the directory isn't a repo, or any error occurs."
    # If the repo has no commits, rev-parse --verify HEAD fails, so it returns None.
    # The test for "no commits" will cover this.
    # If I make a commit, then it works.
    
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True)
    subprocess.run(["git", "add", "untracked.txt"], cwd=repo_dir, check=True) # wait, if I add it, it's staged.
    # Let's try adding it to gitignore
    (repo_dir / ".gitignore").write_text("ignored.txt")
    (repo_dir / "ignored.txt").write_text("ignore me")
    
    # Re-run check with a commit first
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_dir, check=True)
    
    # Now create new untracked
    (repo_dir / "new.txt").write_text("new")
    
    changed = await get_changed_files(repo_dir)
    assert changed is not None
    assert any(p.name == "new.txt" for p in changed)
    assert not any(p.name == "ignored.txt" for p in changed)

@pytest.mark.asyncio
async def test_clean_tree(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True)
    
    (repo_dir / "file.txt").write_text("content")
    subprocess.run(["git", "add", "file.txt"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_dir, check=True)
    
    changed = await get_changed_files(repo_dir)
    assert changed == []

@pytest.mark.asyncio
async def test_no_commits(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=repo_dir, check=True)
    
    changed = await get_changed_files(repo_dir)
    assert changed is None

@pytest.mark.asyncio
async def test_non_repo(tmp_path):
    changed = await get_changed_files(tmp_path)
    assert changed is None

@pytest.mark.asyncio
async def test_path_normalization(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True)
    
    # Subdirectory
    sub_dir = repo_dir / "sub"
    sub_dir.mkdir()
    (sub_dir / "file.txt").write_text("content")
    
    # Must commit to have HEAD
    subprocess.run(["git", "add", "sub/file.txt"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_dir, check=True)
    
    # Modify it to be detected
    (sub_dir / "file.txt").write_text("modified content")
    
    changed = await get_changed_files(sub_dir)
    assert changed is not None
    assert any(p.is_absolute() for p in changed)
    assert any(p.name == "file.txt" for p in changed)

@pytest.mark.asyncio
async def test_fast_check_timeout(monkeypatch, tmp_path):
    async def mock_create_subprocess_exec(*args, **kwargs):
        class MockProc:
            returncode = 0
            async def communicate(self):
                raise asyncio.TimeoutError()
            def terminate(self): pass
            async def wait(self): pass
        return MockProc()
    monkeypatch.setattr("asyncio.create_subprocess_exec", mock_create_subprocess_exec)
    changed = await get_changed_files(tmp_path)
    assert changed is None

@pytest.mark.asyncio
async def test_fast_check_exception(monkeypatch, tmp_path):
    async def mock_create_subprocess_exec(*args, **kwargs):
        raise Exception("generic error")
    monkeypatch.setattr("asyncio.create_subprocess_exec", mock_create_subprocess_exec)
    changed = await get_changed_files(tmp_path)
    assert changed is None

@pytest.mark.asyncio
async def test_fast_check_root_none(monkeypatch, tmp_path):
    async def mock_run_git(args, *, cwd=None, timeout=30):
        if "HEAD" in args and "rev-parse" in args:
            return "head_exists"
        if "--show-toplevel" in args:
            return None
        return ""
    monkeypatch.setattr("core.infra.git_utils.run_git", mock_run_git)
    changed = await get_changed_files(tmp_path)
    assert changed is None

@pytest.mark.asyncio
async def test_run_git_command_terminate_exception(tmp_path, monkeypatch):
    from core.infra.git_utils import run_git
    import asyncio

    class MockProc:
        returncode = None
        async def communicate(self):
            await asyncio.sleep(10)
        def terminate(self):
            raise RuntimeError("Mock terminate error")
        async def wait(self):
            pass

    async def mock_create(*args, **kwargs):
        return MockProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_create)
    # mock wait_for to just raise TimeoutError
    async def mock_wait_for(coro, timeout):
        raise asyncio.TimeoutError()
    monkeypatch.setattr(asyncio, "wait_for", mock_wait_for)

    res = await run_git(["status"], cwd=tmp_path)
    assert res is None
