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
    """
    # 1. Ensure parent exists
    ensure_dir(path.parent)
    
    # Serialize data - remove default=str to force failure on non-serializable objects
    json_str = json.dumps(data, indent=indent)
    
    # 3. Use UUID4 for temp file name
    tmp_path = path.with_suffix(f".{uuid.uuid4()}.tmp")
    
    try:
        # 3. Write to temp file
        async with aiofiles.open(tmp_path, "w", encoding="utf-8") as f:
            await f.write(json_str)
            
            # 4. Flush internal buffer
            await f.flush()
            
            # 5. fsync to guarantee data hits disk
            os.fsync(f.fileno())
        
        # 6. Atomic rename
        os.replace(str(tmp_path), str(path))
        
    except Exception as e:
        # 7. Cleanup on failure
        if tmp_path.exists():
            os.remove(tmp_path)
        logger.error(f"Failed to atomically write JSON to {path}: {e}")
        raise

async def read_json(path: Path) -> Optional[Any]:
    """
    Read and parse a JSON file. Return None if missing or corrupt.
    """
    if not path.exists():
        return None
        
    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            content = await f.read()
        return json.loads(content)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Failed to read/parse JSON from {path}: {e}")
        return None
