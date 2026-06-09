# conftest.py — lives at the project root so pytest adds it to sys.path
# This is the ONLY thing needed to fix "ModuleNotFoundError: No module named 'orchestrator'"
import sys
from pathlib import Path

# Ensure the project root is always on sys.path regardless of where pytest is
# invoked from (e.g. `pytest tests/` from /home/yusupha/my_tools/nexus_audit_v3).
ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
