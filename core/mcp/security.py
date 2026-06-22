from pathlib import Path

def _assert_safe_path(path_str: str) -> Path:
    p = Path(path_str).resolve()
    base = (Path.home() / ".nexus_audit").resolve()
    try:
        p.relative_to(base)
    except ValueError:
        raise ValueError(f"Path outside allowed sandbox: {path_str}")
    return p
