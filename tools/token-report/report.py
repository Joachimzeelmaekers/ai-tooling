"""HTML report generation — provider-agnostic with client-side provider filtering."""

import json
import os
from datetime import datetime


def fmt_tokens(n: int) -> str:
    return f"{n:,}"


def fmt_compact(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def fmt_cost(c: float) -> str:
    return f"${c:.2f}"


COLORS = [
    "#6366f1", "#22d3ee", "#f59e0b", "#10b981", "#ef4444",
    "#a78bfa", "#f472b6", "#34d399", "#fbbf24", "#818cf8",
]

PROVIDER_COLORS = {
    "claude-code": "#d97757",  # terracotta
    "opencode": "#6366f1",      # indigo
    "cursor": "#22d3ee",        # cyan
    "codex": "#ef4444",         # red
}


def build_html(data: dict) -> str:
    model_stats = data["model_stats"]
    hourly_data = data["hourly"]
    project_stats = data["project_stats"]
    provider_totals = data.get("provider_totals", {})
    total_msgs = data["total_messages"]
    total_sess = data["total_sessions"]
    month_cost = data.get("month_cost_estimated", 0.0)
    month_stats = data.get("month_stats", {})
    current_month = data.get("current_month", "")

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    sorted_models = sorted(
        model_stats.items(),
        key=lambda x: x[1]["input"] + x[1]["output"],
        reverse=True,
    )

    model_colors = {k: COLORS[i % len(COLORS)] for i, (k, _) in enumerate(sorted_models)}

    active_providers = sorted(provider_totals.keys())

    # Build full model data blob for JS (drives all charts + tables + cards)
    models_js = json.dumps([
        {
            "key": k,
            "provider": ms.get("provider", ""),
            "color": model_colors[k],
            "messages": ms["messages"],
            "input": ms["input"],
            "output": ms["output"],
            "reasoning": ms["reasoning"],
            "cache_read": ms["cache_read"],
            "cost_estimated": round(ms["cost_estimated"], 2),
            "month_cost": round(month_stats.get(k, {}).get("cost_estimated", 0.0), 2),
        }
        for k, ms in sorted_models
    ])

    providers_js = json.dumps([
        {
            "name": p,
            "color": PROVIDER_COLORS.get(p, "#7d8590"),
            "messages": provider_totals[p]["messages"],
            "sessions": provider_totals[p]["sessions"],
            "input": provider_totals[p]["input"],
            "output": provider_totals[p]["output"],
            "cost_estimated": round(provider_totals[p]["cost_estimated"], 2),
        }
        for p in active_providers
    ])

    # Timeline needs provider info per model in hourly data
    # Enrich hourly with provider mapping
    model_provider_map = {k: ms.get("provider", "") for k, ms in model_stats.items()}

    timeline_raw = json.dumps(hourly_data)
    timeline_models = json.dumps([
        {"key": k, "name": k, "color": model_colors[k], "provider": model_provider_map.get(k, "")}
        for k, _ in sorted_models
    ])

    # Project data with per-model breakdown (so we can filter by provider)
    projects_js_data = {}
    for path, model_map in project_stats.items():
        dir_name = os.path.basename(path) or path
        projects_js_data[dir_name] = {
            "path": path,
            "models": {
                mk: {"messages": mv["messages"], "input": mv["input"], "output": mv["output"]}
                for mk, mv in model_map.items()
            }
        }
    projects_js = json.dumps(projects_js_data)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>AI Token Report</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
  <style>
    :root {{
      --bg: #141413;
      --surface: #1c1c1a;
      --surface-hover: #2a2926;
      --border: #3d3b36;
      --text: #eae6dc;
      --text-muted: #a39e90;
      --brand: #d97757;
      --brand-hover: #e09070;
      --space-sm: 0.75rem;
      --space-md: 1rem;
      --space-lg: 1.5rem;
      --space-xl: 2rem;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
      display: flex;
      min-height: 100vh;
    }}

    /* Sidebar */
    aside {{
      width: 220px;
      background: var(--bg);
      border-right: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      flex-shrink: 0;
    }}
    .brand {{
      height: 56px;
      display: flex;
      align-items: center;
      padding: 0 1rem;
      border-bottom: 1px solid var(--border);
    }}
    .brand h1 {{
      font-size: 1rem;
      font-weight: 700;
      color: var(--text);
    }}
    .brand h1 span {{ color: var(--brand); }}

    nav {{
      padding: 0.75rem;
      flex: 1;
    }}
    .nav-item {{
      display: flex;
      align-items: center;
      gap: 0.625rem;
      padding: 0.5rem 0.75rem;
      border-radius: 8px;
      color: var(--text-muted);
      font-size: 0.875rem;
      cursor: pointer;
      transition: all 0.15s;
      text-decoration: none;
    }}
    .nav-item:hover {{
      background: var(--surface-hover);
      color: var(--text);
    }}
    .nav-item.active {{
      background: var(--surface);
      color: var(--text);
    }}
    .nav-item svg {{
      width: 1rem;
      height: 1rem;
      color: var(--text-muted);
    }}
    .nav-item.active svg {{ color: var(--brand); }}

    .sidebar-footer {{
      padding: 0.75rem;
      border-top: 1px solid var(--border);
      font-size: 0.7rem;
      color: var(--text-muted);
    }}

    /* Main content */
    main {{
      flex: 1;
      overflow: auto;
      max-width: 1280px;
      margin: 0 auto;
      padding: 1.5rem 2rem;
    }}

    .page-header {{
      margin-bottom: var(--space-lg);
    }}
    .page-header h2 {{
      font-size: 1.5rem;
      font-weight: 700;
      color: var(--text);
    }}
    .page-header p {{
      font-size: 0.875rem;
      color: var(--text-muted);
      margin-top: 0.25rem;
    }}

    .filter-bar {{
      display: flex;
      align-items: center;
      gap: var(--space-sm);
      margin-bottom: var(--space-lg);
      padding: var(--space-sm) var(--space-md);
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
    }}
    .filter-bar .filter-label {{
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      font-weight: 600;
    }}
    .filter-btn {{
      padding: 0.35rem 0.85rem;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: transparent;
      color: var(--text-muted);
      font-size: 0.75rem;
      font-family: ui-monospace, monospace;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s;
    }}
    .filter-btn:hover {{ color: var(--text); border-color: var(--text-muted); }}

    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: var(--space-sm);
      margin-bottom: var(--space-xl);
    }}
    .card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1rem 1.25rem;
    }}
    .card .label {{ font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); }}
    .card .value {{ font-size: 1.5rem; font-weight: 700; margin-top: 0.25rem; }}
    .card .sub   {{ font-size: 0.75rem; color: var(--text-muted); margin-top: 0.125rem; }}

    h3 {{
      font-size: 1rem;
      font-weight: 600;
      margin-bottom: 0.75rem;
      color: var(--text);
    }}
    .section {{ margin-bottom: var(--space-xl); }}

    .charts-grid-2 {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: var(--space-md);
      margin-bottom: var(--space-xl);
    }}
    .chart-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.25rem;
    }}
    .chart-card h3 {{ margin-bottom: 1rem; }}
    .chart-wrapper {{ position: relative; height: 260px; }}
    .chart-card.full .chart-wrapper {{ height: 340px; }}
    .chart-card.full {{ margin-bottom: var(--space-md); }}

    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.875rem;
    }}
    thead th {{
      background: var(--bg);
      padding: 0.75rem 1rem;
      text-align: left;
      font-size: 0.7rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--text-muted);
      border-bottom: 1px solid var(--border);
    }}
    thead th.right {{ text-align: right; }}
    tbody tr {{ border-bottom: 1px solid var(--border); transition: background 0.1s; }}
    tbody tr:last-child {{ border-bottom: none; }}
    tbody tr:hover {{ background: var(--surface-hover); }}
    tbody td {{ padding: 0.75rem 1rem; }}
    .table-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow: hidden;
    }}
    .table-card h3 {{ padding: 1rem 1.25rem; border-bottom: 1px solid var(--border); margin: 0; }}

    .mono  {{ font-family: ui-monospace, "SF Mono", monospace; }}
    .right {{ text-align: right; }}
    .cost  {{ color: var(--brand); }}
    .path  {{ max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 0.8rem; color: var(--text-muted); }}

    .model-badge {{
      display: inline-block;
      padding: 0.2em 0.65em;
      border-radius: 999px;
      border: 1px solid;
      font-size: 0.75rem;
      font-weight: 500;
      font-family: ui-monospace, monospace;
    }}
    .provider-badge {{
      font-size: 0.7rem;
      font-weight: 600;
      font-family: ui-monospace, monospace;
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }}

    .timeline-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.25rem;
      margin-bottom: var(--space-xl);
    }}
    .timeline-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 0.75rem;
      margin-bottom: 1rem;
    }}
    .timeline-header h3 {{ margin: 0; }}
    .timeline-controls {{
      display: flex;
      gap: 0.5rem;
      flex-wrap: wrap;
    }}
    .timeline-select {{
      background: var(--surface);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0.3rem 0.55rem;
      font-size: 0.75rem;
      font-family: inherit;
      min-width: 7rem;
      cursor: pointer;
    }}
    .timeline-select:focus {{
      outline: none;
      border-color: var(--brand);
    }}
    .btn-group {{
      display: flex;
      border: 1px solid var(--border);
      border-radius: 8px;
      overflow: hidden;
    }}
    .btn {{
      background: transparent;
      color: var(--text-muted);
      border: none;
      padding: 0.3rem 0.65rem;
      font-size: 0.7rem;
      font-family: inherit;
      cursor: pointer;
      transition: all 0.15s;
    }}
    .btn:not(:last-child) {{ border-right: 1px solid var(--border); }}
    .btn:hover {{ color: var(--text); background: var(--surface-hover); }}
    .btn.active {{ background: var(--brand); color: #fff; }}
    .timeline-wrapper {{ position: relative; height: 500px; }}

    footer {{
      text-align: center;
      padding: 1.5rem;
      color: var(--text-muted);
      font-size: 0.75rem;
      border-top: 1px solid var(--border);
      margin-top: auto;
    }}

    .tab-bar {{
      display: flex;
      gap: 0.25rem;
      margin-bottom: 1.5rem;
      border-bottom: 1px solid var(--border);
    }}
    .tab-btn {{
      padding: 0.75rem 1rem;
      background: transparent;
      border: none;
      border-bottom: 2px solid transparent;
      color: var(--text-muted);
      font-size: 0.875rem;
      cursor: pointer;
      transition: all 0.15s;
    }}
    .tab-btn:hover {{ color: var(--text); }}
    .tab-btn.active {{
      color: var(--text);
      border-bottom-color: var(--brand);
    }}

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
      font-size: 0.6rem;
      color: var(--text-muted);
    }}
    .sortable thead th.sort-asc::after {{ content: "\\25B2"; color: var(--brand); }}
    .sortable thead th.sort-desc::after {{ content: "\\25BC"; color: var(--brand); }}

    @media (max-width: 900px) {{
      .charts-grid-2 {{ grid-template-columns: 1fr; }}
      .summary-grid {{ grid-template-columns: repeat(2, 1fr); }}
      aside {{ display: none; }}
    }}

    /* Page sections */
    .page {{ display: none; }}
    .page.active {{ display: block; }}
  </style>
