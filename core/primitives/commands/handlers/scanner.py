from core.primitives.commands.context import READONLY, OPERATOR, ADMIN


def register(registry) -> None:
    from core.primitives.commands.registry import Command
    from core.primitives.commands.parser import CommandParser

    registry.register(Command(
        name="scanner:list",
        description="List all available scanners and their install status.",
        usage="scanner:list [--category NAME]",
        handler=_handle_list,
        required_privilege=READONLY,
        parser=CommandParser("scanner:list").add_argument("--category", default=None),
    ))

    registry.register(Command(
        name="scanner:enable",
        description="Enable a scanner for the active project.",
        usage="scanner:enable <name>",
        handler=_handle_enable,
        required_privilege=OPERATOR,
        parser=CommandParser("scanner:enable").add_argument("name"),
    ))

    registry.register(Command(
        name="scanner:disable",
        description="Disable a scanner for the active project.",
        usage="scanner:disable <name>",
        handler=_handle_disable,
        required_privilege=OPERATOR,
        parser=CommandParser("scanner:disable").add_argument("name"),
    ))

    registry.register(Command(
        name="scanner:install",
        description="Print the install command for a scanner's external tool.",
        usage="scanner:install <name>",
        handler=_handle_install,
        required_privilege=ADMIN,
        parser=CommandParser("scanner:install").add_argument("name"),
    ))

    registry.register(Command(
        name="scanner:config",
        description="View or update a scanner's configuration for the active project.",
        usage="scanner:config <name> [--strictness LEVEL]",
        handler=_handle_config,
        required_privilege=ADMIN,
        parser=(
            CommandParser("scanner:config")
            .add_argument("name")
            .add_argument("--strictness", default=None)
        ),
    ))


def _get_plugin_registry(ctx):
    """
    Use the orchestrator's shared PluginRegistry when available.
    Falls back to a fresh load in read-only / test mode.
    The orchestrator should expose _plugin_registry after its first job run
    or on initialisation.
    """
    orch = getattr(ctx, "orchestrator", None)
    if orch and getattr(orch, "_plugin_registry", None):
        return orch._plugin_registry
    from core.infra.registry import PluginRegistry
    reg = PluginRegistry()
    reg.load()
    return reg


async def _handle_list(ctx, params):
    from core.infra.tool_resolver import ToolResolver
    pr       = _get_plugin_registry(ctx)
    resolver = ToolResolver()
    category = params.get("category")
    ctx.write(f"  {'NAME':<22} {'ECOSYSTEM':<12} STATUS")
    ctx.write(f"  {'─'*22} {'─'*12} {'─'*12}")
    for cls in pr.all():
        if category and getattr(cls, "category", None) != category:
            continue
        tool = getattr(cls, "tool_name", cls.name)
        eco  = getattr(cls, "ecosystem",  "python")
        try:
            await resolver.resolve(tool, eco)
            status = "installed"
        except Exception:
            status = "not found"
        ctx.write(f"  {cls.name:<22} {eco:<12} {status}")


async def _handle_enable(ctx, params):
    if not ctx.active_project:
        ctx.write_error("No active project.")
        return
    await ctx.settings_manager.patch_project_settings(
        ctx.active_project.id, {"scanners": {params["name"]: True}}
    )
    ctx.write(f"Scanner '{params['name']}' enabled.")


async def _handle_disable(ctx, params):
    if not ctx.active_project:
        ctx.write_error("No active project.")
        return
    await ctx.settings_manager.patch_project_settings(
        ctx.active_project.id, {"scanners": {params["name"]: False}}
    )
    ctx.write(f"Scanner '{params['name']}' disabled.")


async def _handle_install(ctx, params):
    name = params["name"]
    pr   = _get_plugin_registry(ctx)
    cls  = pr.get(name)
    if not cls:
        ctx.write_error(f"Scanner '{name}' not found in registry.")
        return
    eco  = getattr(cls, "ecosystem",  "python")
    tool = getattr(cls, "tool_name",  name)
    if eco == "node":
        ctx.write(f"npm install -g {tool}")
    elif eco == "binary":
        ctx.write(f"Install '{tool}' via your system package manager.")
    else:
        ctx.write(f"pip install {tool}")


async def _handle_config(ctx, params):
    if not ctx.active_project:
        ctx.write_error("No active project.")
        return
    import json
    name       = params["name"]
    strictness = params.get("strictness")
    if strictness:
        await ctx.settings_manager.patch_project_settings(
            ctx.active_project.id,
            {"scanner_configs": {name: {"strictness": strictness}}}
        )
        ctx.write(f"Updated '{name}' scanner config.")
    else:
        cfg = ctx.active_project.settings.scanner_configs.get(name, {})
        ctx.write(json.dumps(cfg, indent=2))
