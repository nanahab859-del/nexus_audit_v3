import asyncio
from core.primitives.settings import SettingsManager
from core.primitives.commands import CommandRegistry, CommandContext

async def test():
    sm = SettingsManager()
    reg = CommandRegistry(sm)
    ctx = CommandContext(await sm.load_workspace(), sm)
    
    # Test system:version
    res = await reg.execute("system:version", ctx)
    print(res.stdout_buffer)
    
    # Test privilege denial
    ctx.privilege_level = 0
    res = await reg.execute("project:delete 123", ctx)
    print(res.stdout_buffer)

asyncio.run(test())