</head>
<body>

<aside>
  <div class="brand">
    <h1><span>AI</span> Dashboard</h1>
  </div>
  <nav>
    <a class="nav-item active" data-page="overview">
      <svg viewBox="0 0 16 16" fill="currentColor"><rect x="1" y="3" width="14" height="3" rx="1"/><rect x="1" y="8" width="14" height="3" rx="1"/><rect x="1" y="13" width="14" height="3" rx="1"/></svg>
      Overview
    </a>
    <a class="nav-item" data-page="timeline">
      <svg viewBox="0 0 16 16" fill="currentColor"><path d="M2 12l3-3 3 3 5-5v3H2v-1z"/><circle cx="13.5" cy="4.5" r="2"/></svg>
      Timeline
    </a>
    <a class="nav-item" data-page="models">
      <svg viewBox="0 0 16 16" fill="currentColor"><path d="M8 1a7 7 0 100 14A7 7 0 008 1zM6 5l6 3-6 3V5z"/></svg>
      Models
    </a>
    <a class="nav-item" data-page="projects">
      <svg viewBox="0 0 16 16" fill="currentColor"><path d="M2 3h4l1 1h7v10H2V3zm0 5h12"/></svg>
      Projects
    </a>
  </nav>
  <div class="sidebar-footer">
    <p>Generated {generated_at}</p>
  </div>
