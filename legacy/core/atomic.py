import json
import os
from pathlib import Path
from typing import Any

import aiofiles


async def write_json(path: Path, data: dict[str, Any] | list[Any]) -> None:
    """
    Write data as formatted JSON atomically.
    Serializes to path.with_suffix('.tmp'), then os.replace() to final path.
    .tmp file is always cleaned up.
    """
    tmp_path = path.with_suffix(".tmp")
    try:
        json_str = json.dumps(data, indent=2, default=str)
        async with aiofiles.open(tmp_path, "w") as f:
            await f.write(json_str)
        # os.replace() is atomic on POSIX and effectively atomic on Windows
        # when source and destination are on the same filesystem (always true here).
        os.replace(tmp_path, path)
    finally:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass


async def read_json(path: Path) -> dict[str, Any] | list[Any] | None:
    """
    Read and parse JSON from path.
    Returns None if path does not exist.
    Raises json.JSONDecodeError if file is corrupt.
    """
    if not path.exists():
        return None

    async with aiofiles.open(path, "r") as f:
        content = await f.read()
    return json.loads(content)
