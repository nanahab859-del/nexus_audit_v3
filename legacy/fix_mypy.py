import re

files_to_fix = [
    'core/key_pool.py', 'core/dep_cache.py', 'core/atomic.py', 'core/models.py',
    'core/timeline.py', 'core/fix_queue.py', 'core/file_discovery.py', 'core/git_context.py',
    'core/source_sync.py', 'core/dna_builder.py', 'core/coupling.py', 'core/rules_engine.py',
    'core/scoring_engine.py', 'core/reports/markdown_report.py', 'plugins/base.py',
    'plugins/security/django_settings_plugin.py', 'plugins/security/bandit_plugin.py',
    'plugins/quality/vulture_plugin.py', 'plugins/quality/semgrep_plugin.py',
    'plugins/quality/radon_plugin.py', 'plugins/dependency/safety_plugin.py',
    'plugins/architecture/lizard_plugin.py', 'api/routes_stream.py', 'api/routes_report.py',
    'api/routes_data.py', 'api/middleware.py', 'api/server.py', 'ai/prompts.py', 'orchestrator.py'
]

for file in files_to_fix:
    try:
        with open(file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Global dict/list type fixes
        content = re.sub(r':\s*dict([^\w\[])', r': dict[str, Any]\1', content)
        content = re.sub(r'->\s*dict([^\w\[])', r'-> dict[str, Any]\1', content)
        content = re.sub(r':\s*list([^\w\[])', r': list[Any]\1', content)
        content = re.sub(r'->\s*list([^\w\[])', r'-> list[Any]\1', content)
        content = re.sub(r'def ([a-zA-Z0-9_]+)\(self\):', r'def \1(self) -> None:', content)
        content = re.sub(r'def ([a-zA-Z0-9_]+)\(self, ([^)]+)\):', r'def \1(self, \2) -> None:', content)
        
        # Specific fixes
        if 'orchestrator.py' in file:
            content = content.replace('_current_task: asyncio.Task | None', '_current_task: asyncio.Task[Any] | None')
            content = content.replace('changed = get_changed_files(job.project_path)', 'changed = await get_changed_files(job.project_path)')
            content = content.replace('app_scores.get("fleet_average").score if "fleet_average" in app_scores else 0.0', 'app_scores["fleet_average"].score if "fleet_average" in app_scores and app_scores["fleet_average"] else 0.0')
            content = content.replace('fix_queue.get_status(f.id).status if fix_queue.get_status(f.id) else "open"', '(fix_queue.get_status(f.id).status if fix_queue.get_status(f.id) is not None else "open")  # type: ignore')
            
        if 'core/source_sync.py' in file:
            content = content.replace('Path | None', 'Path')
            
        if 'core/rules_engine.py' in file:
            content = content.replace('captures = query.captures(tree.root_node)', 'captures = query.captures(tree.root_node)  # type: ignore')
            content = content.replace('def dfs(node):', 'def dfs(node: Any) -> None:')
            
        if 'core/dna_builder.py' in file:
            content = content.replace('captures = query.captures(tree.root_node)', 'captures = query.captures(tree.root_node)  # type: ignore')
            
        if 'api/server.py' in file:
            content = content.replace('-> Response:', '-> web.Response | web.FileResponse:')
            
        if 'api/routes_report.py' in file:
            content = content.replace('-> web.Response:', '-> web.FileResponse:')
            
        with open(file, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        print(f"Failed {file}: {e}")
