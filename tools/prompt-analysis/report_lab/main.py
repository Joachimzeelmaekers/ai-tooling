#!/usr/bin/env python3
import argparse
import json
import os
import re
from collections import Counter
from datetime import datetime


def ensure_parent_dir(path):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def load_pairs(path):
    pairs = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                pairs.append(json.loads(line))
            except Exception:
                continue
    return pairs


def parse_day(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).date().isoformat()
    except Exception:
        return None


def quantiles(values, qs):
    if not values:
        return {q: 0 for q in qs}
    values = sorted(values)
    out = {}
    for q in qs:
        idx = int((len(values) - 1) * q)
        out[q] = values[idx]
    return out


def normalize_sentence(s):
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def split_sentences(text):
    parts = re.split(r"[\.!?\n]+", text)
    return [p.strip() for p in parts if p.strip()]


def ascii_bar(value, max_value, width=30):
    if max_value <= 0:
        return ""
    filled = int(width * (value / max_value))
    return "#" * filled + "-" * (width - filled)


def collect_metrics(pairs):
    prompt_tokens = [p.get("prompt_tokens", 0) for p in pairs]
    answer_tokens = [p.get("answer_tokens", 0) for p in pairs]
    total_tokens = [p.get("total_tokens", 0) for p in pairs]

    session_counts = Counter()
    day_counts = Counter()
    prompt_starts = Counter()
    rule_candidates = Counter()
    correction_hits = 0
    skill_mentions = Counter()

    rule_regex = re.compile(r"\b(must|should|always|never|avoid|prefer|only|do not|don't|cannot|can't|require|required|forbid|forbidden)\b", re.I)
    correction_regex = re.compile(r"\b(actually|wait|undo|no,|that's wrong|wrong)\b", re.I)
    skill_regex = re.compile(r"(?m)(?:^|\s)(/[a-z][a-z0-9-]{1,30})\b")

    for row in pairs:
        session_id = row.get("session_id") or "unknown"
        session_counts[session_id] += 1
        day = parse_day(row.get("prompt_time"))
        if day:
            day_counts[day] += 1

        prompt = row.get("prompt", "") or ""
        first_line = prompt.strip().split("\n", 1)[0].strip()
        if first_line:
            prompt_starts[first_line[:80]] += 1

        if correction_regex.search(prompt):
            correction_hits += 1

        for match in skill_regex.findall(prompt):
            skill_mentions[match] += 1

        sentences = split_sentences(prompt)
        for s in sentences:
            if len(s) < 12 or len(s) > 240:
                continue
            if rule_regex.search(s):
                rule_candidates[normalize_sentence(s)] += 1

    return {
        "total_pairs": len(pairs),
        "prompt_tokens": prompt_tokens,
        "answer_tokens": answer_tokens,
        "total_tokens": total_tokens,
        "session_counts": session_counts,
        "day_counts": day_counts,
        "prompt_starts": prompt_starts,
        "rule_candidates": rule_candidates,
        "correction_hits": correction_hits,
        "skill_mentions": skill_mentions,
    }


