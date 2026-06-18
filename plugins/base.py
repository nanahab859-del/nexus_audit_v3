import asyncio
import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar, List, Any, Tuple, Optional
from core.primitives.models import Finding, Category
from core.primitives.events import EventBus
from core.infra.tool_resolver import ToolResolver, ToolNotFoundError

logger = logging.getLogger(__name__)

class BaseScanner(ABC):
    # ── ClassVar metadata (required) ────────────────────────
    name: ClassVar[str]
    version: ClassVar[str]
    languages: ClassVar[List[str]]
    category: ClassVar[Category]
    requires_tool: ClassVar[bool]
    tool_name: ClassVar[str]
    ecosystem: ClassVar[str] = "python" # Added ecosystem

    # ── ClassVar metadata (optional) ─────────────────────────
    requires_ai: ClassVar[bool] = False
    timeout: ClassVar[int] = 120

    def __init__(self, config: dict, bus: EventBus):
        self.config = config
        self.bus = bus
        self.resolver = ToolResolver()

    @abstractmethod
    async def scan(self, target: Path, config: dict, bus: EventBus) -> List[Finding]:
        """Execute the scan."""
        pass

    @abstractmethod
    def _parse_output(self, output: Any) -> List[Finding]:
        """Parse tool output into Findings."""
        pass

    async def _check_tool(self, bus: EventBus) -> bool:
        if not self.requires_tool:
            return True
        try:
            await self.resolver.resolve(self.tool_name, self.ecosystem)
            return True
        except ToolNotFoundError:
            logger.warning(f"Scanner '{self.name}' requires tool '{self.tool_name}' which is not installed.")
            await bus.publish_log("warning", f"Scanner '{self.name}' requires tool '{self.tool_name}' in {self.ecosystem}")
            return False

    async def _build_args(self, target: Path, config: dict) -> List[str]:
        return []

    async def _filter_to_changed(
        self,
        findings: List[Finding],
        file_filter: Optional[List[str]]
    ) -> List[Finding]:
        """Filter findings to only files in the changed-file list (fast mode)."""
        if not file_filter:
            return findings
        changed = set(file_filter)
        return [f for f in findings if not f.file or f.file in changed]

    async def _run_tool(
        self,
        args: List[str],
        bus: EventBus,
        working_dir: Optional[Path] = None
    ) -> Tuple[int, str, str]:
        try:
            cmd = await self.resolver.resolve(self.tool_name, self.ecosystem)
            cmd.extend(args)
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(working_dir) if working_dir else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
            return proc.returncode, stdout.decode(errors='ignore'), stderr.decode(errors='ignore')
        except asyncio.TimeoutError:
            # Clean up zombies
            try:
                proc.terminate()
                await proc.wait()
            except:
                pass
            logger.error(f"Scanner '{self.name}' timed out")
            return 1, "", "Timeout exceeded"
        except ToolNotFoundError:
            return 127, "", "Tool not found"
        except Exception as e:
            logger.error(f"Scanner '{self.name}' failed: {e}")
            return 1, "", str(e)

def validate_scanner_class(cls: type) -> List[str]:
    errors = []
    required_attrs = ["name", "version", "languages", "category", "tool_name", "requires_tool"]
    for attr in required_attrs:
        if not hasattr(cls, attr):
            errors.append(f"Missing required attribute: {attr}")
    
    if not hasattr(cls, "scan"):
        errors.append("scan() method must be implemented")
    if not hasattr(cls, "_parse_output"):
        errors.append("_parse_output() method must be implemented")
        
    if hasattr(cls, "languages") and not isinstance(cls.languages, list):
        errors.append("languages must be a list")
    
    # Validate category is Category Enum
    if hasattr(cls, "category") and not isinstance(cls.category, Category):
        errors.append("category must be a Category enum")
        
    return errors