</aside>

<main>
  <!-- Provider filter -->
  <div class="filter-bar">
    <span class="filter-label">Filter</span>
    <button class="filter-btn active" data-provider="all">All</button>
  </div>

  <!-- Overview Page -->
  <div class="page active" id="page-overview">
    <div class="page-header">
      <h2>Overview</h2>
      <p>Token usage analytics across all providers</p>
    </div>

    <!-- Summary cards -->
    <div class="summary-grid" id="summaryCards"></div>

    <!-- Charts -->
    <div class="chart-card full">
      <h3>Tokens by Model</h3>
      <div class="chart-wrapper"><canvas id="barChart"></canvas></div>
    </div>
    <div class="charts-grid-2">
      <div class="chart-card">
        <h3>Output Token Share</h3>
        <div class="chart-wrapper"><canvas id="donutChart"></canvas></div>
      </div>
      <div class="chart-card">
        <h3>Tokens by Provider</h3>
        <div class="chart-wrapper"><canvas id="provDonutChart"></canvas></div>
      </div>
    </div>
  </div>

  <!-- Timeline Page -->
  <div class="page" id="page-timeline">
    <div class="page-header">
      <h2>Timeline</h2>
      <p>Token usage over time</p>
    </div>
    <div class="timeline-card">
      <div class="timeline-header">
        <h3>Token Usage Over Time</h3>
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
          <select id="lookbackSelect" class="timeline-select" aria-label="Timeline range">
            <option value="1m">Last 1 month</option>
            <option value="3m" selected>Last 3 months</option>
            <option value="6m">Last 6 months</option>
            <option value="1y">Last 1 year</option>
            <option value="2y">Last 2 years</option>
            <option value="all">All time</option>
          </select>
        </div>
      </div>
      <div class="timeline-wrapper"><canvas id="lineChart"></canvas></div>
    </div>
  </div>

  <!-- Models Page -->
  <div class="page" id="page-models">
    <div class="page-header">
      <h2>Models</h2>
      <p>Token usage by model</p>
    </div>
    <div class="section">
      <div class="table-card">
        <h3>Token Usage by Model</h3>
        <table class="sortable" id="modelTable">
          <thead>
            <tr>
              <th data-type="string">Model</th>
              <th data-type="string">Source</th>
              <th class="right" data-type="number">Messages</th>
              <th class="right" data-type="number">Input</th>
              <th class="right" data-type="number">Output</th>
              <th class="right" data-type="number">Reasoning</th>
              <th class="right" data-type="number">Cache Read</th>
              <th class="right" data-type="number">Total</th>
              <th class="right" data-type="number">Est. Cost</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Projects Page -->
  <div class="page" id="page-projects">
    <div class="page-header">
      <h2>Projects</h2>
      <p>Token usage by project</p>
    </div>
    <div class="section">
      <div class="table-card">
        <h3>Projects by Token Usage</h3>
        <table class="sortable" id="projectTable">
          <thead>
            <tr>
              <th data-type="string">Project</th>
              <th class="right" data-type="number">Messages</th>
              <th class="right" data-type="number">Input</th>
              <th class="right" data-type="number">Output</th>
              <th class="right" data-type="number">Total</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
  </div>
