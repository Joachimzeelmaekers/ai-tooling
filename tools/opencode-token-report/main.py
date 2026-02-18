#!/usr/bin/env python3
"""
opencode Token Report Generator
Reads from ~/.local/share/opencode/opencode.db (SQLite) with fallback to
legacy JSON files, groups assistant messages by model, and generates a
self-contained HTML report.
"""

import json
import os
import glob
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OPENCODE_DIR = os.path.expanduser("~/.local/share/opencode")
DB_PATH = os.path.join(OPENCODE_DIR, "opencode.db")
STORAGE_DIR = os.path.join(OPENCODE_DIR, "storage")
REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# Known pricing per 1M tokens (USD).
# Format: { "providerID/modelID": (input_price, output_price, cache_read_price) }
PRICING = {
    # Free-tier models
    "opencode/kimi-k2.5-free":  (0.0, 0.0, 0.0),
    "opencode/glm-4.7-free":    (0.0, 0.0, 0.0),
    "opencode/glm-5-free":      (0.0, 0.0, 0.0),
    # opencode internal models - unknown; placeholder $0
    "opencode/big-pickle":      (0.0, 0.0, 0.0),
    # gpt-5.x-codex: $1.75/M input, $14.00/M output, $0.175/M cached input
    "openai/gpt-5.2-codex":     (1.75, 14.00, 0.175),
    "openai/gpt-5.3-codex":     (1.75, 14.00, 0.175),
}


def fmt_tokens(n: int) -> str:
    """Format token count with commas."""
    return f"{n:,}"


def fmt_compact(n: int) -> str:
    """Format number compactly: 1000 -> 1K, 20000000 -> 20M."""
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def fmt_cost(c: float) -> str:
    return f"${c:.2f}"


def load_sessions() -> dict:
    """Load session metadata keyed by session ID."""
    sessions = {}
    # Try SQLite first
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
            for row in conn.execute("SELECT id, directory, title FROM session"):
                sessions[row[0]] = {"id": row[0], "directory": row[1], "title": row[2]}
            conn.close()
            return sessions
        except Exception:
            pass
    # Fallback to JSON files
    for f in glob.glob(f"{STORAGE_DIR}/session/**/*.json", recursive=True):
        try:
            d = json.load(open(f))
            sessions[d["id"]] = d
        except Exception:
            pass
    return sessions


def load_messages() -> list:
    """Load all assistant messages that have token data."""
    messages = []
    source = "json"
    # Try SQLite first
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
            for row in conn.execute("SELECT session_id, data FROM message"):
                d = json.loads(row[1])
                d["sessionID"] = row[0]
                if d.get("role") != "assistant":
                    continue
                if "tokens" not in d:
                    continue
                messages.append(d)
            conn.close()
            source = "sqlite"
        except Exception:
            messages = []
    # Fallback to JSON files if SQLite yielded nothing
    if not messages:
        for f in glob.glob(f"{STORAGE_DIR}/message/**/*.json", recursive=True):
            try:
                d = json.load(open(f))
                if d.get("role") != "assistant":
                    continue
                if "tokens" not in d:
                    continue
                messages.append(d)
            except Exception:
                pass
        source = "json"
    return messages, source


