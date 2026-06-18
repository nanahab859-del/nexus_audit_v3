import asyncio
from core.infra.tool_resolver import ToolResolver
import json

tools = ["bandit", "vulture", "semgrep", "safety", "radon", "lizard", "ruff", "mypy", "pylint", "trufflehog", "djlint", "eslint", "pip-licenses", "django_settings", "secretscrub", "generic_script"]

async def main():
    installed = []
    not_installed = []
    resolver = ToolResolver()
    for tool in tools:
        if await resolver.is_available(tool):
            installed.append(tool)
        else:
            not_installed.append(tool)
    print(f"Installed: {installed}")
    print(f"Not installed: {not_installed}")

asyncio.run(main())