</main>

<footer>AI Token Usage Report</footer>

<script>
// =========================================================================
// Data
// =========================================================================
const ALL_MODELS = {models_js};
const PROVIDERS = {providers_js};
const RAW_TIMELINE = {timeline_raw};
const TIMELINE_MODELS = {timeline_models};
const PROJECTS = {projects_js};
const PROVIDER_COLORS = {json.dumps(PROVIDER_COLORS)};
const CURRENT_MONTH = "{current_month}";
const TOTAL_SESSIONS = {total_sess};

// Model -> provider lookup
const MODEL_PROVIDER = {{}};
ALL_MODELS.forEach(m => MODEL_PROVIDER[m.key] = m.provider);

// =========================================================================
// State
// =========================================================================
let activeProvider = "all"; // "all" or a provider name
let tlState = {{ chartType: "line", tokenType: "total", groupBy: "day", lookback: "3m" }};

const chartDefaults = {{
  responsive: true,
  maintainAspectRatio: false,
  plugins: {{ legend: {{ labels: {{ color: "#eae6dc", font: {{ size: 12 }} }} }} }},
}};
const fmtAxis = v => v >= 1e6 ? (v/1e6).toFixed(1)+"M" : v >= 1e3 ? (v/1e3).toFixed(0)+"K" : v;
const fmtNum = n => n.toLocaleString();
const fmtCompact = n => {{
  if (n >= 1e9) return (n/1e9).toFixed(1) + "B";
  if (n >= 1e6) return (n/1e6).toFixed(1) + "M";
  if (n >= 1e3) return (n/1e3).toFixed(1) + "K";
  return String(n);
}};
const fmtCost = c => "$" + c.toFixed(2);

function getModels() {{
  if (activeProvider === "all") return ALL_MODELS;
  return ALL_MODELS.filter(m => m.provider === activeProvider);
}}

// =========================================================================
// Navigation
// =========================================================================
function initNav() {{
  document.querySelectorAll('.nav-item').forEach(item => {{
    item.addEventListener('click', e => {{
      e.preventDefault();
      const page = item.dataset.page;
      document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
      item.classList.add('active');
      document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
      document.getElementById('page-' + page).classList.add('active');
    }});
  }});
}}

