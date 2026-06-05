import json
import os
from pathlib import Path
from typing import Any, Optional

async def write_json(path: Path, data: Any):
    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, path)

async def read_json(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    with open(path, "r") as f:
        return json.load(f)
