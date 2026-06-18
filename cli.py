"""
cli.py — Nexus Audit interactive REPL.

One asyncio event loop for the entire session so that:
  - Background audit tasks (asyncio.create_task) stay alive between prompts
  - EventBus pub/sub works across commands
  - log:stream --follow receives live events
  - prompt_toolkit async API (prompt_async) is used correctly

The Orchestrator is created HERE and injected into CommandRegistry and
CommandContext — it is never instantiated inside core/.
"""
from __future__ import annotations

import asyncio
import argparse
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path

import click
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter

from core.primitives.settings import SettingsManager
from core.primitives.commands import CommandRegistry, CommandContext, OPERATOR, ADMIN


def _get_version() -> str:
    try:
        return version("nexus-audit")
    except PackageNotFoundError:
        return "dev"


class NexusCLI:
    def __init__(
        self,
        registry: CommandRegistry,
        context: CommandContext,
        sm: SettingsManager,
    ):
        self.registry = registry
        self.context  = context
        self.sm       = sm

        completer   = WordCompleter([c.name for c in registry.list_all()], ignore_case=True)
        history_dir = Path.home() / ".nexus_audit"
        history_dir.mkdir(parents=True, exist_ok=True)

        self.session = PromptSession(
            history=FileHistory(str(history_dir / ".cli_history")),
            auto_suggest=AutoSuggestFromHistory(),
            completer=completer,
        )

    def run(self) -> None:
        """Synchronous entry point. The entire session runs in one event loop."""
        asyncio.run(self._run_async())

    async def _run_async(self) -> None:
        self._print_banner()

        while True:
            try:
                # prompt_async yields to the event loop while waiting for user input.
                # Background audit tasks make progress during this wait.
                line = await self.session.prompt_async("nexus> ")

                if not line.strip():
                    continue

                # Reset per-command output state
                self.context.stdout_buffer = []
                self.context.has_error     = False

                # Execute (still inside the same event loop — no new loop created)
                await self.registry.execute(line, self.context)

                # Render output — the CLI is responsible for this, not the context
                self._render(self.context)

                # Resync workspace only when a mutating command set workspace_dirty
                if self.context.workspace_dirty:
                    await self._sync_context()
                    self.context.workspace_dirty = False

                # Honour exit requested by the 'exit' command handler
                if self.context.exit_requested:
                    break

            except EOFError:
                break
            except KeyboardInterrupt:
                click.echo("\n[INTERRUPT] Use 'exit' to quit gracefully.")
                continue

    def _render(self, ctx: CommandContext) -> None:
        """Render the output buffer to the terminal. Context never calls click directly."""
        for line in ctx.stdout_buffer:
            if line.startswith("[ERROR]"):
                click.secho(line, fg="red", bold=True)
            else:
                click.echo(line)

    async def _sync_context(self) -> None:
        """Reload workspace and active project from disk. Called only after mutating commands."""
        workspace = await self.sm.load_workspace()
        self.context.workspace = workspace
        if workspace.active_project_id:
            try:
                self.context.active_project = await self.sm.load_project(
                    workspace.active_project_id
                )
            except FileNotFoundError:
                self.context.active_project = None
        else:
            self.context.active_project = None

    def _print_banner(self) -> None:
        click.secho(r"""
  _   _
 | \ | | _____  ___   _ ___
 |  \| |/ _ \ \/ / | | / __|
 | |\  |  __/>  <| |_| \__ \
 |_| \_|\___/_/\_\\__,_|___/
""", fg="green")
        click.echo(f"  Nexus Audit v{_get_version()}")
        click.echo("  Type 'system:help' for available commands.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Nexus Audit CLI")
    parser.add_argument(
        "--admin",
        action="store_true",
        help="Start with administrator privileges (no authentication — local use only)",
    )
    args = parser.parse_args()

    # ── Bootstrap: one-time loads before the persistent loop starts ────────────
    sm        = SettingsManager()
    workspace = asyncio.run(sm.load_workspace())

    active_project = None
    if workspace.active_project_id:
        try:
            active_project = asyncio.run(sm.load_project(workspace.active_project_id))
        except FileNotFoundError:
            pass

    priv_level = ADMIN if args.admin else OPERATOR

    # ── Wire up: Orchestrator created here, injected everywhere ───────────────
    # This is the ONLY place in the codebase that should instantiate Orchestrator.
    # core/ must never import or create it.
    from orchestrator import Orchestrator
    orchestrator = Orchestrator(sm)

    context = CommandContext(
        workspace=workspace,
        settings_manager=sm,
        active_project=active_project,
        privilege_level=priv_level,
        orchestrator=orchestrator,
    )

    registry = CommandRegistry(sm, orchestrator=orchestrator)

    NexusCLI(registry, context, sm).run()


if __name__ == "__main__":
    main()
