import os
import re

def fix_file(path):
    if not os.path.exists(path):
        return
        
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    orig = content
        
    # Add Any to imports if not there
    if 'typing' in content and 'Any' not in content:
        content = re.sub(r'from typing import (.*)', r'from typing import Any, \1', content)
    elif 'from typing import ' not in content:
        content = 'from typing import Any\n' + content
        
    # Replace dict -> dict[str, Any] in annotations
    content = re.sub(r':\s*dict([^\w\[])', r': dict[str, Any]\1', content)
    content = re.sub(r'->\s*dict([^\w\[])', r'-> dict[str, Any]\1', content)
    
    # Add -> None to defs missing return type (simplistic)
    # def _refresh_exhausted(self): -> def _refresh_exhausted(self) -> None:
    content = re.sub(r'(def [a-zA-Z0-9_]+\([^)]*\)):\n', r'\1 -> None:\n', content)
    
    # For Orchestrator
    if 'orchestrator.py' in path:
        content = content.replace('changed = get_changed_files(job.project_path)', 'changed = await get_changed_files(job.project_path)')
        content = content.replace('_current_task: asyncio.Task | None', '_current_task: asyncio.Task[Any] | None')
        
    # For dna_builder and rules_engine query.captures
    if 'dna_builder.py' in path or 'rules_engine.py' in path:
        content = content.replace('captures = query.captures(tree.root_node)', 'captures = query.captures(tree.root_node)  # type: ignore')
        
    if orig != content:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)

files_to_fix = [
    'core/key_pool.py',
    'core/dep_cache.py',
    'core/atomic.py',
    'core/models.py',
    'core/timeline.py',
    'core/fix_queue.py',
    'core/file_discovery.py',
    'core/git_context.py',
    'core/source_sync.py',
    'core/dna_builder.py',
    'core/coupling.py',
    'core/rules_engine.py',
    'core/scoring_engine.py',
    'core/reports/markdown_report.py',
    'plugins/base.py',
    'plugins/security/django_settings_plugin.py',
    'plugins/security/bandit_plugin.py',
    'plugins/quality/vulture_plugin.py',
    'plugins/quality/semgrep_plugin.py',
    'plugins/quality/radon_plugin.py',
    'plugins/dependency/safety_plugin.py',
    'plugins/architecture/lizard_plugin.py',
    'api/routes_stream.py',
    'api/routes_report.py',
    'api/routes_data.py',
    'api/middleware.py',
    'api/server.py',
    'ai/prompts.py',
    'orchestrator.py'
]

for f in files_to_fix:
    fix_file(f)
