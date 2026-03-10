# AI Tooling

Personal AI development tools. Token usage reporting across providers, prompt analysis, and more.

## Quick Start

```bash
make ai-report
```

Generates a self-contained HTML report with token usage across all providers and opens it in your browser.

## Token Report

Reads local usage data from:

| Provider | Source |
|----------|--------|
| Claude Code | `~/.claude/stats-cache.json` + session JSONL |
| OpenCode | `~/.local/share/opencode/opencode.db` |
| Cursor | `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb` |
| Codex | `~/.codex/sessions/**/*.jsonl` |

Features:
- Per-model token breakdown with estimated costs
- Monthly cost tracking
- Timeline charts (hourly/daily)
- Per-project breakdown
- Client-side provider filtering
- Data caching (only fetches new data on subsequent runs)

### Requirements

- Python 3.10+
- No pip dependencies (stdlib only)

## Other Tools

```bash
make prompt-analysis   # Analyze Claude/OpenCode session prompts
make ai-serve          # Live-reload report server on localhost:9999
make clean             # Clean all output directories
```