// =========================================================================
// Filter bar
// =========================================================================
function initFilterBar() {{
  const bar = document.querySelector(".filter-bar");
  PROVIDERS.forEach(p => {{
    const btn = document.createElement("button");
    btn.className = "filter-btn";
    btn.dataset.provider = p.name;
    btn.textContent = p.name;
    btn.style.setProperty("--pcolor", p.color);
    bar.appendChild(btn);
  }});
  bar.addEventListener("click", e => {{
    const btn = e.target.closest(".filter-btn");
    if (!btn) return;
    bar.querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    activeProvider = btn.dataset.provider;
    renderAll();
  }});
  // Style active buttons
  updateFilterStyles();
}}

function updateFilterStyles() {{
  document.querySelectorAll(".filter-btn").forEach(btn => {{
    const p = btn.dataset.provider;
    const color = p === "all" ? "#d97757" : (PROVIDER_COLORS[p] || "#a39e90");
    if (btn.classList.contains("active")) {{
      btn.style.background = color;
      btn.style.borderColor = color;
      btn.style.color = "#fff";
    }} else {{
      btn.style.background = "transparent";
      btn.style.borderColor = "";
      btn.style.color = "";
    }}
  }});
}}

// =========================================================================
// Summary cards
// =========================================================================
function renderSummaryCards() {{
  const models = getModels();
  const msgs = models.reduce((s, m) => s + m.messages, 0);
  const inp = models.reduce((s, m) => s + m.input, 0);
  const out = models.reduce((s, m) => s + m.output, 0);
  const rea = models.reduce((s, m) => s + m.reasoning, 0);
  const cr = models.reduce((s, m) => s + m.cache_read, 0);
  const cost = models.reduce((s, m) => s + m.cost_estimated, 0);

  const sess = activeProvider === "all"
    ? TOTAL_SESSIONS
    : (PROVIDERS.find(p => p.name === activeProvider)?.sessions || 0);

  let html = `
    <div class="card"><div class="label">Messages</div><div class="value">${{fmtCompact(msgs)}}</div><div class="sub">${{fmtNum(msgs)}} turns</div></div>
    <div class="card"><div class="label">Sessions</div><div class="value">${{fmtCompact(sess)}}</div><div class="sub">unique sessions</div></div>
    <div class="card"><div class="label">Input</div><div class="value" style="color:#6366f1">${{fmtCompact(inp)}}</div><div class="sub">${{fmtNum(inp)}}</div></div>
    <div class="card"><div class="label">Output</div><div class="value" style="color:#22d3ee">${{fmtCompact(out)}}</div><div class="sub">${{fmtNum(out)}}</div></div>
    <div class="card"><div class="label">Reasoning</div><div class="value" style="color:#f59e0b">${{fmtCompact(rea)}}</div><div class="sub">${{fmtNum(rea)}}</div></div>
    <div class="card"><div class="label">Cache Read</div><div class="value" style="color:#10b981">${{fmtCompact(cr)}}</div><div class="sub">${{fmtNum(cr)}}</div></div>
    <div class="card"><div class="label">Est. Cost (all time)</div><div class="value" style="color:#22d3ee">${{fmtCost(cost)}}</div><div class="sub">based on public pricing</div></div>
    <div class="card"><div class="label">${{CURRENT_MONTH}} Cost</div><div class="value" style="color:#f59e0b">${{fmtCost(models.reduce((s, m) => s + m.month_cost, 0))}}</div><div class="sub">this month</div></div>
  `;

  if (activeProvider === "all") {{
    PROVIDERS.forEach(p => {{
      html += `<div class="card"><div class="label" style="color:${{p.color}}">${{p.name}}</div><div class="value">${{fmtCompact(p.messages)}}</div><div class="sub">${{fmtNum(p.input + p.output)}} tokens &middot; ${{fmtCost(p.cost_estimated)}}</div></div>`;
    }});
  }}

  document.getElementById("summaryCards").innerHTML = html;
}}

// =========================================================================
// Charts
// =========================================================================
let barChart, donutChart, provDonutChart;

function renderBarChart() {{
  const models = getModels();
  if (barChart) barChart.destroy();
  barChart = new Chart(document.getElementById("barChart"), {{
    type: "bar",
    data: {{
      labels: models.map(m => m.key),
      datasets: [
        {{ label: "Input", data: models.map(m => m.input), backgroundColor: models.map(m => m.color + "cc"), borderRadius: 4 }},
        {{ label: "Output", data: models.map(m => m.output), backgroundColor: models.map(m => m.color + "55"), borderRadius: 4 }},
      ]
    }},
    options: {{
      ...chartDefaults,
      scales: {{
        x: {{ ticks: {{ color: "#a39e90", maxRotation: 45, minRotation: 25 }}, grid: {{ color: "#3d3b36" }} }},
        y: {{ ticks: {{ color: "#a39e90", callback: fmtAxis }}, grid: {{ color: "#3d3b36" }} }},
      }},
    }}
  }});
}}

