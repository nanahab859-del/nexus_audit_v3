"""
One-time migration: re-save workspace and all projects so that Enum fields
are stored as name strings (e.g. "CRITICAL") instead of int values (e.g. 4).

Run once after updating to_dict() to use .name instead of .value:
    python migrate_enum_format.py
"""
import asyncio
from core.primitives.settings import SettingsManager


async def main():
    sm = SettingsManager()
    workspace = await sm.load_workspace()
    print(f"Found {len(workspace.projects)} project(s).")

    for pid in list(workspace.projects.keys()):
        try:
            project = await sm.load_project(pid)
            await sm.save_project(project)
            print(f"  Re-saved project: {project.name} ({pid[:8]})")
        except Exception as e:
            print(f"  FAILED for {pid}: {e}")

    await sm.save_workspace(workspace)
    print("Workspace re-saved.")
    print("Migration complete.")


if __name__ == "__main__":
    asyncio.run(main())
