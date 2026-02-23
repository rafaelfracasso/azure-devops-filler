# AGENTS.md

> Project map for AI agents. Keep this file up-to-date as the project evolves.

## Project Overview
`adf` is a Python CLI that auto-fills Azure DevOps Tasks by collecting activities from Outlook, Recurring Activities, and Azure Git, then creating Work Items via the Azure DevOps REST API.

## Tech Stack
- **Language:** Python 3.10+
- **CLI Framework:** Typer + Rich
- **HTTP Client:** httpx (async)
- **Config Validation:** Pydantic v2
- **Config Format:** YAML + `.env`

## Project Structure
```
azure-devops-filler/
├── src/azure_devops_filler/
│   ├── cli.py               # CLI entry point — Typer app, all commands (run, export, import, sources, test, stats)
│   ├── config.py            # Config loading — reads config.yaml + .env, Pydantic validation
│   ├── models.py            # Dataclasses — Activity, Task, ProcessingResult
│   ├── dedup.py             # Deduplication — hash-based, persisted to data/processed.json
│   ├── clients/
│   │   ├── azure_devops.py  # Azure DevOps client — create Work Items, fetch Git commits
│   │   └── microsoft_graph.py  # Microsoft Graph client — fetch Outlook calendar events
│   └── sources/
│       ├── base.py          # BaseSource interface — all sources must implement collect()
│       ├── outlook.py       # Outlook source — CSV file or Graph API
│       ├── recurring.py      # Recurring activities source — template-based
│       └── git.py           # Azure Git source — commits grouped by repo/day
├── config.yaml              # Project/area config (teams, work item area paths, source settings)
├── .env                     # Secrets — AZURE_DEVOPS_PAT, Graph credentials (not committed)
├── .env.example             # Template for .env
├── pyproject.toml           # Package metadata, dependencies, `adf` console script entry
└── data/
    ├── processed.json       # Dedup state (auto-generated, not committed)
    └── calendar.csv         # Outlook CSV export (manual, optional)
```

## Key Entry Points
| File | Purpose |
|------|---------|
| `src/azure_devops_filler/cli.py` | Main CLI — all `adf` commands |
| `src/azure_devops_filler/config.py` | Config loading and Pydantic validation |
| `src/azure_devops_filler/sources/base.py` | Interface contract for all data sources |
| `config.yaml` | User-facing configuration (projects, areas, source settings) |
| `.env` | Secrets (PAT, Graph credentials) |
| `pyproject.toml` | Package definition and dependencies |

## Documentation
| Document | Path | Description |
|----------|------|-------------|
| README | README.md | Project landing page |
| Getting Started | docs/getting-started.md | Installation, setup, first steps |
| Configuration | docs/configuration.md | config.yaml and .env variables reference |
| Sources | docs/sources.md | Outlook, Recurring Activities and Azure Git setup |
| CLI Reference | docs/cli.md | All commands with options and examples |

## AI Context Files
| File | Purpose |
|------|---------|
| AGENTS.md | This file — project structure map |