def aggregate(messages: list, sessions: dict) -> dict:
    """Build all aggregated views needed for the report."""

    # -----------------------------------------------------------------------
    # Per-model totals
    # -----------------------------------------------------------------------
    model_stats = defaultdict(lambda: {
        "messages": 0,
        "input": 0, "output": 0, "reasoning": 0,
        "cache_read": 0, "cache_write": 0,
        "cost_logged": 0.0,
    })

    # Hourly usage  { "YYYY-MM-DDTHH": { model_key: {input,output} } }
    hourly = defaultdict(lambda: defaultdict(lambda: {"input": 0, "output": 0}))

    # Project usage { project_dir: { model_key: {input,output,messages} } }
    project_stats = defaultdict(lambda: defaultdict(lambda: {
        "messages": 0, "input": 0, "output": 0,
    }))

    total_messages = 0
    total_sessions = set()

    for msg in messages:
        model_key = f"{msg.get('providerID','unknown')}/{msg.get('modelID','unknown')}"
        t = msg["tokens"]
        inp = t.get("input", 0)
        out = t.get("output", 0)
        rea = t.get("reasoning", 0)
        cr  = t.get("cache", {}).get("read", 0)
        cw  = t.get("cache", {}).get("write", 0)
        cost = msg.get("cost", 0.0) or 0.0

        ms = model_stats[model_key]
        ms["messages"] += 1
        ms["input"]     += inp
        ms["output"]    += out
        ms["reasoning"] += rea
        ms["cache_read"] += cr
        ms["cache_write"] += cw
        ms["cost_logged"] += cost

        # Hourly bucket
        ts_ms = msg.get("time", {}).get("created", 0)
        if ts_ms:
            dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
            hour_key = dt.strftime("%Y-%m-%dT%H")
            hourly[hour_key][model_key]["input"]  += inp
            hourly[hour_key][model_key]["output"] += out

        # Project bucket
        path = msg.get("path", {}).get("root") or ""
        if not path:
            sess = sessions.get(msg.get("sessionID", ""), {})
            path = sess.get("directory", "unknown")
        project_stats[path][model_key]["messages"] += 1
        project_stats[path][model_key]["input"]    += inp
        project_stats[path][model_key]["output"]   += out

        total_sessions.add(msg.get("sessionID", ""))
        total_messages += 1

    # -----------------------------------------------------------------------
    # Compute estimated cost per model
    # -----------------------------------------------------------------------
    for model_key, ms in model_stats.items():
        price = PRICING.get(model_key, (0.0, 0.0, 0.0))
        inp_price, out_price, cr_price = price
        ms["cost_estimated"] = (
            ms["input"]      / 1_000_000 * inp_price
            + ms["output"]   / 1_000_000 * out_price
            + ms["cache_read"] / 1_000_000 * cr_price
        )

    return {
        "model_stats": dict(model_stats),
        "hourly": {k: dict(v) for k, v in hourly.items()},
        "project_stats": {k: dict(v) for k, v in project_stats.items()},
        "total_messages": total_messages,
        "total_sessions": len(total_sessions),
    }


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