function renderDonutChart() {{
  const models = getModels();
  if (donutChart) donutChart.destroy();
  donutChart = new Chart(document.getElementById("donutChart"), {{
    type: "doughnut",
    data: {{
      labels: models.map(m => m.key),
      datasets: [{{ data: models.map(m => m.output), backgroundColor: models.map(m => m.color), borderWidth: 0 }}],
    }},
    options: {{ ...chartDefaults, cutout: "65%" }}
  }});
}}

function renderProvDonutChart() {{
  if (provDonutChart) provDonutChart.destroy();
  const provs = activeProvider === "all" ? PROVIDERS : PROVIDERS.filter(p => p.name === activeProvider);
  provDonutChart = new Chart(document.getElementById("provDonutChart"), {{
    type: "doughnut",
    data: {{
      labels: provs.map(p => p.name),
      datasets: [{{ data: provs.map(p => p.input + p.output), backgroundColor: provs.map(p => p.color), borderWidth: 0 }}],
    }},
    options: {{ ...chartDefaults, cutout: "65%" }}
  }});
}}

// =========================================================================
// Timeline
// =========================================================================
let tlChart = null;

function getWeekKey(d) {{
  const dt = new Date(d + ":00:00Z");
  const jan1 = new Date(Date.UTC(dt.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((dt - jan1) / 86400000 + jan1.getUTCDay() + 1) / 7);
  return dt.getUTCFullYear() + "-W" + String(week).padStart(2, "0");
}}

function parseWeekKey(weekKey) {{
  const [year, weekNum] = weekKey.split("-W").map(Number);
  const jan1 = new Date(Date.UTC(year, 0, 1));
  return new Date(Date.UTC(year, 0, 1 + (weekNum - 1) * 7 - jan1.getUTCDay() + 1));
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
      if (activeProvider !== "all" && MODEL_PROVIDER[mk] !== activeProvider) continue;
      if (!buckets[bk][mk]) buckets[bk][mk] = {{ input: 0, output: 0 }};
      buckets[bk][mk].input += t.input || 0;
      buckets[bk][mk].output += t.output || 0;
    }}
  }}
  return buckets;
}}

function fillGaps(keys, groupBy) {{
  if (keys.length < 2 || groupBy === "hour") return [...keys].sort();
  const sorted = [...keys].sort();
  const first = sorted[0], last = sorted[sorted.length - 1];
  const filled = [];
  if (groupBy === "day") {{
    const d = new Date(first + "T00:00:00Z"), end = new Date(last + "T00:00:00Z");
    while (d <= end) {{ filled.push(d.toISOString().slice(0, 10)); d.setUTCDate(d.getUTCDate() + 1); }}
  }} else if (groupBy === "week") {{
    const d = parseWeekKey(first), end = parseWeekKey(last);
    while (d <= end) {{ filled.push(getWeekKey(d.toISOString().slice(0, 13).replace(":", ""))); d.setUTCDate(d.getUTCDate() + 7); }}
  }} else if (groupBy === "month") {{
    const [fy, fm] = first.split("-").map(Number), [ly, lm] = last.split("-").map(Number);
    let y = fy, m = fm;
    while (y < ly || (y === ly && m <= lm)) {{ filled.push(y + "-" + String(m).padStart(2, "0")); m++; if (m > 12) {{ m = 1; y++; }} }}
  }}
  return filled.length ? filled : sorted;
}}

function fmtTimeLabel(raw, groupBy) {{
  if (groupBy === "hour") {{ const [dp, h] = raw.split("T"); const d = new Date(dp + "T00:00:00Z"); return d.toLocaleString("en", {{ month: "short", timeZone: "UTC" }}) + " " + d.getUTCDate() + " " + h + ":00"; }}
  if (groupBy === "day") {{ const d = new Date(raw + "T00:00:00Z"); return d.toLocaleString("en", {{ month: "short", timeZone: "UTC" }}) + " " + d.getUTCDate(); }}
  if (groupBy === "week") return raw;
  if (groupBy === "month") {{ const d = new Date(raw + "-01T00:00:00Z"); return d.toLocaleString("en", {{ month: "long", year: "numeric", timeZone: "UTC" }}); }}
  return raw;
}}

