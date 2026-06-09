# Nexus Audit V3 — Settings Reference

This document describes every field in the five settings tabs and the backend
data model they map to.

---

## Project Tab

### Project Identity & Metadata

| Field            | Settings Key      | Type       | Description                                        |
|------------------|-------------------|------------|----------------------------------------------------|
| Project Name     | `project_name`    | `str`      | Display name shown in reports and the About tab.   |
| Project Version  | `project_version` | `str`      | Semantic version of the codebase being audited.    |
| Primary Stack    | `primary_stack`   | `str`      | Main language/framework. Drives scanner defaults.  |

Populated from `/api/capabilities` → `stacks[]`. No hardcoding.

---

### Repository & Codebase Configuration

| Field            | Settings Key      | Type         | Description                                       |
|------------------|-------------------|--------------|---------------------------------------------------|
| Project Path     | `project_path`    | `str`        | Absolute path on the server to the codebase root. |
| Inclusions       | `inclusions`      | `list[str]`  | Glob patterns for files/dirs to always include.   |
| Exclusions       | `exclusions`      | `list[str]`  | Glob patterns for files/dirs to always skip.      |

---

### Output & Reports

| Field              | Settings Key        | Type       | Description                                      |
|--------------------|---------------------|------------|--------------------------------------------------|
| Output Format      | `output_format`     | `str`      | JSON, HTML, PDF, or Markdown.                    |
| Report Output Dir  | `report_output_dir` | `str`      | Directory where report files are written.        |
| Webhook URL        | `webhook_url`       | `str`      | HTTP POST target for audit-complete notifications.|

---

### Extensions

| Field               | Settings Key         | Type         | Description                                    |
|---------------------|----------------------|--------------|------------------------------------------------|
| Enabled Extensions  | `enabled_extensions` | `list[str]`  | Extra file extensions to include in the scan.  |

---

## Scanners Tab

The scanner list is **fully dynamic** — it comes from `GET /api/scanners`, which
reads the live `plugins/` directory. Nothing is hardcoded.

### Per-scanner settings (stored under `scanner_configs[scanner_name]`)

| Field          | Key              | Type         | Description                                            |
|----------------|------------------|--------------|--------------------------------------------------------|
| Enabled        | `scanners[name]` | `bool`       | Whether this scanner runs on each audit.               |
| Strictness     | `strictness`     | `str`        | "Low", "Medium", or "High". Controls threshold/severity.|
| Exclude Paths  | `exclude_paths`  | `list[str]`  | Comma-separated paths this scanner skips.              |
| Skip Checks    | `skip_checks`    | `list[str]`  | Individual check IDs to suppress.                      |

### Install button

Calls `POST /api/scanners/install { "name": "<scanner>" }`. Streams pip output
in real time. The badge updates to **Installed** automatically.  
**No restart required.**

### Refresh button

Calls `POST /api/registry/reload`. Re-scans `plugins/` for new `.py` files.
New scanners appear immediately without a server restart.

### Add Custom Plugin

Calls `POST /api/scanners/custom`. Stores the registration in
`settings.json → ui.custom_scanners`. See [PLUGINS.md](PLUGINS.md) Case 3.

### View Raw YAML Snippet

Opens a modal showing the YAML block for this scanner's current configuration.
You can copy it and paste it into `{project_path}/audit_config.yaml` to
persist scanner settings under version control.

---

## AI Tab

| Field        | Settings Key  | Type    | Description                                           |
|--------------|---------------|---------|-------------------------------------------------------|
| AI Enabled   | `ai_enabled`  | `bool`  | Whether AI analysis runs after the scanner pass.      |
| Provider     | `ai_provider` | `str`   | `"claude"` or `"openai"`.                             |
| Model        | `ai_model`    | `str`   | Model ID, e.g. `"claude-opus-4-7"`.                  |
| API Key      | `api_key`     | `str`   | Stored encrypted (Fernet) on disk. Never sent in GET. |

> **Security:** The API key is encrypted using AES-128-CBC (Fernet) before
> being written to `settings.json`. The encryption key is stored in
> `.nexus_secret` (600 permissions, gitignored). `GET /api/settings` always
> returns `"***"` for this field.

---

## Rules Tab

| Field              | Settings Key        | Type   | Description                                           |
|--------------------|---------------------|--------|-------------------------------------------------------|
| Custom Rules YAML  | `custom_rules_yaml` | `str`  | Inline YAML with custom rule definitions.             |

### Validate button

Calls `POST /api/config/validate`. Returns a list of validation errors or
`{ "valid": true }`.

### View Full YAML button

Opens a new browser tab showing the complete merged configuration
(settings.json + audit_config.yaml override), formatted as YAML.

---

## About Tab

| Field   | Source             | Description                                             |
|---------|--------------------|---------------------------------------------------------|
| Version | `/api/capabilities`| Application version. Read from `pyproject.toml` or     |
|         |                    | `importlib.metadata` at server startup. Dynamic.        |
| Server  | static             | Bind address of the aiohttp server (127.0.0.1:8421).   |
| Project | `project_path`     | Current project root from settings.                     |
| License | static             | MIT                                                     |

---

## Settings Persistence

Settings are stored in `settings.json` in the project root.

The file is written atomically (temp-file + rename) to prevent corruption.
Reads and writes are guarded by an `asyncio.Lock` to prevent race conditions.

### Overriding settings per-project

Create `{project_path}/audit_config.yaml`. Keys in this file **win** over
`settings.json`. This allows per-project scanner profiles without touching
the global config.

Example:

```yaml
scanners:
  bandit:
    enabled: true
    strictness: High
    exclude_paths:
      - /tests
      - /migrations
  vulture:
    enabled: false
```

---

## API Endpoints Summary

| Method | Path                    | Description                                    |
|--------|-------------------------|------------------------------------------------|
| GET    | `/api/settings`         | Returns settings (api_key redacted).           |
| POST   | `/api/settings`         | Saves settings (api_key encrypted).            |
| GET    | `/api/config`           | Returns merged config (settings + YAML).       |
| GET    | `/api/config/yaml`      | Returns merged config as plain YAML text.      |
| POST   | `/api/config/validate`  | Validates a config dict, returns error list.   |
| GET    | `/api/scanners`         | Dynamic scanner list from plugins/ directory.  |
| POST   | `/api/registry/reload`  | Re-scans plugins/ without server restart.      |
| GET    | `/api/scanners/status`  | Tool install status for all known scanners.    |
| POST   | `/api/scanners/install` | pip-install a scanner, streams SSE progress.   |
| POST   | `/api/scanners/custom`  | Register a custom script as a scanner.         |
| GET    | `/api/capabilities`     | Returns stacks, formats, categories (dynamic). |
| GET    | `/api/status`           | Returns engine state and app version.          |
