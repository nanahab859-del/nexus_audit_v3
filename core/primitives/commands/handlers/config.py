import ast
import json
from core.primitives.commands.context import READONLY, OPERATOR
from core.primitives.models import to_dict


def register(registry) -> None:
    from core.primitives.commands.registry import Command
    from core.primitives.commands.parser import CommandParser

    registry.register(Command(
        name="config:get",
        description="Read a dot-separated config key from the active project.",
        usage="config:get <key>",
        handler=_handle_get,
        required_privilege=READONLY,
        parser=CommandParser("config:get").add_argument("key"),
    ))

    registry.register(Command(
        name="config:set",
        description="Set a dot-separated config key to a value.",
        usage="config:set <key> <value>",
        handler=_handle_set,
        required_privilege=OPERATOR,
        parser=(
            CommandParser("config:set")
            .add_argument("key")
            .add_argument("value")
        ),
    ))

    registry.register(Command(
        name="config:show",
        description="Display the full config or a named section.",
        usage="config:show [--section NAME]",
        handler=_handle_show,
        required_privilege=READONLY,
        parser=CommandParser("config:show").add_argument("--section", default=None),
    ))

    registry.register(Command(
        name="config:export",
        description="Export the project config as JSON to stdout or a file.",
        usage="config:export [--path PATH]",
        handler=_handle_export,
        required_privilege=READONLY,
        parser=CommandParser("config:export").add_argument("--path", default=None),
    ))


def _get_nested(obj, keys):
    for k in keys:
        if isinstance(obj, dict):
            obj = obj.get(k)
        elif hasattr(obj, k):
            obj = getattr(obj, k)
        else:
            return None
    return obj


def _coerce_value(raw: str):
    """
    Convert a CLI string argument to the most appropriate Python type.

    Uses ast.literal_eval which correctly handles:
      "true"   -> True        (case-insensitive before eval)
      "false"  -> False
      "75.5"   -> 75.5        (float)
      "-1"     -> -1          (negative int)
      "42"     -> 42          (int)
      "[1,2]"  -> [1, 2]      (list)

    Falls back to raw string for plain words like "myproject".
    This replaces the broken str.isdigit() pattern in the old commands.py.
    """
    # Normalise boolean strings before literal_eval
    normalised = raw.strip()
    if normalised.lower() == "true":
        return True
    if normalised.lower() == "false":
        return False
    try:
        return ast.literal_eval(normalised)
    except (ValueError, SyntaxError):
        return raw   # keep as string


async def _handle_get(ctx, params):
    if not ctx.active_project:
        ctx.write_error("No active project.")
        return
    keys = params["key"].split(".")
    val  = _get_nested(to_dict(ctx.active_project.settings), keys)
    ctx.write(f"{params['key']}: {val}")


async def _handle_set(ctx, params):
    if not ctx.active_project:
        ctx.write_error("No active project.")
        return
    key   = params["key"]
    value = _coerce_value(params["value"])
    keys  = key.split(".")
    # Build nested patch dict: "a.b.c" -> {"a": {"b": {"c": value}}}
    patch: dict = {}
    node = patch
    for k in keys[:-1]:
        node[k] = {}
        node = node[k]
    node[keys[-1]] = value
    try:
        await ctx.settings_manager.patch_project_settings(ctx.active_project.id, patch)
        ctx.write(f"Set {key} = {value!r}")
    except Exception as e:
        ctx.write_error(f"Failed to set '{key}': {e}")


async def _handle_show(ctx, params):
    if not ctx.active_project:
        ctx.write_error("No active project.")
        return
    section = params.get("section")
    data    = to_dict(ctx.active_project.settings)
    if section:
        data = _get_nested(data, section.split("."))
    ctx.write_json(data)


async def _handle_export(ctx, params):
    if not ctx.active_project:
        ctx.write_error("No active project.")
        return
    config = to_dict(await ctx.settings_manager.export_project_config(ctx.active_project.id))
    path   = params.get("path")
    if path:
        import pathlib
        import asyncio
        content = json.dumps(config, indent=2, default=str)
        await asyncio.to_thread(pathlib.Path(path).write_text, content)
        ctx.write(f"Exported to {path}")
    else:
        ctx.write_json(config)
