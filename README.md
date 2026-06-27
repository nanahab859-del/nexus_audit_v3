# Nexus Audit

Nexus Audit is a powerful interactive CLI REPL designed for managing, executing, and analyzing comprehensive code security audits. It serves as a unified control center that orchestrates multiple security scanners, indexes findings locally, provides AI-driven recommendations via an embedded MCP server, and offers a complete workflow for tracking and queuing fixes.

Unlike traditional single-shot CLI tools, Nexus Audit operates as a persistent, asynchronous shell (built with `prompt-toolkit`) where background audit tasks, live event streaming, and stateful project management all occur within a single session.

## Features

- **Interactive REPL Shell:** A stateful, autocomplete-enabled interactive command line interface (`nexus`).
- **Project & Workspace Management:** Register, list, and switch between multiple audit projects (`project:register`, `workspace:active`).
- **Multi-Scanner Orchestration:** Install, configure, enable, and disable various security scanners (`scanner:install`, `scanner:enable`).
- **Audit Execution & Analytics:** Run async audits in the background, track live status, compare historical trends, and export results (`audit:run`, `audit:diff`, `audit:trend`).
- **Fix & Patch Queuing:** Interactively review vulnerabilities, add notes, and queue fixes for implementation (`fix:list`, `fix:queue`, `fix:mark`).
- **MCP & AI Integration:** Built-in Model Context Protocol (MCP) server for exposing audit data to external AI agents, plus AI recommendation commands (`mcp:config`, `ai:recommend`).
- **Live Event Logging:** Stream live system events, audit progress, and errors directly to the console (`log:stream`).
- **Local SQLite Indexing:** All project findings and histories are securely stored in a local SQLite database (`~/.nexus_audit/projects/<id>/nexus_state.db`).

## Installation (Standard Setup)

For standard single-workspace development or usage, set up your environment as follows:

```bash
# 1. Clone the repository
git clone <repository_url> nexus_audit
cd nexus_audit

# 2. Create a fresh virtual environment
python3 -m venv .venv

# 3. Activate the environment
source .venv/bin/activate

# 4. Install the tool in editable mode
pip install -e .

# 5. Start the interactive shell
nexus
```

## Git Worktree Setup (Critical Rules)

If you are a developer utilizing **Git Worktrees** to manage multiple branches concurrently, you **must** strictly adhere to the following environment rules to prevent path conflicts:

- **Each worktree needs its own `.venv` created fresh inside it.**
- **Never copy `.venv` from another worktree.** (Copying brings over hardcoded absolute paths that point to the wrong source code).
- **Always run `pip install -e .` inside each worktree after creating its `.venv`.**
- *Why?* The `.venv` directory is gitignored and is not carried over when a new worktree is created. Re-running the editable install ensures the `nexus` command correctly resolves to the local files in that specific worktree.

## Usage Examples

Once installed, simply type `nexus` to enter the interactive shell:

```bash
$ nexus
```

Inside the shell, you can manage your audit lifecycle:

```text
# Register your current directory as an audit project
nexus> project:register --path . --name my_app

# List registered projects and switch your active workspace
nexus> project:list
nexus> workspace:active <project_id>

# Run a security audit
nexus> audit:run

# Review the findings and queue fixes
nexus> fix:list
nexus> fix:queue <finding_id>

# Generate a final HTML/JSON report
nexus> report:generate
```

Type `system:help` inside the shell for a complete list of commands.

## Developer Notes & Known Fixes

**Testing the CLI:**
- **Always test using the `nexus` command**, not `python cli.py` directly. This ensures the environment wrappers and entry points behave exactly as they will for end-users.

**Recent System Fixes (Already Applied):**
- **Multi-delete support:** The `project:delete` command now seamlessly accepts multiple project IDs at once (`project:delete id1 id2 id3`).
- **Sorted output:** The `project:list` command now sorts projects logically (newest first).
- **Project Registration Guardrails:** Uniqueness checks have been added to prevent duplicate `default` projects. 
  - Registering an already-registered path seamlessly sets it as the active workspace instead of throwing an error.
  - Registering a duplicate name across different paths correctly throws a `DuplicateNameError`.
- **Test Teardown:** Fixed a state leakage issue where integration tests were leaving ghost projects in the global workspace. Tests now use `yield` fixtures with explicit `delete_project` cleanup.
