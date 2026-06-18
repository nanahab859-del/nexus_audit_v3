import asyncio
from pathlib import Path
from core.primitives.settings import SettingsManager
from orchestrator import Orchestrator

async def main():
    sm = SettingsManager()
    project = await sm.register_project("test-audit", "/tmp/test-audit")
    project.settings.scanners["DjangoSettings"] = True
    await sm.save_project(project)
    
    orchestrator = Orchestrator(sm)
    job = await orchestrator.start_job(project.id)
    
    while True:
        job = sm._jobs.get(job.id, job) # reload job
        if job.state.value not in ("pending", "running"):
            break
        await asyncio.sleep(0.5)
        
    output_file = Path.home() / ".nexus_audit" / "projects" / project.id / "jobs" / job.id / "audit_data_complete.json"
    import json
    data = json.loads(output_file.read_text())
    print("KEYS:", list(data.keys()))
    await sm.delete_project(project.id)

asyncio.run(main())
