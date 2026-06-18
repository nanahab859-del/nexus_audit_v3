from core.primitives.commands.context import READONLY, ADMIN


def register(registry) -> None:
    from core.primitives.commands.registry import Command
    from core.primitives.commands.parser import CommandParser

    registry.register(Command(
        name="ai:status",
        description="Show AI module availability.",
        usage="ai:status",
        handler=_stub("ai:status"),
        required_privilege=READONLY,
    ))

    registry.register(Command(
        name="ai:test",
        description="Run a connectivity test against the AI backend.",
        usage="ai:test",
        handler=_stub("ai:test"),
        required_privilege=ADMIN,
    ))

    registry.register(Command(
        name="ai:recommend",
        description="Get an AI-generated fix recommendation for a finding.",
        usage="ai:recommend <finding_id>",
        handler=_stub("ai:recommend"),
        required_privilege=READONLY,
        parser=CommandParser("ai:recommend").add_argument("finding_id"),
    ))


def _stub(name: str):
    async def _handler(ctx, params):
        ctx.write(f"[TODO] '{name}' — AI module not yet implemented.")
    return _handler
