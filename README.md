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

# 2. Create a fresh virtual environment (ALWAYS use python3)
python3 -m venv .venv

# 3. Activate the environment
source .venv/bin/activate

# 4. Install the tool and all runtime dependencies
pip install -e .
```

### Installing Scanners

Nexus Audit supports scanners across four categories. Some are installed via `pip`, others via system package managers. Install only what you need.

#### Quick Reference — Pip-Managed Scanners

You can install scanners by category, or install all of them at once:

```bash
# Install by category (pick the ones you need):
pip install -e .[quality]       # ruff, mypy, djlint, pylint, vulture, radon
pip install -e .[security]      # bandit, semgrep
pip install -e .[architecture]  # lizard
pip install -e .[dependency]    # pip-audit, pip-licenses

# Install ALL pip-managed scanners in one command:
pip install -e .[scanners]

# Developers — install everything (scanners + test tools):
pip install -e .[dev,scanners]
```

#### System-Level Scanners (Cannot be installed via pip)

> **These two scanners require separate installation outside of pip.** Without them, those specific scanners will simply report as unavailable — the rest of the tool works fine.

**TruffleHog** (Security — Git secret scanning)
TruffleHog is a Go binary. Install it with:
```bash
# Linux (via official install script):
curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh | sh -s -- -b /usr/local/bin

# macOS (via Homebrew):
brew install trufflehog

# Verify installation:
trufflehog --version
```

**ESLint** (Quality — JavaScript/TypeScript linting)
ESLint is an NPM package and must be installed via Node.js. It should be installed **inside the project you are auditing**, not globally:
```bash
# Inside the JavaScript project you want to audit:
npm install --save-dev eslint

# Or, to install globally on your system:
npm install -g eslint

# Verify installation:
eslint --version
```

#### Built-in Scanners (No installation required)

These two scanners are implemented as pure Python inside Nexus Audit and require no external tools:

- **SecretScrub** — Scans all files for hardcoded secrets, AWS keys, GitHub tokens, and private key headers using regex + entropy analysis.
- **Django Settings** — Audits Django `settings.py` files for insecure production configurations (`DEBUG=True`, `ALLOWED_HOSTS=*`, etc.).

#### Complete Scanner Reference

| Scanner | Category | Install Method | Command |
|---|---|---|---|
| `ruff` | quality | pip | `pip install ruff` |
| `mypy` | quality | pip | `pip install mypy` |
| `pylint` | quality | pip | `pip install pylint` |
| `djlint` | quality | pip | `pip install djlint` |
| `vulture` | quality | pip | `pip install vulture` |
| `radon` | quality | pip | `pip install radon` |
| `bandit` | security | pip | `pip install bandit` |
| `semgrep` | security | pip | `pip install semgrep` |
| `trufflehog` | security | **system binary** | See TruffleHog section above |
| `lizard` | architecture | pip | `pip install lizard` |
| `pip-audit` | dependency | pip | `pip install pip-audit` |
| `pip-licenses` | dependency | pip | `pip install pip-licenses` |
| `eslint` | quality | **npm** | See ESLint section above |
| `secretscrub` | security | **built-in** | No install needed |
| `django_settings` | security | **built-in** | No install needed |

```bash
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
