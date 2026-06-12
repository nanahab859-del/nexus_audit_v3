import json
import logging
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Optional
from enum import Enum
from core.primitives.events import EventBus, EventType
from core.primitives.atomic import write_json

class AuditAction(Enum):
    PHASE_START = "phase_start"
    PHASE_COMPLETE = "phase_complete"
    PHASE_ERROR = "phase_error"
    DETECTION = "detection"
    FINDING = "finding"
    DECISION = "decision"
    ERROR = "error"
    WARNING = "warning"
    DEBUG = "debug"

class ActionLogger:
    def __init__(self, job_id: str, bus: EventBus, log_path: Path):
        self._job_id = job_id
        self._bus = bus
        self.log_path = log_path
        self.entries = []
        self.start_time = datetime.now(timezone.utc)
    
    async def log_action(self, 
                   action: AuditAction, 
                   component: str,
                   message: str,
                   details: Optional[dict[str, Any]] = None,
                   level: str = "info") -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action.value,
            "component": component,
            "message": message,
            "level": level,
            "details": details or {}
        }
        self.entries.append(entry)
        # Publish event for telemetry
        await self._bus.publish(EventType.LOG, {"level": level, "message": message, "action": action.value})
    
    async def log_phase_start(self, phase_num: int, phase_name: str, context: dict = None) -> None:
        await self.log_action(
            AuditAction.PHASE_START,
            f"orchestrator.phase_{phase_num}",
            f"PHASE {phase_num}: {phase_name} - Starting",
            {"phase": phase_num, "name": phase_name, **(context or {})},
            "info"
        )
    
    async def log_phase_complete(self, phase_num: int, phase_name: str, 
                          result_count: int = 0, context: dict = None) -> None:
        await self.log_action(
            AuditAction.PHASE_COMPLETE,
            f"orchestrator.phase_{phase_num}",
            f"PHASE {phase_num}: {phase_name} - Completed",
            {
                "phase": phase_num,
                "name": phase_name,
                "result_count": result_count,
                **(context or {})
            },
            "info"
        )
    
    async def log_phase_error(self, phase_num: int, phase_name: str, error: str, 
                       traceback_str: str = None) -> None:
        await self.log_action(
            AuditAction.PHASE_ERROR,
            f"orchestrator.phase_{phase_num}",
            f"PHASE {phase_num}: {phase_name} - FAILED",
            {
                "phase": phase_num,
                "name": phase_name,
                "error": error,
                "traceback": traceback_str
            },
            "error"
        )
    
    async def log_detection(self, detector_name: str, detected_items: list[str], 
                     reason: str = None, context: dict = None) -> None:
        await self.log_action(
            AuditAction.DETECTION,
            f"detection.{detector_name}",
            f"Detected: {', '.join(detected_items)}",
            {
                "detector": detector_name,
                "detected_items": detected_items,
                "count": len(detected_items),
                "reason": reason,
                **(context or {})
            },
            "info"
        )
    
    async def log_app_detection(self, apps: list[str], mode: str, 
                         indicators: dict = None) -> None:
        await self.log_action(
            AuditAction.DETECTION,
            "detection.apps",
            f"App detection: {mode} mode detected {len(apps)} app(s)",
            {
                "apps": apps,
                "mode": mode,
                "count": len(apps),
                "indicators": indicators or {}
            },
            "info"
        )
    
    async def log_decision(self, component: str, decision_name: str, chosen_option: str, 
                    alternatives: list[str] = None, reasoning: str = None) -> None:
        await self.log_action(
            AuditAction.DECISION,
            component,
            f"Decision '{decision_name}': chose '{chosen_option}'",
            {
                "decision": decision_name,
                "chosen": chosen_option,
                "alternatives": alternatives or [],
                "reasoning": reasoning
            },
            "info"
        )
    
    async def log_finding(self, scanner: str, category: str, severity: str, 
                   count: int, examples: list[str] = None) -> None:
        await self.log_action(
            AuditAction.FINDING,
            f"scanner.{scanner}",
            f"Scanner '{scanner}' found {count} {category} issues",
            {
                "scanner": scanner,
                "category": category,
                "severity": severity,
                "count": count,
                "examples": examples or []
            },
            "info"
        )
    
    async def log_error(self, component: str, error_msg: str, 
                 error_type: str = None, context: dict = None) -> None:
        await self.log_action(
            AuditAction.ERROR,
            component,
            f"Error: {error_msg}",
            {
                "error_type": error_type or "Unknown",
                "error_message": error_msg,
                **(context or {})
            },
            "error"
        )
    
    async def log_warning(self, component: str, warning_msg: str, context: dict = None) -> None:
        await self.log_action(
            AuditAction.WARNING,
            component,
            f"Warning: {warning_msg}",
            context or {},
            "warning"
        )
    
    async def log_debug(self, component: str, debug_msg: str, context: dict = None) -> None:
        await self.log_action(
            AuditAction.DEBUG,
            component,
            debug_msg,
            context or {},
            "debug"
        )
    
    async def save(self) -> None:
        """Save audit log to file atomically."""
        try:
            audit_data = {
                "metadata": {
                    "started_at": self.start_time.isoformat(),
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "total_entries": len(self.entries),
                    "total_errors": sum(1 for e in self.entries if e["level"] == "error"),
                    "total_warnings": sum(1 for e in self.entries if e["level"] == "warning"),
                },
                "entries": self.entries
            }
            await write_json(self.log_path, audit_data, indent=2)
            
            logging.info(f"[ACTION_LOGGER] Saved comprehensive audit log to {self.log_path}")
        except Exception as e:
            logging.error(f"[ACTION_LOGGER] Failed to save audit log: {e}")