def render_markdown(metrics, out_path):
    ensure_parent_dir(out_path)
    prompt_q = quantiles(metrics["prompt_tokens"], [0.5, 0.9, 0.99])
    answer_q = quantiles(metrics["answer_tokens"], [0.5, 0.9, 0.99])
    total_q = quantiles(metrics["total_tokens"], [0.5, 0.9, 0.99])

    top_sessions = metrics["session_counts"].most_common(15)
    top_days = sorted(metrics["day_counts"].items())
    top_prompts = metrics["prompt_starts"].most_common(10)
    top_rules = metrics["rule_candidates"].most_common(12)
    top_skills = metrics["skill_mentions"].most_common(10)

    max_day = max([count for _, count in top_days], default=0)

    lines = []
    lines.append("# Lab Report: Prompt/Answer Dataset")
    lines.append("")
    lines.append(f"Generated: {datetime.now().isoformat()}")
    lines.append("")
    lines.append("## Overview")
    lines.append(f"- Total prompt/answer pairs: {metrics['total_pairs']}")
    lines.append(f"- Total prompt tokens: {sum(metrics['prompt_tokens'])}")
    lines.append(f"- Total answer tokens: {sum(metrics['answer_tokens'])}")
    lines.append(f"- Total tokens: {sum(metrics['total_tokens'])}")
    lines.append("")

    lines.append("## Token Distribution")
    lines.append("Prompt tokens (median / p90 / p99): " + f"{prompt_q[0.5]} / {prompt_q[0.9]} / {prompt_q[0.99]}")
    lines.append("Answer tokens (median / p90 / p99): " + f"{answer_q[0.5]} / {answer_q[0.9]} / {answer_q[0.99]}")
    lines.append("Total tokens (median / p90 / p99): " + f"{total_q[0.5]} / {total_q[0.9]} / {total_q[0.99]}")
    lines.append("")

    lines.append("## Activity Over Time (pairs/day)")
    for day, count in top_days:
        bar = ascii_bar(count, max_day)
        lines.append(f"- {day} | {count:4d} | {bar}")
    lines.append("")

    lines.append("## Charts")
    lines.append("- messages per session: `output/messages_per_session.svg`")
    lines.append("- messages per day: `output/messages_per_day.svg`")
    lines.append("")

    lines.append("## Top Sessions (by pairs)")
    for session_id, count in top_sessions:
        lines.append(f"- {session_id} | {count}")
    lines.append("")

    lines.append("## Prompt Starters (top 10)")
    for text, count in top_prompts:
        lines.append(f"- {text} | {count}")
    lines.append("")

    lines.append("## Candidate Global Rules (heuristic)")
    if top_rules:
        for text, count in top_rules:
            lines.append(f"- {text} | {count}")
    else:
        lines.append("- none detected")
    lines.append("")

    lines.append("## Skill Mentions (slash commands)")
    if top_skills:
        for name, count in top_skills:
            lines.append(f"- {name} | {count}")
    else:
        lines.append("- none detected")
    lines.append("")

    lines.append("## Corrections and Constraints")
    lines.append(f"- Prompts containing correction language: {metrics['correction_hits']}")
    lines.append("")

    lines.append("## Recommendations")
    lines.append("- Convert repeated rule-like prompts into AGENTS.md or CLAUDE.md entries.")
    lines.append("- Promote frequently referenced slash commands into skills if not already present.")
    lines.append("- Use the top prompt starters list to create template skills or prompts.")
    lines.append("")

    lines.append("## Methodology")
    lines.append("- Parsed prompt/answer pairs from pairs.jsonl.")
    lines.append("- Token counts derived from the dataset (tiktoken if available, whitespace fallback).")
    lines.append("- Rule candidates detected via modal keyword heuristics.")
    lines.append("- Skill mentions detected via slash command regex.")
    lines.append("")

    lines.append("## Limitations")
    lines.append("- Heuristic rule detection may include false positives.")
    lines.append("- Token counts are approximate if tiktoken was unavailable.")
    lines.append("- Multi-turn context is not reconstructed beyond prompt/answer pairs.")
    lines.append("")

    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def render_html(metrics, out_path, assets_dir):
    ensure_parent_dir(out_path)
    prompt_q = quantiles(metrics["prompt_tokens"], [0.5, 0.9, 0.99])
    answer_q = quantiles(metrics["answer_tokens"], [0.5, 0.9, 0.99])
    total_q = quantiles(metrics["total_tokens"], [0.5, 0.9, 0.99])

    top_sessions = metrics["session_counts"].most_common(15)
    top_days = sorted(metrics["day_counts"].items())
    top_prompts = metrics["prompt_starts"].most_common(10)
    top_rules = metrics["rule_candidates"].most_common(12)
    top_skills = metrics["skill_mentions"].most_common(10)

    report_dir = os.path.dirname(out_path) or "."
    chart_map = {
        "Messages per session": os.path.join(assets_dir, "messages_per_session.svg"),
        "Messages per day": os.path.join(assets_dir, "messages_per_day.svg"),
        "Pairs per model": os.path.join(assets_dir, "pairs_per_model.svg"),
        "Pairs per provider": os.path.join(assets_dir, "pairs_per_provider.svg"),
        "Pairs per agent": os.path.join(assets_dir, "pairs_per_agent.svg"),
        "Pairs per mode": os.path.join(assets_dir, "pairs_per_mode.svg"),
        "Pairs per tool": os.path.join(assets_dir, "pairs_per_tool.svg"),
        "Pairs per source": os.path.join(assets_dir, "pairs_per_source.svg"),
    }
    charts = []
    for label, path in chart_map.items():
        if os.path.exists(path):
            charts.append((label, os.path.relpath(path, report_dir)))

    def list_items(items):
        return "\n".join([f"<li>{escape_html(text)} <span class=\"muted\">({count})</span></li>" for text, count in items])

    html = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Lab Report: Prompt/Answer Dataset</title>
  <style>
    :root {{
      --bg: #f7f7fb;
      --card: #ffffff;
      --text: #141419;
      --muted: #5b6270;
      --accent: #2f6fe4;
      --border: #e4e6ef;
    }}
    body {{
      margin: 0;
      font-family: "Inter", "Helvetica Neue", Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    header {{
      padding: 40px 8vw 24px;
      background: linear-gradient(120deg, #eef2ff 0%, #f7f7fb 60%);
      border-bottom: 1px solid var(--border);
    }}
    header h1 {{
      margin: 0 0 8px;
      font-size: 32px;
    }}
    header p {{
      margin: 0;
      color: var(--muted);
    }}
    main {{
      padding: 24px 8vw 48px;
      display: grid;
      gap: 20px;
    }}
    section {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 20px 24px;
      box-shadow: 0 10px 30px rgba(20, 20, 40, 0.06);
    }}
    h2 {{
      margin-top: 0;
      font-size: 20px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
    }}
    .metric {{
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 14px 16px;
      background: #fbfbff;
    }}
    .metric h3 {{
      margin: 0 0 6px;
      font-size: 14px;
      color: var(--muted);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    .metric p {{
      margin: 0;
      font-size: 18px;
      font-weight: 600;
    }}
    ul {{
      margin: 8px 0 0 18px;
    }}
    .muted {{
      color: var(--muted);
      font-size: 0.9em;
    }}
    .charts img {{
      width: 100%;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: #fff;
      padding: 8px;
    }}
  </style>
</head>
<body>
  <header>
    <h1>Lab Report: Prompt/Answer Dataset</h1>
    <p>Generated {escape_html(datetime.now().isoformat())}</p>
  </header>
  <main>
    <section>
      <h2>Overview</h2>
      <div class=\"grid\">
        <div class=\"metric\"><h3>Total pairs</h3><p>{metrics['total_pairs']}</p></div>
        <div class=\"metric\"><h3>Prompt tokens</h3><p>{sum(metrics['prompt_tokens'])}</p></div>
        <div class=\"metric\"><h3>Answer tokens</h3><p>{sum(metrics['answer_tokens'])}</p></div>
        <div class=\"metric\"><h3>Total tokens</h3><p>{sum(metrics['total_tokens'])}</p></div>
      </div>
    </section>
    <section>
      <h2>Token Distribution</h2>
      <ul>
        <li>Prompt tokens (median / p90 / p99): {prompt_q[0.5]} / {prompt_q[0.9]} / {prompt_q[0.99]}</li>
        <li>Answer tokens (median / p90 / p99): {answer_q[0.5]} / {answer_q[0.9]} / {answer_q[0.99]}</li>
        <li>Total tokens (median / p90 / p99): {total_q[0.5]} / {total_q[0.9]} / {total_q[0.99]}</li>
      </ul>
    </section>
    <section class=\"charts\">
      <h2>Charts</h2>
      {"".join([f'<img src="{escape_attr(path)}" alt="{escape_attr(label)}" />' for label, path in charts])}
    </section>
    <section>
      <h2>Top Sessions</h2>
      <ul>
        {list_items(top_sessions)}
      </ul>
    </section>
    <section>
      <h2>Prompt Starters</h2>
      <ul>
        {list_items(top_prompts)}
      </ul>
    </section>
    <section>
      <h2>Candidate Global Rules</h2>
      <ul>
        {list_items(top_rules) if top_rules else '<li>none detected</li>'}
      </ul>
    </section>
    <section>
      <h2>Skill Mentions</h2>
      <ul>
        {list_items(top_skills) if top_skills else '<li>none detected</li>'}
      </ul>
    </section>
    <section>
      <h2>Corrections and Constraints</h2>
      <p>Prompts containing correction language: <strong>{metrics['correction_hits']}</strong></p>
    </section>
    <section>
      <h2>Methodology</h2>
      <ul>
        <li>Parsed prompt/answer pairs from pairs.jsonl.</li>
        <li>Token counts derived from the dataset (tiktoken if available, whitespace fallback).</li>
        <li>Rule candidates detected via modal keyword heuristics.</li>
        <li>Skill mentions detected via slash command regex.</li>
      </ul>
      <p class=\"muted\">Heuristic rule detection may include false positives; multi-turn context is not reconstructed beyond pairs.</p>
    </section>
  </main>
</body>
</html>
"""

    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(html)


def escape_html(text):
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def escape_attr(text):
    return (
        text.replace("&", "&amp;")
        .replace("\"", "&quot;")
    )


def main():
    parser = argparse.ArgumentParser(description="Generate a lab-style report from pairs.jsonl")
    parser.add_argument("--in", dest="input_path", default="output/pairs.jsonl")
    parser.add_argument("--out", dest="output_path", default="output/report.html")
    parser.add_argument("--format", dest="format", default="html", choices=["html", "md"])
    parser.add_argument("--assets-dir", dest="assets_dir", default="output")
    args = parser.parse_args()

    input_path = os.path.expanduser(args.input_path)
    output_path = os.path.expanduser(args.output_path)
    assets_dir = os.path.expanduser(args.assets_dir)
    pairs = load_pairs(input_path)
    if not pairs:
        raise SystemExit("No pairs found. Run export_pairs.py first.")

    metrics = collect_metrics(pairs)
    if args.format == "md":
        render_markdown(metrics, output_path)
    else:
        render_html(metrics, output_path, assets_dir)
    print(f"Wrote lab report to {output_path}")


if __name__ == "__main__":
    main()
