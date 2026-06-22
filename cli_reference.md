# Nexus Audit CLI Reference

This document lists all available commands in the system, including the newly added extensions.

## `ai` commands

### `ai:recommend`
- **Description**: Get an AI-generated fix recommendation for a finding.
- **Usage**: `ai:recommend <finding_id>`

### `ai:status`
- **Description**: Show AI module availability.
- **Usage**: `ai:status`

### `ai:test`
- **Description**: Run a connectivity test against the AI backend.
- **Usage**: `ai:test`

## `audit` commands

### `audit:cancel`
- **Description**: Cancel the currently running audit job and wait for it to stop.
- **Usage**: `audit:cancel`

### `audit:diff`
- **Description**: Show the structural diff between two audit runs.
- **Usage**: `audit:diff [--run-a RUN_ID] [--run-b RUN_ID]`
- **Aliases**: diff

### `audit:export`
- **Description**: Export audit findings in SARIF, JSON, or CSV format.
- **Usage**: `audit:export [--format sarif|json|csv] [--since Nd] [--output PATH]`
- **Aliases**: export

### `audit:history`
- **Description**: List recent audit runs. Add --all to include failed/empty jobs.
- **Usage**: `audit:history [--limit N] [--all]`

### `audit:rebuild-index`
- **Description**: Rebuild the SQLite audit index from all job summaries.
- **Usage**: `audit:rebuild-index`

### `audit:run`
- **Description**: Start an audit job on the active project.
- **Usage**: `audit:run [--scanner NAME] [--fast] [--force] [--follow]`

### `audit:status`
- **Description**: Show the state of the current or last audit job.
- **Usage**: `audit:status`

### `audit:trend`
- **Description**: Show score trend across recent audit runs.
- **Usage**: `audit:trend [--last N] [--branch BRANCH]`
- **Aliases**: trend

## `config` commands

### `config:export`
- **Description**: Export the project config as JSON to stdout or a file.
- **Usage**: `config:export [--path PATH]`

### `config:get`
- **Description**: Read a dot-separated config key from the active project.
- **Usage**: `config:get <key>`

### `config:set`
- **Description**: Set a dot-separated config key to a value.
- **Usage**: `config:set <key> <value>`

### `config:show`
- **Description**: Display the full config or a named section.
- **Usage**: `config:show [--section NAME]`

## `fix` commands

### `fix:list`
- **Description**: List findings in the fix queue.
- **Usage**: `fix:list [--status STATUS] [--limit N]`

### `fix:mark`
- **Description**: Update the status of a finding.
- **Usage**: `fix:mark <finding_id> <status>`

### `fix:note`
- **Description**: Append a note to a finding.
- **Usage**: `fix:note <finding_id> <text>`

### `fix:queue`
- **Description**: Show the ranked fix queue — findings ordered by severity × age × recurrence.
- **Usage**: `fix:queue [--severity LEVEL] [--limit N]`
- **Aliases**: queue

### `fix:show`
- **Description**: Show full detail for one finding.
- **Usage**: `fix:show <finding_id>`

## `general` commands

### `exit`
- **Description**: Close the Nexus CLI session.
- **Usage**: `exit`
- **Aliases**: quit

## `log` commands

### `log:stream`
- **Description**: Stream live log events from the audit engine.
- **Usage**: `log:stream [--follow] [--all]`

## `mcp` commands

### `mcp:config`
- **Description**: Write the agent host config entry for Claude Desktop / Cursor.
- **Usage**: `mcp:config`

### `mcp:status`
- **Description**: Check if the MCP server configuration is present.
- **Usage**: `mcp:status`

## `project` commands

### `project:clear`
- **Description**: Delete ALL registered projects (requires --force).
- **Usage**: `project:clear [--force]`

### `project:delete`
- **Description**: Delete a registered project. Accepts full UUID or 8-char prefix.
- **Usage**: `project:delete <project_id>`

### `project:info`
- **Description**: Show details for a project. Accepts full UUID or 8-char prefix.
- **Usage**: `project:info [project_id]`

### `project:list`
- **Description**: List all registered projects.
- **Usage**: `project:list`

### `project:register`
- **Description**: Register a local path as an auditable project.
- **Usage**: `project:register --path PATH [--name NAME]`

## `report` commands

### `report:generate`
- **Description**: Generate a report from the latest (or a specified) audit run.
- **Usage**: `report:generate [--format md|json] [--output PATH] [--job JOB_ID]`

### `report:history`
- **Description**: List previously generated reports for the active project.
- **Usage**: `report:history [--limit N]`

## `scanner` commands

### `scanner:config`
- **Description**: View or update a scanner's configuration for the active project.
- **Usage**: `scanner:config <name> [--strictness LEVEL]`

### `scanner:disable`
- **Description**: Disable one or more scanners for the active project.
- **Usage**: `scanner:disable <name> [name ...] | --all`

### `scanner:enable`
- **Description**: Enable one or more scanners for the active project.
- **Usage**: `scanner:enable <name> [name ...] | --all | --installed`

### `scanner:install`
- **Description**: Print the install command for a scanner's external tool.
- **Usage**: `scanner:install <name>`

### `scanner:list`
- **Description**: List all scanners — shows tool install status and project enabled state.
- **Usage**: `scanner:list [--category NAME] [--enabled] [--installed]`

## `system` commands

### `system:clear`
- **Description**: Clear the output buffer.
- **Usage**: `system:clear`

### `system:help`
- **Description**: List all commands or show help for a specific command.
- **Usage**: `system:help [command]`

### `system:status`
- **Description**: Show workspace and session status.
- **Usage**: `system:status`

### `system:version`
- **Description**: Print the installed package version.
- **Usage**: `system:version`

## `workspace` commands

### `workspace:active`
- **Description**: Set the active project by ID or 8-char prefix.
- **Usage**: `workspace:active <project_id>`

### `workspace:status`
- **Description**: Show registered project count and active project.
- **Usage**: `workspace:status`