function parseGroupStart(groupKey, groupBy) {{
  if (groupBy === "hour") return new Date(groupKey + ":00:00Z");
  if (groupBy === "day") return new Date(groupKey + "T00:00:00Z");
  if (groupBy === "week") return parseWeekKey(groupKey);
  if (groupBy === "month") return new Date(groupKey + "-01T00:00:00Z");
  return new Date(groupKey);
}}

function getLookbackCutoff(anchorDate, lookback) {{
  if (lookback === "all") return null;
  const amount = Number(lookback.slice(0, -1));
  const unit = lookback.slice(-1);
  if (!Number.isFinite(amount) || amount <= 0) return null;

  const cutoff = new Date(anchorDate.getTime());
  if (unit === "m") cutoff.setUTCMonth(cutoff.getUTCMonth() - amount);
  if (unit === "y") cutoff.setUTCFullYear(cutoff.getUTCFullYear() - amount);
  return cutoff;
}}

function filterLabelsByLookback(labels, groupBy, lookback) {{
  if (!labels.length || lookback === "all") return labels;
  const anchorDate = parseGroupStart(labels[labels.length - 1], groupBy);
  if (Number.isNaN(anchorDate.getTime())) return labels;
  const cutoff = getLookbackCutoff(anchorDate, lookback);
  if (!cutoff) return labels;

  return labels.filter(label => {{
    const pointDate = parseGroupStart(label, groupBy);
    return !Number.isNaN(pointDate.getTime()) && pointDate >= cutoff;
  }});
}}

const CHART_GRID_COLOR = "#3d3b36";
const CHART_TEXT_COLOR = "#a39e90";

function renderTimeline() {{
  const {{ chartType, tokenType, groupBy, lookback }} = tlState;
  const grouped = groupData(RAW_TIMELINE, groupBy);
  const labels = filterLabelsByLookback(fillGaps(Object.keys(grouped), groupBy), groupBy, lookback);
  const visibleModels = TIMELINE_MODELS.filter(m => activeProvider === "all" || m.provider === activeProvider);

  const datasets = visibleModels.map(m => {{
    const series = labels.map(l => {{
      const b = grouped[l]?.[m.key] || {{ input: 0, output: 0 }};
      if (tokenType === "input") return b.input;
      if (tokenType === "output") return b.output;
      return b.input + b.output;
    }});

    const firstRealIdx = series.findIndex(v => v > 0);
    const data = series.map((v, idx) => (firstRealIdx !== -1 && idx < firstRealIdx ? null : v));

    return {{
      label: m.name, data,
      borderColor: m.color,
      backgroundColor: chartType === "bar" ? m.color + "bb" : m.color + "20",
      tension: 0.3, fill: false,
      pointRadius: 0,
      pointHoverRadius: 3,
      borderWidth: chartType === "line" ? 2 : 0,
      borderRadius: chartType === "bar" ? 4 : 0,
    }};
  }});

  if (tlChart) tlChart.destroy();
  tlChart = new Chart(document.getElementById("lineChart"), {{
    type: chartType,
    data: {{ labels: labels.map(l => fmtTimeLabel(l, groupBy)), datasets }},
    options: {{
      ...chartDefaults,
      interaction: {{ mode: "index", intersect: false }},
      scales: {{
        x: {{
          title: {{ display: true, text: groupBy.charAt(0).toUpperCase() + groupBy.slice(1), color: CHART_TEXT_COLOR }},
          ticks: {{ color: CHART_TEXT_COLOR, maxTicksLimit: 24, maxRotation: 45, minRotation: 25 }},
          grid: {{ color: CHART_GRID_COLOR }},
          stacked: chartType === "bar",
        }},
        y: {{
          title: {{ display: true, text: tokenType.charAt(0).toUpperCase() + tokenType.slice(1) + " Tokens", color: CHART_TEXT_COLOR }},
          ticks: {{ color: CHART_TEXT_COLOR, callback: fmtAxis }},
          grid: {{ color: CHART_GRID_COLOR }},
          stacked: chartType === "bar",
        }},
      }},
      plugins: {{
        ...chartDefaults.plugins,
        tooltip: {{
          callbacks: {{
            label: ctx => ctx.dataset.label + ": " + ctx.parsed.y.toLocaleString() + " tokens"
          }}
        }}
      }},
    }},
  }});
}}

function initLookbackSelect() {{
  const select = document.getElementById("lookbackSelect");
  if (!select) return;
  select.value = tlState.lookback;
  select.addEventListener("change", e => {{
    tlState.lookback = e.target.value;
    renderTimeline();
  }});
}}

