import shlex
import shutil
from dataclasses import dataclass, field
from typing import Callable, Any, Optional, Dict, List, Awaitable
from core.primitives.models import Workspace, Project
from core.primitives.settings import SettingsManager
from pathlib import Path

@dataclass
class CommandContext:
    workspace: Workspace
    settings_manager: SettingsManager
    active_project: Optional[Project] = None
    stdout_buffer: List[str] = field(default_factory=list)
    has_error: bool = False

    def write(self, text: str) -> None:
        self.stdout_buffer.append(text)

    def write_error(self, text: str) -> None:
        self.has_error = True
        self.stdout_buffer.append(f"[ERROR] {text}")

@dataclass
class Command:
    name: str
    description: str
    usage: str
    handler: Callable[[CommandContext, Dict[str, Any]], Awaitable[Any]]

class CommandRegistry:
    def __init__(self, settings_manager: SettingsManager):
        self._commands: Dict[str, Command] = {}
        self._settings_manager = settings_manager
        self._register_builtins()

    def register(self, command: Command) -> None:
        self._commands[command.name] = command

    def _register_builtins(self):
        # Workspace
        self.register(Command("workspace:status", "Outputs registered project count and active project name.", "workspace:status", self._handle_workspace_status))
        self.register(Command("workspace:active", "Sets active project.", "workspace:active <project_id>", self._handle_workspace_active))
        
        # Project
        self.register(Command("project:register", "Creates a new project.", "project:register --path=<path> --name=<name>", self._handle_project_register))
        self.register(Command("project:list", "Lists projects.", "project:list", self._handle_project_list))
        self.register(Command("project:delete", "Deletes a project.", "project:delete <project_id>", self._handle_project_delete))
        
        # Audit
        self.register(Command("audit:run", "Triggers audit.", "audit:run --scanner=<name> --force", self._handle_stub))
        self.register(Command("audit:cancel", "Cancels audit.", "audit:cancel", self._handle_stub))
        self.register(Command("audit:status", "Returns job state.", "audit:status", self._handle_stub))
        
        # Config
        self.register(Command("config:get", "Reads a setting.", "config:get <key>", self._handle_stub))
        self.register(Command("config:set", "Updates a setting.", "config:set <key> <value>", self._handle_stub))
        self.register(Command("config:show", "Displays config.", "config:show", self._handle_stub))
        
        # Fix
        self.register(Command("fix:list", "Lists fixes.", "fix:list", self._handle_stub))
        self.register(Command("fix:mark", "Marks fix status.", "fix:mark <finding_id> <status>", self._handle_stub))
        
        # Report
        self.register(Command("report:generate", "Generates report.", "report:generate --format=<fmt>", self._handle_stub))
        
        # Scanner
        self.register(Command("scanner:list", "Lists scanners.", "scanner:list", self._handle_stub))
        self.register(Command("scanner:install", "Installs/enables scanner.", "scanner:install <name>", self._handle_stub))
        
        # System
        self.register(Command("system:help", "Lists all commands.", "system:help [command]", self._handle_help))
        self.register(Command("system:version", "Outputs version.", "system:version", self._handle_version))
        self.register(Command("system:clear", "Clears buffer.", "system:clear", self._handle_stub))

    async def execute(self, input_string: str) -> CommandContext:
        workspace = await self._settings_manager.load_workspace()
        
        active_project = None
        if workspace.active_project_id:
            try:
                active_project = await self._settings_manager.get_active_project()
            except FileNotFoundError:
                active_project = None
        
        context = CommandContext(
            workspace=workspace,
            settings_manager=self._settings_manager,
            active_project=active_project
        )
        
        try:
            tokens = shlex.split(input_string)
            if not tokens:
                return context
            
            cmd_name = tokens[0]
            args = tokens[1:]
            
            if cmd_name not in self._commands:
                context.write_error(f"Unknown command: {cmd_name}")
                return context
                
            # Basic arg parsing (can be enhanced)
            cmd_args = {"args": args} 
            await self._commands[cmd_name].handler(context, cmd_args)
            
        except Exception as e:
            context.write_error(str(e))
            
        return context

    async def _handle_workspace_status(self, ctx: CommandContext, args: Dict[str, Any]):
        ctx.write(f"Registered projects: {len(ctx.workspace.projects)}")
        ctx.write(f"Active project: {ctx.active_project.name if ctx.active_project else 'None'}")

    async def _handle_workspace_active(self, ctx: CommandContext, args: Dict[str, Any]):
        if not args["args"]:
            ctx.write_error("Missing project_id")
            return
        await ctx.settings_manager.set_active_project(args["args"][0])
        ctx.write(f"Active project set to {args['args'][0]}")

    async def _handle_project_register(self, ctx: CommandContext, args: Dict[str, Any]):
        # Very simple arg parsing for demo
        path = "."
        name = "default"
        for arg in args["args"]:
            if arg.startswith("--path="): path = arg.split("=")[1]
            if arg.startswith("--name="): name = arg.split("=")[1]
        
        path_obj = Path(path).expanduser()
        await ctx.settings_manager.register_project(name, str(path_obj))
        ctx.write(f"Project '{name}' registered at {path_obj}")

    async def _handle_project_list(self, ctx: CommandContext, args: Dict[str, Any]):
        for pid, proj in ctx.workspace.projects.items():
            ctx.write(f"{pid}: {proj.name} ({proj.path})")

    async def _handle_project_delete(self, ctx: CommandContext, args: Dict[str, Any]):
        if not args["args"]:
            ctx.write_error("Missing project_id")
            return
        await ctx.settings_manager.delete_project(args["args"][0])
        ctx.write(f"Project {args['args'][0]} deleted")

    async def _handle_help(self, ctx: CommandContext, args: Dict[str, Any]):
        ctx.write("Available commands:")
        for name, cmd in self._commands.items():
            ctx.write(f"  {name:20} {cmd.description}")

    async def _handle_version(self, ctx: CommandContext, args: Dict[str, Any]):
        ctx.write("Nexus Audit V3 - version 0.1.0")

    async def _handle_stub(self, ctx: CommandContext, args: Dict[str, Any]):
        ctx.write("[INFO] Feature will be available in a future phase")
