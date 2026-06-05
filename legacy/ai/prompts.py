from typing import Any
from core.models import Finding
from core.scoring_engine import AppScore

def build_system_prompt(config: dict[str, Any]) -> str:
    """
    Builds the AI system prompt dynamically from the audit config.
    """
    apps_data = config.get("apps", [])
    app_descriptions = []
    for app in apps_data:
        name = app.get("name", "Unknown")
        role = app.get("role", "No role defined")
        hub = " (Hub App)" if app.get("hub") else ""
        app_descriptions.append(f"- **{name}**{hub}: {role}")
        
    apps_text = "\n".join(app_descriptions) if app_descriptions else "No specific app boundaries defined."
    
    return f"""You are an expert software architect assisting with a codebase audit.
The project follows these architectural boundaries:

{apps_text}

Provide concise, actionable advice. Focus on structural integrity, maintainability, and security.
Output should be formatted in Markdown."""

def build_violation_prompt(
    finding: Finding,
    persistence: str,
    config: dict[str, Any],
) -> tuple[str, str]:
    """Deep analysis of a single boundary violation."""
    system = build_system_prompt(config)
    
    user = f"""Analyze this architectural violation:
Title: {finding.title}
File: {finding.file}
Description: {finding.description}
Status: {persistence} (new, persistent, intermittent, resolved)

Please explain WHY this is a problem in the context of the project architecture, and provide a concrete recommendation to fix it."""

    return system, user

def build_health_prompt(
    app: str,
    score: AppScore,
    config: dict[str, Any],
) -> tuple[str, str]:
    """4-sentence health narrative for one app."""
    system = build_system_prompt(config)
    
    user = f"""Provide a concise health narrative (maximum 4 sentences) for the app '{app}'.
Current Score: {score.score}/100
Violations: {score.finding_counts.get('violations', 0)}
Security Issues: {score.finding_counts.get('security_high', 0)} High, {score.finding_counts.get('security_medium', 0)} Medium
"""

    return system, user

def build_upgrade_prompt(packages: list[dict[str, Any]]) -> tuple[str, str]:
    """Package upgrade advisor — returns structured JSON."""
    system = "You are an expert Python dependency manager. Provide package upgrade advice in structured JSON format."
    
    pkgs_str = ", ".join(f"{p['name']} ({p['current']} -> {p['latest']})" for p in packages)
    user = f"""Review these outdated packages and recommend which ones should be upgraded immediately, and which might contain breaking changes:
{pkgs_str}

Return JSON like: {{"upgrades": [{{"package": "name", "recommendation": "do it", "risk": "low"}}]}}"""

    return system, user

def build_cve_prompt(cves: list[dict[str, Any]]) -> tuple[str, str]:
    """CVE security advisor — returns structured JSON."""
    system = "You are an expert security researcher. Provide CVE remediation advice in structured JSON format."
    
    cves_str = "\n".join(f"- {c['id']} in {c['package']}: {c['summary']}" for c in cves)
    user = f"""Analyze these security vulnerabilities and provide specific remediation steps:
{cves_str}

Return JSON like: {{"remediations": [{{"cve": "id", "action": "upgrade to X", "urgency": "high"}}]}}"""

    return system, user