// =========================================================================
// Tables
// =========================================================================
function renderModelTable() {{
  const models = getModels();
  const tbody = document.querySelector("#modelTable tbody");
  tbody.innerHTML = models.map(m => {{
    const total = m.input + m.output;
    const pc = PROVIDER_COLORS[m.provider] || "#7d8590";
    return `<tr data-provider="${{m.provider}}">
      <td data-sort="${{m.key}}"><span class="model-badge" style="background:${{m.color}}20;color:${{m.color}};border-color:${{m.color}}40">${{m.key}}</span></td>
      <td data-sort="${{m.provider}}"><span class="provider-badge" style="color:${{pc}}">${{m.provider}}</span></td>
      <td class="mono right" data-sort="${{m.messages}}">${{fmtNum(m.messages)}}</td>
      <td class="mono right" data-sort="${{m.input}}">${{fmtNum(m.input)}}</td>
      <td class="mono right" data-sort="${{m.output}}">${{fmtNum(m.output)}}</td>
      <td class="mono right" data-sort="${{m.reasoning}}">${{fmtNum(m.reasoning)}}</td>
      <td class="mono right" data-sort="${{m.cache_read}}">${{fmtNum(m.cache_read)}}</td>
      <td class="mono right" data-sort="${{total}}">${{fmtNum(total)}}</td>
      <td class="mono right cost" data-sort="${{m.cost_estimated.toFixed(6)}}">${{fmtCost(m.cost_estimated)}}</td>
    </tr>`;
  }}).join("");
}}

function renderProjectTable() {{
  const tbody = document.querySelector("#projectTable tbody");
  const rows = [];
  for (const [dirName, proj] of Object.entries(PROJECTS)) {{
    let msgs = 0, inp = 0, out = 0;
    for (const [mk, mv] of Object.entries(proj.models)) {{
      if (activeProvider !== "all" && MODEL_PROVIDER[mk] !== activeProvider) continue;
      msgs += mv.messages; inp += mv.input; out += mv.output;
    }}
    if (msgs === 0) continue;
    rows.push({{ dirName, path: proj.path, msgs, inp, out, total: inp + out }});
  }}
  rows.sort((a, b) => b.total - a.total);
  tbody.innerHTML = rows.map(r => `<tr>
    <td class="mono path" title="${{r.path}}" data-sort="${{r.dirName}}">${{r.dirName}}</td>
    <td class="mono right" data-sort="${{r.msgs}}">${{fmtNum(r.msgs)}}</td>
    <td class="mono right" data-sort="${{r.inp}}">${{fmtNum(r.inp)}}</td>
    <td class="mono right" data-sort="${{r.out}}">${{fmtNum(r.out)}}</td>
    <td class="mono right" data-sort="${{r.total}}">${{fmtNum(r.total)}}</td>
  </tr>`).join("");
}}

// =========================================================================
// Sortable tables
// =========================================================================
function initSortable() {{
  document.querySelectorAll("table.sortable").forEach(table => {{
    table.querySelector("thead").addEventListener("click", e => {{
      const th = e.target.closest("th");
      if (!th) return;
      const headers = table.querySelectorAll("thead th");
      const colIdx = Array.from(headers).indexOf(th);
      const isNum = th.dataset.type === "number";
      const tbody = table.querySelector("tbody");
      const rows = Array.from(tbody.querySelectorAll("tr"));
      const wasAsc = th.classList.contains("sort-asc");
      headers.forEach(h => h.classList.remove("sort-asc", "sort-desc"));
      const dir = wasAsc ? -1 : 1;
      th.classList.add(dir === 1 ? "sort-asc" : "sort-desc");
      rows.sort((a, b) => {{
        const av = a.children[colIdx]?.dataset.sort || a.children[colIdx]?.textContent || "";
        const bv = b.children[colIdx]?.dataset.sort || b.children[colIdx]?.textContent || "";
        if (isNum) return (parseFloat(av) - parseFloat(bv)) * dir;
        return av.localeCompare(bv) * dir;
      }});
      rows.forEach(r => tbody.appendChild(r));
    }});
  }});
}}

// =========================================================================
// Render all
// =========================================================================
function renderAll() {{
  updateFilterStyles();
  renderSummaryCards();
  renderBarChart();
  renderDonutChart();
  renderProvDonutChart();
  renderTimeline();
  renderModelTable();
  renderProjectTable();
}}

// =========================================================================
// Init
// =========================================================================
initNav();
initFilterBar();
initSortable();
initLookbackSelect();

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

renderAll();
</script>
</body>
</html>"""
