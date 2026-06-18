import asyncio
import json
from pathlib import Path
from core.primitives.settings import SettingsManager
from orchestrator import Orchestrator

async def main():
    sm = SettingsManager()
    project = await sm.register_project("test-audit", "/tmp/test-audit")
    
    # Enable at least one fast scanner so it doesn't fail
    project.settings.scanners["DjangoSettings"] = True
    await sm.save_project(project)
    
    # Run audit
    orchestrator = Orchestrator(sm)
    job = await orchestrator.start_job(project.id)
    
    # Wait for completion
    while job.state.value in ("pending", "running"):
        await asyncio.sleep(0.5)
        
    print(f"Job state: {job.state.value}")
    if job.error:
        print(f"Error: {job.error}")
        
    output_file = Path.home() / ".nexus_audit" / "projects" / project.id / "jobs" / job.id / "audit_data_complete.json"
    if output_file.exists():
        data = json.loads(output_file.read_text())
        print("Keys present in audit_data_complete.json:")
        for k in data.keys():
            print(f"- {k}")
    else:
        print("Output file not found!")
        
    # Cleanup
    await sm.delete_project(project.id)

if __name__ == "__main__":
    asyncio.run(main())
