# AI Tooling

Personal engineering tools. Usage reporting across AI providers, GitHub PR/review statistics, prompt analysis, and more.

## Quick Start

```bash
make engineering-report
```

Generates a self-contained HTML engineering dashboard and opens it in your browser.

## Engineering Report

Reads local usage data from:

| Provider | Source |
|----------|--------|
| Claude Code | `~/.claude/stats-cache.json` + session JSONL |
| OpenCode | `~/.local/share/opencode/opencode.db` |
| Cursor | `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb` |
| Codex | `~/.codex/sessions/**/*.jsonl` |
| GitHub | GraphQL API (PRs authored + reviews given) |

Features:
- Per-model token breakdown with estimated costs
- Monthly cost tracking
- Timeline charts (hourly/daily)
- Per-project breakdown
- Client-side provider filtering
- GitHub PR statistics (total, per-org, per-repo, size percentiles)
- Review statistics (approved/commented/changes requested)
- Workday vs weekend PR averages
- Data caching (only fetches new data on subsequent runs)

### Requirements

- Python 3.10+
- `gh` CLI (authenticated) for GitHub stats
- No pip dependencies (stdlib only)

## Other Tools

```bash
make prompt-analysis      # Analyze Claude/OpenCode session prompts
make engineering-serve    # Live-reload report server on localhost:9999
make clean               # Clean all output directories
```
