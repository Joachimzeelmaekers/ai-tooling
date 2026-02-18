# opencode-token-report

Generates a self-contained HTML report of token usage from local [opencode](https://opencode.ai) session data.

## Usage

```bash
make report
open output/latest.html
```

Each run also saves `output/report_YYYY-MM-DD_HH-MM-SS.html`.

## What it reports

- Summary cards — sessions, messages, input/output/reasoning/cache tokens, estimated cost
- Tokens by model — bar chart + donut chart
- Daily usage timeline — per-model line chart
- Model table — all token types and estimated cost per model
- Project table — top 20 directories by token usage

## Pricing

All current models are free-tier or opencode-internal proxies (`cost = $0`).
Update the `PRICING` dict at the top of `main.py` if you add paid models.

## Requirements

Python 3.8+ — no third-party packages.