def build_html(data: dict) -> str:
    model_stats   = data["model_stats"]
    hourly_data   = data["hourly"]
    project_stats = data["project_stats"]
    total_msgs    = data["total_messages"]
    total_sess    = data["total_sessions"]

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Grand totals
    grand_input      = sum(v["input"]      for v in model_stats.values())
    grand_output     = sum(v["output"]     for v in model_stats.values())
    grand_reasoning  = sum(v["reasoning"]  for v in model_stats.values())
    grand_cache_read = sum(v["cache_read"] for v in model_stats.values())
    grand_cost_est   = sum(v["cost_estimated"] for v in model_stats.values())
    grand_cost_log   = sum(v["cost_logged"]    for v in model_stats.values())

    # Sort models by total tokens desc
    sorted_models = sorted(
        model_stats.items(),
        key=lambda x: x[1]["input"] + x[1]["output"],
        reverse=True,
    )

    # Color palette
    COLORS = ["#6366f1", "#22d3ee", "#f59e0b", "#10b981", "#ef4444", "#a78bfa"]

    model_colors = {k: COLORS[i % len(COLORS)] for i, (k, _) in enumerate(sorted_models)}

    # -----------------------------------------------------------------------
    # Model table rows
    # -----------------------------------------------------------------------
    model_rows = ""
    for i, (key, ms) in enumerate(sorted_models):
        provider, model = key.split("/", 1)
        color = model_colors[key]
        total_tok = ms["input"] + ms["output"]
        model_rows += f"""
        <tr>
          <td data-sort="{model}"><span class="model-badge" style="background:{color}20;color:{color};border-color:{color}40">{model}</span></td>
          <td class="mono" data-sort="{provider}">{provider}</td>
          <td class="mono right" data-sort="{ms['messages']}">{fmt_tokens(ms['messages'])}</td>
          <td class="mono right" data-sort="{ms['input']}">{fmt_tokens(ms['input'])}</td>
          <td class="mono right" data-sort="{ms['output']}">{fmt_tokens(ms['output'])}</td>
          <td class="mono right" data-sort="{ms['reasoning']}">{fmt_tokens(ms['reasoning'])}</td>
          <td class="mono right" data-sort="{ms['cache_read']}">{fmt_tokens(ms['cache_read'])}</td>
          <td class="mono right" data-sort="{total_tok}">{fmt_tokens(total_tok)}</td>
          <td class="mono right cost" data-sort="{ms['cost_estimated']:.6f}">{fmt_cost(ms['cost_estimated'])}</td>
        </tr>"""

    # -----------------------------------------------------------------------
    # Bar chart data (tokens by model)
    # -----------------------------------------------------------------------
    bar_labels = json.dumps([k.split("/", 1)[1] for k, _ in sorted_models])
    bar_input  = json.dumps([v["input"]  for _, v in sorted_models])
    bar_output = json.dumps([v["output"] for _, v in sorted_models])
    bar_cache  = json.dumps([v["cache_read"] for _, v in sorted_models])
    bar_colors = json.dumps([model_colors[k] for k, _ in sorted_models])

    # -----------------------------------------------------------------------
    # Timeline raw data (hourly granularity, grouped in JS)
    # -----------------------------------------------------------------------
    # Export: { "YYYY-MM-DDTHH": { "model": { "input": N, "output": N } } }
    timeline_raw = json.dumps(hourly_data)
    timeline_models = json.dumps([
        {"key": k, "name": k.split("/", 1)[1], "color": model_colors[k]}
        for k, _ in sorted_models
    ])

    # -----------------------------------------------------------------------
    # Donut chart (output token share by model)
    # -----------------------------------------------------------------------
    donut_labels = json.dumps([k.split("/", 1)[1] for k, _ in sorted_models])
    donut_data   = json.dumps([v["output"] for _, v in sorted_models])
    donut_colors = json.dumps([model_colors[k] for k, _ in sorted_models])

    # -----------------------------------------------------------------------
    # Project table rows (top 20 by tokens)
    # -----------------------------------------------------------------------
    proj_totals = []
    for path, model_map in project_stats.items():
        total_inp = sum(v["input"]  for v in model_map.values())
        total_out = sum(v["output"] for v in model_map.values())
        total_msg = sum(v["messages"] for v in model_map.values())
        proj_totals.append((path, total_inp, total_out, total_msg))
    proj_totals.sort(key=lambda x: x[1] + x[2], reverse=True)

    project_rows = ""
    for path, inp, out, msgs in proj_totals:
        dir_name = os.path.basename(path) or path
        project_rows += f"""
        <tr>
          <td class="mono path" title="{path}" data-sort="{dir_name}">{dir_name}</td>
          <td class="mono right" data-sort="{msgs}">{fmt_tokens(msgs)}</td>
          <td class="mono right" data-sort="{inp}">{fmt_tokens(inp)}</td>
          <td class="mono right" data-sort="{out}">{fmt_tokens(out)}</td>
          <td class="mono right" data-sort="{inp + out}">{fmt_tokens(inp + out)}</td>
        </tr>"""

    # -----------------------------------------------------------------------
    # HTML template
    # -----------------------------------------------------------------------
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>opencode Token Report</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
  <style>
    :root {{
      --bg: #0f1117;
      --surface: #161b22;
      --border: #21262d;
      --text: #e6edf3;
      --muted: #7d8590;
      --accent: #6366f1;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
    }}
    header {{
      background: linear-gradient(135deg, #1a1f2e 0%, #161b22 100%);
      border-bottom: 1px solid var(--border);
      padding: 2rem 2.5rem;
    }}
    header h1 {{ font-size: 1.75rem; font-weight: 700; color: var(--text); }}
    header h1 span {{ color: var(--accent); }}
    header p {{ color: var(--muted); font-size: 0.875rem; margin-top: 0.25rem; }}
    .container {{ max-width: 1400px; margin: 0 auto; padding: 2rem 2.5rem; }}

    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(7, 1fr);
      gap: 1rem;
      margin-bottom: 2.5rem;
    }}
    .card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.25rem 1.5rem;
    }}
    .card .label {{ font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }}
    .card .value {{ font-size: 1.75rem; font-weight: 700; margin-top: 0.25rem; }}
    .card .sub   {{ font-size: 0.8rem; color: var(--muted); margin-top: 0.125rem; }}

    h2 {{
      font-size: 1.125rem;
      font-weight: 600;
      margin-bottom: 1rem;
      color: var(--text);
    }}
    .section {{ margin-bottom: 3rem; }}

    .charts-grid {{
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 1.5rem;
      margin-bottom: 2.5rem;
    }}
    .chart-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.5rem;
    }}
    .chart-card h2 {{ margin-bottom: 1rem; }}
    .chart-wrapper {{ position: relative; height: 280px; }}

    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.875rem;
    }}
    thead th {{
      background: #0d1117;
      padding: 0.75rem 1rem;
      text-align: left;
      font-size: 0.75rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--muted);
      border-bottom: 1px solid var(--border);
    }}
    thead th.right {{ text-align: right; }}
    tbody tr {{ border-bottom: 1px solid var(--border); transition: background 0.1s; }}
    tbody tr:last-child {{ border-bottom: none; }}
    tbody tr:hover {{ background: #1c2128; }}
    tbody td {{ padding: 0.75rem 1rem; }}
    .table-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow: hidden;
    }}
    .table-card h2 {{ padding: 1.25rem 1.5rem; border-bottom: 1px solid var(--border); margin: 0; }}
    .table-card table {{ border-radius: 0; }}

    .mono  {{ font-family: ui-monospace, "SF Mono", monospace; }}
    .right {{ text-align: right; }}
    .cost  {{ color: #22d3ee; }}
    .path  {{ max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 0.8rem; color: var(--muted); }}

    .model-badge {{
      display: inline-block;
      padding: 0.2em 0.65em;
      border-radius: 999px;
      border: 1px solid;
      font-size: 0.8rem;
      font-weight: 500;
      font-family: ui-monospace, monospace;
    }}

    .timeline-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.5rem;
      margin-bottom: 2.5rem;
    }}
    .timeline-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 0.75rem;
      margin-bottom: 1rem;
    }}
    .timeline-header h2 {{ margin: 0; }}
    .timeline-controls {{
      display: flex;
      gap: 0.5rem;
      flex-wrap: wrap;
    }}
    .btn-group {{
      display: flex;
      border: 1px solid var(--border);
      border-radius: 8px;
      overflow: hidden;
    }}
    .btn {{
      background: transparent;
      color: var(--muted);
      border: none;
      padding: 0.35rem 0.75rem;
      font-size: 0.75rem;
      font-family: inherit;
      cursor: pointer;
      transition: all 0.15s;
    }}
    .btn:not(:last-child) {{ border-right: 1px solid var(--border); }}
    .btn:hover {{ color: var(--text); background: #1c2128; }}
    .btn.active {{ background: var(--accent); color: #fff; }}
    .timeline-wrapper {{ position: relative; height: 300px; }}

    footer {{
      text-align: center;
      padding: 2rem;
      color: var(--muted);
      font-size: 0.8rem;
      border-top: 1px solid var(--border);
    }}
    footer a {{ color: var(--accent); text-decoration: none; }}

    .sortable thead th {{
      cursor: pointer;
      user-select: none;
      position: relative;
      padding-right: 1.5rem;
    }}
    .sortable thead th:hover {{ color: var(--text); }}
    .sortable thead th::after {{
      content: "";
      position: absolute;
      right: 0.5rem;
      top: 50%;
      transform: translateY(-50%);
      font-size: 0.65rem;
      color: var(--muted);
    }}
    .sortable thead th.sort-asc::after {{ content: "\\25B2"; color: var(--accent); }}
    .sortable thead th.sort-desc::after {{ content: "\\25BC"; color: var(--accent); }}

    @media (max-width: 900px) {{
      .charts-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>

<header>
  <h1><span>opencode</span> Token Report</h1>
  <p>Generated {generated_at} &mdash; reads live from ~/.local/share/opencode/</p>
</header>

<div class="container">

  <!-- Summary cards -->
  <div class="summary-grid">
    <div class="card">
      <div class="label">Messages</div>
      <div class="value">{fmt_compact(total_msgs)}</div>
      <div class="sub">{fmt_tokens(total_msgs)} turns</div>
    </div>
    <div class="card">
      <div class="label">Sessions</div>
      <div class="value">{fmt_compact(total_sess)}</div>
      <div class="sub">unique sessions</div>
    </div>
    <div class="card">
      <div class="label">Input</div>
      <div class="value" style="color:#6366f1">{fmt_compact(grand_input)}</div>
      <div class="sub">{fmt_tokens(grand_input)}</div>
    </div>
    <div class="card">
      <div class="label">Output</div>
      <div class="value" style="color:#22d3ee">{fmt_compact(grand_output)}</div>
      <div class="sub">{fmt_tokens(grand_output)}</div>
    </div>
    <div class="card">
      <div class="label">Reasoning</div>
      <div class="value" style="color:#f59e0b">{fmt_compact(grand_reasoning)}</div>
      <div class="sub">{fmt_tokens(grand_reasoning)}</div>
    </div>
    <div class="card">
      <div class="label">Cache Read</div>
      <div class="value" style="color:#10b981">{fmt_compact(grand_cache_read)}</div>
      <div class="sub">{fmt_tokens(grand_cache_read)}</div>
    </div>
    <div class="card">
      <div class="label">Est. Cost</div>
      <div class="value" style="color:#22d3ee">{fmt_cost(grand_cost_est)}</div>
      <div class="sub">based on pricing</div>
    </div>
  </div>

  <!-- Charts -->
  <div class="charts-grid">
    <div class="chart-card">
      <h2>Tokens by Model</h2>
      <div class="chart-wrapper">
        <canvas id="barChart"></canvas>
      </div>
    </div>
    <div class="chart-card">
      <h2>Output Token Share</h2>
      <div class="chart-wrapper">
        <canvas id="donutChart"></canvas>
      </div>
    </div>
  </div>

  <!-- Timeline -->
  <div class="timeline-card">
    <div class="timeline-header">
      <h2>Token Usage Over Time</h2>
      <div class="timeline-controls">
        <div class="btn-group" id="chartTypeGroup">
          <button class="btn active" data-value="line">Line</button>
          <button class="btn" data-value="bar">Bar</button>
        </div>
        <div class="btn-group" id="tokenTypeGroup">
          <button class="btn" data-value="input">Input</button>
          <button class="btn" data-value="output">Output</button>
          <button class="btn active" data-value="total">Total</button>
        </div>
        <div class="btn-group" id="groupByGroup">
          <button class="btn" data-value="hour">Hour</button>
          <button class="btn active" data-value="day">Day</button>
          <button class="btn" data-value="week">Week</button>
          <button class="btn" data-value="month">Month</button>
        </div>
      </div>
    </div>
    <div class="timeline-wrapper">
      <canvas id="lineChart"></canvas>
    </div>
  </div>

  <!-- Model table -->
  <div class="section">
    <div class="table-card">
      <h2>Token Usage by Model</h2>
      <table class="sortable">
        <thead>
          <tr>
            <th data-type="string">Model</th>
            <th data-type="string">Provider</th>
            <th class="right" data-type="number">Messages</th>
            <th class="right" data-type="number">Input</th>
            <th class="right" data-type="number">Output</th>
            <th class="right" data-type="number">Reasoning</th>
            <th class="right" data-type="number">Cache Read</th>
            <th class="right" data-type="number">Total</th>
            <th class="right" data-type="number">Est. Cost</th>
          </tr>
        </thead>
        <tbody>
          {model_rows}
        </tbody>
      </table>
    </div>
  </div>

  <!-- Project table -->
  <div class="section">
    <div class="table-card">
      <h2>Projects by Token Usage</h2>
      <table class="sortable">
        <thead>
          <tr>
            <th data-type="string">Project</th>
            <th class="right" data-type="number">Messages</th>
            <th class="right" data-type="number">Input</th>
            <th class="right" data-type="number">Output</th>
            <th class="right" data-type="number">Total</th>
          </tr>
        </thead>
        <tbody>
          {project_rows}
        </tbody>
      </table>
    </div>
  </div>

</div>

<footer>
  Opencode Token Usage Report &mdash; By Joachim Zeelmaekers
</footer>

<script>
const chartDefaults = {{
  responsive: true,
  maintainAspectRatio: false,
  plugins: {{ legend: {{ labels: {{ color: "#e6edf3", font: {{ size: 12 }} }} }} }},
}};

// Bar chart — tokens by model
new Chart(document.getElementById("barChart"), {{
  type: "bar",
  data: {{
    labels: {bar_labels},
    datasets: [
      {{
        label: "Input Tokens",
        data: {bar_input},
        backgroundColor: {bar_colors}.map(c => c + "cc"),
        borderRadius: 4,
      }},
      {{
        label: "Output Tokens",
        data: {bar_output},
        backgroundColor: {bar_colors}.map(c => c + "55"),
        borderRadius: 4,
      }},
    ]
  }},
  options: {{
    ...chartDefaults,
    scales: {{
      x: {{
        title: {{ display: true, text: "Model", color: "#7d8590" }},
        ticks: {{ color: "#7d8590" }},
        grid: {{ color: "#21262d" }},
      }},
      y: {{
        title: {{ display: true, text: "Tokens", color: "#7d8590" }},
        ticks: {{ color: "#7d8590", callback: v => v >= 1e6 ? (v/1e6).toFixed(1)+"M" : v >= 1e3 ? (v/1e3).toFixed(0)+"K" : v }},
        grid: {{ color: "#21262d" }},
      }},
    }},
  }}
}});

// Donut chart — output share
new Chart(document.getElementById("donutChart"), {{
  type: "doughnut",
  data: {{
    labels: {donut_labels},
    datasets: [{{ data: {donut_data}, backgroundColor: {donut_colors}, borderWidth: 0 }}],
  }},
  options: {{
    ...chartDefaults,
    cutout: "65%",
  }}
}});

// Timeline — interactive with grouping, chart type, token type
const RAW = {timeline_raw};
const MODELS = {timeline_models};
const fmtAxis = v => v >= 1e6 ? (v/1e6).toFixed(1)+"M" : v >= 1e3 ? (v/1e3).toFixed(0)+"K" : v;

let tlChart = null;
let tlState = {{ chartType: "line", tokenType: "total", groupBy: "day" }};

function getWeekKey(d) {{
  const dt = new Date(d + ":00:00Z");
  const jan1 = new Date(Date.UTC(dt.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((dt - jan1) / 86400000 + jan1.getUTCDay() + 1) / 7);
  return dt.getUTCFullYear() + "-W" + String(week).padStart(2, "0");
}}

function groupData(raw, groupBy) {{
  const buckets = {{}};
  for (const [hourKey, models] of Object.entries(raw)) {{
    let bk;
    if (groupBy === "hour") bk = hourKey;
    else if (groupBy === "day") bk = hourKey.slice(0, 10);
    else if (groupBy === "week") bk = getWeekKey(hourKey);
    else bk = hourKey.slice(0, 7);
    if (!buckets[bk]) buckets[bk] = {{}};
    for (const [mk, t] of Object.entries(models)) {{
      if (!buckets[bk][mk]) buckets[bk][mk] = {{ input: 0, output: 0 }};
      buckets[bk][mk].input += t.input || 0;
      buckets[bk][mk].output += t.output || 0;
    }}
  }}
  return buckets;
}}

function fillGaps(keys, groupBy) {{
  if (keys.length < 2 || groupBy === "hour") return keys;
  const filled = [];
  const sorted = [...keys].sort();
  const first = sorted[0], last = sorted[sorted.length - 1];
  if (groupBy === "day") {{
    const d = new Date(first + "T00:00:00Z");
    const end = new Date(last + "T00:00:00Z");
    while (d <= end) {{
      filled.push(d.toISOString().slice(0, 10));
      d.setUTCDate(d.getUTCDate() + 1);
    }}
  }} else if (groupBy === "week") {{
    // Parse year and week, step by 7 days
    const parseWeek = w => {{
      const [y, wn] = w.split("-W").map(Number);
      const jan1 = new Date(Date.UTC(y, 0, 1));
      const dayOffset = (wn - 1) * 7 - jan1.getUTCDay() + 1;
      return new Date(Date.UTC(y, 0, 1 + dayOffset));
    }};
    const d = parseWeek(first);
    const end = parseWeek(last);
    while (d <= end) {{
      filled.push(getWeekKey(d.toISOString().slice(0, 13).replace(":", "")));
      d.setUTCDate(d.getUTCDate() + 7);
    }}
  }} else if (groupBy === "month") {{
    const [fy, fm] = first.split("-").map(Number);
    const [ly, lm] = last.split("-").map(Number);
    let y = fy, m = fm;
    while (y < ly || (y === ly && m <= lm)) {{
      filled.push(y + "-" + String(m).padStart(2, "0"));
      m++;
      if (m > 12) {{ m = 1; y++; }}
    }}
  }}
  return filled.length ? filled : sorted;
}}

function renderTimeline() {{
  const {{ chartType, tokenType, groupBy }} = tlState;
  const grouped = groupData(RAW, groupBy);
  const labels = fillGaps(Object.keys(grouped), groupBy);
  const datasets = MODELS.map(m => {{
    const data = labels.map(l => {{
      const b = grouped[l]?.[m.key] || {{ input: 0, output: 0 }};
      if (tokenType === "input") return b.input;
      if (tokenType === "output") return b.output;
      return b.input + b.output;
    }});
    return {{
      label: m.name,
      data,
      borderColor: m.color,
      backgroundColor: chartType === "bar" ? m.color + "bb" : m.color + "20",
      tension: 0.3,
      fill: false,
      pointRadius: chartType === "line" ? 3 : 0,
      borderWidth: chartType === "line" ? 2 : 0,
      borderRadius: chartType === "bar" ? 4 : 0,
    }};
  }});

  const tokenLabel = tokenType.charAt(0).toUpperCase() + tokenType.slice(1);
  const groupLabel = groupBy.charAt(0).toUpperCase() + groupBy.slice(1);

  function fmtLabel(raw) {{
    if (groupBy === "hour") {{
      // "2026-01-31T09" -> "Jan 31 09:00"
      const [datePart, hour] = raw.split("T");
      const d = new Date(datePart + "T00:00:00Z");
      const mon = d.toLocaleString("en", {{ month: "short", timeZone: "UTC" }});
      return mon + " " + d.getUTCDate() + " " + hour + ":00";
    }}
    if (groupBy === "day") {{
      const d = new Date(raw + "T00:00:00Z");
      const mon = d.toLocaleString("en", {{ month: "short", timeZone: "UTC" }});
      return mon + " " + d.getUTCDate();
    }}
    if (groupBy === "week") return raw;
    if (groupBy === "month") {{
      const d = new Date(raw + "-01T00:00:00Z");
      return d.toLocaleString("en", {{ month: "long", year: "numeric", timeZone: "UTC" }});
    }}
    return raw;
  }}

  const displayLabels = labels.map(fmtLabel);

  if (tlChart) tlChart.destroy();
  tlChart = new Chart(document.getElementById("lineChart"), {{
    type: chartType,
    data: {{ labels: displayLabels, datasets }},
    options: {{
      ...chartDefaults,
      interaction: {{ mode: "index", intersect: false }},
      scales: {{
        x: {{
          title: {{ display: true, text: groupLabel, color: "#7d8590" }},
          ticks: {{ color: "#7d8590", maxTicksLimit: 24, maxRotation: 45, minRotation: 25 }},
          grid: {{ color: "#21262d" }},
          stacked: chartType === "bar",
        }},
        y: {{
          title: {{ display: true, text: tokenLabel + " Tokens", color: "#7d8590" }},
          ticks: {{ color: "#7d8590", callback: (v) => fmtAxis(v) }},
          grid: {{ color: "#21262d" }},
          stacked: chartType === "bar",
        }},
      }},
      plugins: {{
        ...chartDefaults.plugins,
        tooltip: {{
          callbacks: {{
            label: ctx => ctx.dataset.label + ": " + ctx.parsed.y.toLocaleString() + " tokens",
          }},
        }},
      }},
    }},
  }});
}}

// Wire up button groups
function setupGroup(id, stateKey) {{
  document.getElementById(id).addEventListener("click", e => {{
    const btn = e.target.closest(".btn");
    if (!btn) return;
    e.currentTarget.querySelectorAll(".btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    tlState[stateKey] = btn.dataset.value;
    renderTimeline();
  }});
}}
setupGroup("chartTypeGroup", "chartType");
setupGroup("tokenTypeGroup", "tokenType");
setupGroup("groupByGroup", "groupBy");
renderTimeline();

// Sortable tables
document.querySelectorAll("table.sortable").forEach(table => {{
  const headers = table.querySelectorAll("thead th");
  headers.forEach((th, colIdx) => {{
    th.addEventListener("click", () => {{
      const isNum = th.dataset.type === "number";
      const tbody = table.querySelector("tbody");
      const rows = Array.from(tbody.querySelectorAll("tr"));
      const wasAsc = th.classList.contains("sort-asc");
      headers.forEach(h => h.classList.remove("sort-asc", "sort-desc"));
      const dir = wasAsc ? -1 : 1;
      th.classList.add(dir === 1 ? "sort-asc" : "sort-desc");
      rows.sort((a, b) => {{
        const av = a.children[colIdx].dataset.sort || a.children[colIdx].textContent;
        const bv = b.children[colIdx].dataset.sort || b.children[colIdx].textContent;
        if (isNum) return (parseFloat(av) - parseFloat(bv)) * dir;
        return av.localeCompare(bv) * dir;
      }});
      rows.forEach(r => tbody.appendChild(r));
    }});
  }});
}});
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    os.makedirs(REPORTS_DIR, exist_ok=True)

    print("Loading sessions...")
    sessions = load_sessions()
    print(f"  {len(sessions)} sessions found")

    print("Loading messages...")
    messages, source = load_messages()
    print(f"  {len(messages)} assistant messages with token data (source: {source})")

    if not messages:
        print("No messages found. Check STORAGE_DIR path.")
        sys.exit(1)

    print("Aggregating...")
    data = aggregate(messages, sessions)

    print("Generating HTML...")
    html = build_html(data)

    # Write timestamped + latest
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_file = os.path.join(REPORTS_DIR, f"report_{ts}.html")
    latest   = os.path.join(REPORTS_DIR, "latest.html")

    with open(out_file, "w") as f:
        f.write(html)
    with open(latest, "w") as f:
        f.write(html)

    print(f"\nReport saved:")
    print(f"  {out_file}")
    print(f"  {latest}  (symlink-style copy)")
    print(f"\nOpen with:  open {latest}")

    # Quick summary
    ms = data["model_stats"]
    total_in  = sum(v["input"]  for v in ms.values())
    total_out = sum(v["output"] for v in ms.values())
    print(f"\nSummary:")
    print(f"  Sessions : {data['total_sessions']:,}")
    print(f"  Messages : {data['total_messages']:,}")
    print(f"  Input    : {total_in:,} tokens")
    print(f"  Output   : {total_out:,} tokens")
    for key, v in sorted(ms.items(), key=lambda x: x[1]["input"]+x[1]["output"], reverse=True):
        print(f"  {key:<35}  {v['input']+v['output']:>12,} tokens  ({v['messages']} msgs)")


if __name__ == "__main__":
    main()
