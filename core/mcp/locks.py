import asyncio
from collections import defaultdict

_project_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

class _WithProjectLock:
    def __init__(self, project_path: str):
        self.project_path = project_path

    async def __aenter__(self):
        await _project_locks[self.project_path].acquire()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        _project_locks[self.project_path].release()

def project_lock(project_path: str):
    return _WithProjectLock(project_path)

async def _with_project_lock(project_path: str, coro):
    """Ensure only one state-modifying action runs at a time per project."""
    async with _project_locks[project_path]:
        return await coro
