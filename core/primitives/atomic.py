import json
import os
import logging
import uuid
import aiofiles
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

def ensure_dir(path: Path) -> None:
    """
    Create directory with restricted permissions (0o755) if it does not exist.
    """
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True, mode=0o755)

async def write_json(path: Path, data: Any, indent: int | None = None) -> None:
    """
    Atomically write data as JSON with durability and crash safety.

    Steps:
      1. Serialise data to JSON string
      2. Ensure parent directory exists
      3. Write to a UUID-named temp file in the same directory
      4. Flush kernel buffers (f.flush)
      5. fsync to guarantee data hits storage
      6. Atomic rename to final path (os.replace)
      7. Clean up temp file on any failure
    """
    json_str = json.dumps(data, indent=indent)    # 1. Serialise
    ensure_dir(path.parent)                        # 2. Ensure parent
    tmp_path = path.with_suffix(f".{uuid.uuid4()}.tmp")   # 3. Temp path
    
    try:
        async with aiofiles.open(tmp_path, "w", encoding="utf-8") as f:
            await f.write(json_str)    # 3. Write
            await f.flush()            # 4. Flush
            os.fsync(f.fileno())       # 5. fsync
        
        os.replace(str(tmp_path), str(path))       # 6. Atomic rename
        
    except Exception as e:
        if tmp_path.exists():
            try:
                os.remove(tmp_path)    # 7. Cleanup
            except OSError:
                pass
        logger.error(f"Failed to atomically write JSON to {path}: {e}")
        raise

async def read_json(path: Path) -> Optional[Any]:
    """
    Read and parse a JSON file.

    Returns None if the file does not exist, is unreadable (PermissionError),
    or contains invalid/empty JSON — callers treat None as "not available".
    """
    if not path.exists():
        return None

    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            content = await f.read()
    except (OSError, PermissionError):
        return None

    if not content.strip():
        return None

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None

