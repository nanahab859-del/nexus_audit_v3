from core.primitives.commands.context import READONLY, OPERATOR, ADMIN


def register(registry) -> None:
    from core.primitives.commands.registry import Command
    from core.primitives.commands.parser import CommandParser

    registry.register(Command(
        name="scanner:list",
        description="List all scanners — shows tool install status and project enabled state.",
        usage="scanner:list [--category NAME] [--enabled] [--installed]",
        handler=_handle_list,
        required_privilege=READONLY,
        parser=(
            CommandParser("scanner:list")
            .add_argument("--category",  default=None,
                          help="Filter by category (security|quality|architecture|dependency)")
            .add_argument("--enabled",   action="store_true",
                          help="Show only scanners enabled for the active project")
            .add_argument("--installed", action="store_true",
                          help="Show only scanners whose external tool is installed")
        ),
    ))

    registry.register(Command(
        name="scanner:enable",
        description="Enable one or more scanners for the active project.",
        usage="scanner:enable <name> [name ...] | --all | --installed",
        handler=_handle_enable,
        required_privilege=OPERATOR,
        parser=(
            CommandParser("scanner:enable")
            .add_argument("name", nargs="*", default=[],
                          help="Scanner name(s) to enable")
            .add_argument("--all",       action="store_true",
                          help="Enable ALL registered scanners")
            .add_argument("--installed", action="store_true",
                          help="Enable only scanners whose external tool is installed")
        ),
    ))

    registry.register(Command(
        name="scanner:disable",
        description="Disable one or more scanners for the active project.",
        usage="scanner:disable <name> [name ...] | --all",
        handler=_handle_disable,
        required_privilege=OPERATOR,
        parser=(
            CommandParser("scanner:disable")
            .add_argument("name", nargs="*", default=[],
                          help="Scanner name(s) to disable")
            .add_argument("--all", action="store_true",
                          help="Disable ALL scanners")
        ),
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


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_plugin_registry(ctx):
    """Use the orchestrator's shared registry if available, otherwise load fresh."""
    orch = getattr(ctx, "orchestrator", None)
    if orch and getattr(orch, "_plugin_registry", None):
        return orch._plugin_registry
    from core.infra.registry import PluginRegistry
    reg = PluginRegistry()
    reg.load()
    return reg


def _project_enabled_set(ctx) -> set:
    """
    Return the set of scanner names explicitly enabled for the active project.
    An empty dict means 'no project-level overrides' — all installed scanners
    run by default.
    """
    if not ctx.active_project:
        return set()
    scanners = ctx.active_project.settings.scanners  # Dict[str, bool]
    return {name for name, enabled in scanners.items() if enabled}


def _project_disabled_set(ctx) -> set:
    """Return scanner names explicitly disabled for the active project."""
    if not ctx.active_project:
        return set()
    scanners = ctx.active_project.settings.scanners
    return {name for name, enabled in scanners.items() if not enabled}


# ── Handlers ───────────────────────────────────────────────────────────────────

async def _handle_list(ctx, params) -> None:
    from core.infra.tool_resolver import ToolResolver

    pr       = _get_plugin_registry(ctx)
    resolver = ToolResolver()
    category = params.get("category")
    only_enabled   = params.get("enabled",   False)
    only_installed = params.get("installed", False)

    # Project-level scanner state
    enabled_set  = _project_enabled_set(ctx)
    disabled_set = _project_disabled_set(ctx)

    rows = []
    for cls in sorted(pr.all(), key=lambda c: c.name):
        if category and getattr(cls, "category", None) != category:
            continue

        tool = getattr(cls, "tool_name", cls.name)
        eco  = getattr(cls, "ecosystem",  "python")

        # Check external tool install status
        try:
            await resolver.resolve(tool, eco)
            tool_status = "installed"
            tool_icon   = "✓"
        except Exception:
            tool_status = "not found"
            tool_icon   = "✗"

        # Determine project-level state
        if cls.name in disabled_set:
            proj_state = "disabled"
        elif cls.name in enabled_set:
            proj_state = "enabled"
        else:
            # No explicit setting — default: enabled if tool is installed
            proj_state = "enabled" if tool_status == "installed" else "disabled"

        if only_enabled   and proj_state != "enabled":
            continue
        if only_installed and tool_status != "installed":
            continue

        rows.append((cls.name, eco, tool_icon, tool_status, proj_state))

    if not rows:
        ctx.write("No scanners match the filter.")
        return

    # Column widths
    ctx.write(f"  {'NAME':<22} {'ECOSYSTEM':<12} {'TOOL':<12} {'PROJECT'}")
    ctx.write(f"  {'─'*22} {'─'*12} {'─'*12} {'─'*10}")

    for name, eco, icon, tool_status, proj_state in rows:
        proj_col = "enabled " if proj_state == "enabled" else "disabled"
        ctx.write(f"  {name:<22} {eco:<12} {icon} {tool_status:<10} {proj_col}")

    # Summary line when a project is active
    if ctx.active_project:
        total    = len(rows)
        en_count = sum(1 for r in rows if r[4] == "enabled")
        ctx.write("")
        ctx.write(
            f"Active project: {ctx.active_project.name} — "
            f"{en_count}/{total} scanners enabled"
        )
        if not enabled_set and not disabled_set:
            ctx.write(
                "  (No explicit scanner config. Run 'scanner:enable --installed' "
                "to lock in the default selection.)"
            )


async def _handle_enable(ctx, params) -> None:
    if not ctx.active_project:
        ctx.write_error("No active project.")
        return

    enable_all       = params.get("all",       False)
    enable_installed = params.get("installed", False)
    names            = params.get("name",      [])

    if not enable_all and not enable_installed and not names:
        ctx.write_error(
            "Specify scanner name(s), --all, or --installed.\n"
            "Examples:\n"
            "  scanner:enable bandit ruff mypy\n"
            "  scanner:enable --installed\n"
            "  scanner:enable --all"
        )
        return

    pr = _get_plugin_registry(ctx)

    if enable_all or enable_installed:
        if enable_installed:
            from core.infra.tool_resolver import ToolResolver
            resolver = ToolResolver()
            targets = []
            for cls in pr.all():
                tool = getattr(cls, "tool_name", cls.name)
                eco  = getattr(cls, "ecosystem",  "python")
                try:
                    await resolver.resolve(tool, eco)
                    targets.append(cls.name)
                except Exception:
                    pass
        else:
            targets = [cls.name for cls in pr.all()]
    else:
        # Validate all names first
        known = {cls.name for cls in pr.all()}
        unknown = [n for n in names if n not in known]
        if unknown:
            ctx.write_error(
                f"Unknown scanner(s): {', '.join(unknown)}\n"
                "Run 'scanner:list' to see available scanners."
            )
            return
        targets = names

    if not targets:
        ctx.write("No scanners to enable (none installed?).")
        return

    patch = {"scanners": {name: True for name in targets}}
    await ctx.settings_manager.patch_project_settings(
        ctx.active_project.id, patch
    )

    for name in targets:
        ctx.write(f"  ✓ {name}")
    ctx.write(f"\n{len(targets)} scanner(s) enabled for '{ctx.active_project.name}'.")


async def _handle_disable(ctx, params) -> None:
    if not ctx.active_project:
        ctx.write_error("No active project.")
        return

    disable_all = params.get("all",  False)
    names       = params.get("name", [])

    if not disable_all and not names:
        ctx.write_error(
            "Specify scanner name(s) or --all.\n"
            "Examples:\n"
            "  scanner:disable djlint eslint trufflehog\n"
            "  scanner:disable --all"
        )
        return

    pr = _get_plugin_registry(ctx)

    if disable_all:
        targets = [cls.name for cls in pr.all()]
    else:
        known   = {cls.name for cls in pr.all()}
        unknown = [n for n in names if n not in known]
        if unknown:
            ctx.write_error(
                f"Unknown scanner(s): {', '.join(unknown)}\n"
                "Run 'scanner:list' to see available scanners."
            )
            return
        targets = names

    patch = {"scanners": {name: False for name in targets}}
    await ctx.settings_manager.patch_project_settings(
        ctx.active_project.id, patch
    )

    for name in targets:
        ctx.write(f"  ✗ {name}")
    ctx.write(f"\n{len(targets)} scanner(s) disabled for '{ctx.active_project.name}'.")


async def _handle_install(ctx, params) -> None:
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


async def _handle_config(ctx, params) -> None:
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
        if cfg:
            ctx.write(json.dumps(cfg, indent=2))
        else:
            ctx.write(f"No config stored for '{name}'. Default settings apply.")
