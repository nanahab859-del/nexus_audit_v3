import os

# 1. audit_logger.py
with open("tests/infra/test_audit_logger.py", "a") as f:
    f.write("""
@pytest.mark.asyncio
async def test_mkdir_failure_on_start(tmp_path, bus, monkeypatch):
    from pathlib import Path
    logger = AuditLogger("job3", bus, tmp_path)
    def mock_mkdir(*args, **kwargs): raise OSError("Mock mkdir error")
    monkeypatch.setattr(Path, "mkdir", mock_mkdir)
    await logger.start()
    assert logger._io_failed

@pytest.mark.asyncio
async def test_circuit_breaker_fast_return(tmp_path, bus):
    logger = AuditLogger("job4", bus, tmp_path)
    logger._io_failed = True
    # Should return immediately and not throw
    class MockEvent:
        pass
    await logger._handle_log(MockEvent())

@pytest.mark.asyncio
async def test_periodic_flush_and_write_failure(tmp_path, bus, monkeypatch):
    import asyncio
    logger = AuditLogger("job5", bus, tmp_path)
    logger._findings_buffer.append({"id": "f_1"})
    
    def mock_write_json(*args, **kwargs):
        raise OSError("Mock write error")
    monkeypatch.setattr("core.infra.audit_logger.write_json", mock_write_json)
    
    # Run _periodic_flush manually to trigger the loop once
    async def mock_sleep(delay):
        if delay == 5:
            raise asyncio.CancelledError() # Break the while True loop
    monkeypatch.setattr(asyncio, "sleep", mock_sleep)
    
    await logger._periodic_flush()
    assert logger._io_failed
""")

# 2. fast_check.py
with open("tests/infra/test_fast_check.py", "a") as f:
    f.write("""
@pytest.mark.asyncio
async def test_run_git_command_terminate_exception(tmp_path, monkeypatch):
    from core.infra.fast_check import run_git_command
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
    
    res = await run_git_command(tmp_path, ["status"])
    assert res is None
""")

# 3. file_discovery.py
with open("tests/infra/test_file_discovery.py", "a") as f:
    f.write("""
def test_symlink_protection_duplicate_resolve(tmp_path, monkeypatch):
    from core.infra.file_discovery import list_project_files
    from pathlib import Path
    
    # We monkeypatch Path.resolve to return the same path twice to simulate overlapping symlinks
    original_resolve = Path.resolve
    call_count = 0
    def mock_resolve(self):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            return original_resolve(Path("/"))
        return original_resolve(self)
        
    monkeypatch.setattr(Path, "resolve", mock_resolve)
    
    # Create a couple files so it loops
    (tmp_path / "f1.py").touch()
    (tmp_path / "f2.py").touch()
    
    res = list_project_files(tmp_path)
""")

# 4. registry.py
with open("tests/infra/test_registry.py", "a") as f:
    f.write("""
def test_registry_load_runtime_error(tmp_path, monkeypatch):
    from core.infra.registry import ScannerRegistry
    import asyncio
    
    class MockBus:
        def publish_log(self, *args, **kwargs): pass
        
    def mock_get_running_loop():
        raise RuntimeError("No loop")
    
    monkeypatch.setattr(asyncio, "get_running_loop", mock_get_running_loop)
    
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    (plugins_dir / "bad.py").write_text("1 / 0")
    
    registry = ScannerRegistry(plugins_dir, bus=MockBus())
    registry.load() # Should catch RuntimeError and use logger.warning

def test_registry_load_no_bus(tmp_path):
    from core.infra.registry import ScannerRegistry
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    (plugins_dir / "bad.py").write_text("1 / 0")
    
    registry = ScannerRegistry(plugins_dir, bus=None)
    registry.load() # Should use logger.warning
""")

# 5. tool_resolver.py
with open("tests/infra/test_tool_resolver.py", "a") as f:
    f.write("""
@pytest.mark.asyncio
async def test_system_path_mocked(monkeypatch):
    from core.infra.tool_resolver import ToolResolver
    monkeypatch.setattr("core.infra.tool_resolver.get_venv_python", lambda: None)
    monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/dummy_system_tool")
    
    resolver = ToolResolver()
    resolved = await resolver.resolve("dummy_system_tool")
    assert resolved == ["/usr/bin/dummy_system_tool"]
""")
