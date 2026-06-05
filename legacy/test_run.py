import asyncio
from pathlib import Path
from core.settings import load as load_settings
from orchestrator import Orchestrator

async def main():
    settings_path = Path("settings.json")
    if not settings_path.exists():
        print("settings.json not found, using defaults")
        # Need to create dummy settings or something
        
    settings = load_settings(settings_path)
    # Set project path to current directory to scan itself
    settings.project_path = Path(".").resolve()
    
    orc = Orchestrator()
    
    print("Starting audit job on the Nexus Audit V3 codebase itself...")
    job = await orc.start_job(settings.project_path, settings)
    
    print(f"Job ID: {job.id}")
    try:
        # Wait up to 60 seconds for the scan to complete
        async def wait_job():
            while job.state == "running":
                await asyncio.sleep(1)
                
        await asyncio.wait_for(wait_job(), timeout=60)
        print(f"Job finished with state: {job.state}")
        
        # Output the report path if generated
        report_path = settings.project_path / "audit_report.md"
        data_path = settings.project_path / "audit_data_complete.json"
        
        print("\nOutputs generated:")
        if report_path.exists():
            print(f"- {report_path.name}")
        if data_path.exists():
            print(f"- {data_path.name}")
            
    except asyncio.TimeoutError:
        print(f"Timeout! Job stuck in state: {job.state}")
    except Exception as e:
        print(f"Error occurred: {e}")
    
if __name__ == "__main__":
    asyncio.run(main())
