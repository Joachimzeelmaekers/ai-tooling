#!/usr/bin/env python3
"""
Multi-provider Token Report Generator.
Collects usage from Claude Code, OpenCode (and extensible to Codex, etc.),
aggregates by model/project/time, and generates a self-contained HTML report.
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

from providers.base import ProviderResult
from providers import opencode, claude, cursor
from pricing import estimate_cost
from report import build_html

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(TOOL_DIR, "output")
DATA_DIR = os.path.join(TOOL_DIR, "data")

# Register providers here — add new ones as simple imports
PROVIDERS = [
    claude.load,
    opencode.load,
    cursor.load,
]


def fmt_tokens(n: int) -> str:
    return f"{n:,}"


def aggregate(results: list[ProviderResult]) -> dict:
    """Build all aggregated views from normalized provider results."""

    model_stats = defaultdict(lambda: {
        "messages": 0,
        "input": 0, "output": 0, "reasoning": 0,
        "cache_read": 0, "cache_write": 0,
        "cost_logged": 0.0, "cost_estimated": 0.0,
        "provider": "",
    })

    hourly = defaultdict(lambda: defaultdict(lambda: {"input": 0, "output": 0}))

    project_stats = defaultdict(lambda: defaultdict(lambda: {
        "messages": 0, "input": 0, "output": 0,
    }))

    total_messages = 0
    total_sessions = 0

    now = datetime.now(timezone.utc)
    current_month = now.strftime("%Y-%m")

    month_stats = defaultdict(lambda: {
        "messages": 0,
        "input": 0, "output": 0, "reasoning": 0,
        "cache_read": 0, "cache_write": 0,
        "cost_logged": 0.0, "cost_estimated": 0.0,
    })

    # Per-provider totals for the summary
    provider_totals = defaultdict(lambda: {
        "messages": 0, "sessions": 0,
        "input": 0, "output": 0,
        "cost_estimated": 0.0,
    })

    for result in results:
        total_sessions += result.sessions
        provider_totals[result.name]["sessions"] += result.sessions

        for msg in result.messages:
            # Model key: use just the model name (provider tracked separately)
            model_key = msg.model

            ms = model_stats[model_key]
            ms["messages"] += 1
            ms["input"] += msg.input_tokens
            ms["output"] += msg.output_tokens
            ms["reasoning"] += msg.reasoning_tokens
            ms["cache_read"] += msg.cache_read_tokens
            ms["cache_write"] += msg.cache_write_tokens
            ms["cost_logged"] += msg.cost
            ms["provider"] = msg.provider

            # Hourly bucket
            if msg.timestamp_ms:
                dt = datetime.fromtimestamp(msg.timestamp_ms / 1000, tz=timezone.utc)
                hour_key = dt.strftime("%Y-%m-%dT%H")
                hourly[hour_key][model_key]["input"] += msg.input_tokens
                hourly[hour_key][model_key]["output"] += msg.output_tokens

                # Current month
                if dt.strftime("%Y-%m") == current_month:
                    mm = month_stats[model_key]
                    mm["messages"] += 1
                    mm["input"] += msg.input_tokens
                    mm["output"] += msg.output_tokens
                    mm["reasoning"] += msg.reasoning_tokens
                    mm["cache_read"] += msg.cache_read_tokens
                    mm["cache_write"] += msg.cache_write_tokens
                    mm["cost_logged"] += msg.cost

            # Project bucket
            project = msg.project or "unknown"
            project_stats[project][model_key]["messages"] += 1
            project_stats[project][model_key]["input"] += msg.input_tokens
            project_stats[project][model_key]["output"] += msg.output_tokens

            total_messages += 1

            # Provider totals
            pt = provider_totals[msg.provider]
            pt["messages"] += 1
            pt["input"] += msg.input_tokens
            pt["output"] += msg.output_tokens

    # Compute estimated costs
    for model_key, ms in model_stats.items():
        ms["cost_estimated"] = estimate_cost(
            model_key, ms["input"], ms["output"], ms["cache_read"], ms["cache_write"]
        )

    month_cost_estimated = 0.0
    for model_key, mm in month_stats.items():
        mm["cost_estimated"] = estimate_cost(
            model_key, mm["input"], mm["output"], mm["cache_read"], mm["cache_write"]
        )
        month_cost_estimated += mm["cost_estimated"]

    for pname, pt in provider_totals.items():
        pt["cost_estimated"] = sum(
            ms["cost_estimated"] for mk, ms in model_stats.items()
            if ms["provider"] == pname
        )

    return {
        "model_stats": dict(model_stats),
        "hourly": {k: dict(v) for k, v in hourly.items()},
        "project_stats": {k: dict(v) for k, v in project_stats.items()},
        "provider_totals": dict(provider_totals),
        "total_messages": total_messages,
        "total_sessions": total_sessions,
        "month_cost_estimated": month_cost_estimated,
        "current_month": current_month,
    }


def snapshot_data(results: list[ProviderResult]):
    """Save a timestamped snapshot of all provider data for historical tracing."""
    os.makedirs(DATA_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d")
    snapshot_file = os.path.join(DATA_DIR, f"snapshot_{ts}.json")

    snapshot = {}
    for result in results:
        snapshot[result.name] = {
            "source": result.source,
            "sessions": result.sessions,
            "message_count": len(result.messages),
            "models": {},
        }
        for msg in result.messages:
            m = snapshot[result.name]["models"].setdefault(msg.model, {
                "messages": 0, "input": 0, "output": 0,
                "cache_read": 0, "cache_write": 0,
            })
            m["messages"] += 1
            m["input"] += msg.input_tokens
            m["output"] += msg.output_tokens
            m["cache_read"] += msg.cache_read_tokens
            m["cache_write"] += msg.cache_write_tokens

    with open(snapshot_file, "w") as f:
        json.dump(snapshot, f, indent=2)
    print(f"  Data snapshot: {snapshot_file}")


def main():
    os.makedirs(REPORTS_DIR, exist_ok=True)

    print("Loading providers...")
    results = []
    for load_fn in PROVIDERS:
        result = load_fn()
        print(f"  {result.name}: {len(result.messages)} messages, {result.sessions} sessions ({result.source})")
        results.append(result)

    all_messages = sum(len(r.messages) for r in results)
    if not all_messages:
        print("No messages found from any provider.")
        sys.exit(1)

    print(f"\nTotal: {all_messages} messages across {len(results)} providers")

    snapshot_data(results)

    print("Aggregating...")
    data = aggregate(results)

    print("Generating HTML...")
    html = build_html(data)

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_file = os.path.join(REPORTS_DIR, f"report_{ts}.html")
    latest = os.path.join(REPORTS_DIR, "latest.html")

    with open(out_file, "w") as f:
        f.write(html)
    with open(latest, "w") as f:
        f.write(html)

    print(f"\nReport saved:")
    print(f"  {out_file}")
    print(f"  {latest}")
    print(f"\nOpen with:  open {latest}")

    # Summary
    ms = data["model_stats"]
    total_in = sum(v["input"] for v in ms.values())
    total_out = sum(v["output"] for v in ms.values())
    print(f"\nSummary:")
    print(f"  Sessions : {data['total_sessions']:,}")
    print(f"  Messages : {data['total_messages']:,}")
    print(f"  Input    : {total_in:,} tokens")
    print(f"  Output   : {total_out:,} tokens")

    for pname, pt in sorted(data["provider_totals"].items()):
        print(f"\n  [{pname}]")
        print(f"    Messages: {pt['messages']:,}  Sessions: {pt['sessions']:,}")
        print(f"    Input: {pt['input']:,}  Output: {pt['output']:,}")
        print(f"    Est. Cost: ${pt['cost_estimated']:.2f}")

    print()
    for key, v in sorted(ms.items(), key=lambda x: x[1]["input"] + x[1]["output"], reverse=True):
        print(f"  {key:<40}  {v['input']+v['output']:>12,} tokens  ({v['messages']} msgs)  [{v['provider']}]")


if __name__ == "__main__":
    main()
