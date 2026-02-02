#!/usr/bin/env python3
import argparse
import csv
import json
import os
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


def write_csv(path, rows, headers):
    ensure_parent_dir(path)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(row)


def generate_plots(session_rows, day_rows, output_dir):
    svg_session = os.path.join(output_dir, "messages_per_session.svg")
    svg_day = os.path.join(output_dir, "messages_per_day.svg")
    ensure_parent_dir(svg_session)

    if session_rows:
        write_bar_svg(svg_session, session_rows, "Top sessions by prompt/answer pairs")
    if day_rows:
        write_line_svg(svg_day, day_rows, "Prompt/answer pairs per day")

    try:
        import matplotlib.pyplot as plt
    except Exception:
        return False

    if session_rows:
        labels = [row[0] for row in session_rows]
        values = [row[1] for row in session_rows]
        plt.figure(figsize=(12, 6))
        plt.barh(labels, values)
        plt.xlabel("pairs (approx messages/2)")
        plt.title("Top sessions by prompt/answer pairs")
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, "messages_per_session.png"))
        plt.close()

    if day_rows:
        labels = [row[0] for row in day_rows]
        values = [row[1] for row in day_rows]
        plt.figure(figsize=(12, 6))
        plt.plot(labels, values, marker="o")
        plt.xlabel("day")
        plt.ylabel("pairs (approx messages/2)")
        plt.title("Prompt/answer pairs per day")
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, "messages_per_day.png"))
        plt.close()

    return True


def write_bar_svg(path, rows, title):
    width = 1100
    bar_height = 22
    left_pad = 240
    right_pad = 40
    top_pad = 60
    bottom_pad = 40
    height = top_pad + len(rows) * (bar_height + 8) + bottom_pad
    max_value = max([r[1] for r in rows]) if rows else 1

    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">']
    lines.append('<rect width="100%" height="100%" fill="#ffffff"/>')
    lines.append(f'<text x="20" y="32" font-size="20" font-family="Arial" fill="#111">{title}</text>')
    lines.append(f'<text x="20" y="50" font-size="12" font-family="Arial" fill="#666">Pairs per session (top {len(rows)})</text>')

    chart_width = width - left_pad - right_pad
    y = top_pad
    for label, value in rows:
        bar_width = int(chart_width * (value / max_value))
        lines.append(f'<text x="20" y="{y + 15}" font-size="11" font-family="Arial" fill="#333">{escape_xml(truncate(label, 28))}</text>')
        lines.append(f'<rect x="{left_pad}" y="{y}" width="{bar_width}" height="{bar_height}" fill="#4C78A8" rx="3"/>')
        lines.append(f'<text x="{left_pad + bar_width + 6}" y="{y + 15}" font-size="11" font-family="Arial" fill="#333">{value}</text>')
        y += bar_height + 8

    lines.append(f'<line x1="{left_pad}" y1="{top_pad - 6}" x2="{left_pad}" y2="{height - bottom_pad}" stroke="#e0e0e0"/>')
    lines.append("</svg>")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def write_line_svg(path, rows, title):
    width = 1100
    height = 420
    left_pad = 70
    right_pad = 30
    top_pad = 60
    bottom_pad = 60
    max_value = max([r[1] for r in rows]) if rows else 1
    step = (width - left_pad - right_pad) / max(1, len(rows) - 1)
    points = []
    for idx, (_, value) in enumerate(rows):
        x = left_pad + idx * step
        y = height - bottom_pad - ((height - top_pad - bottom_pad) * (value / max_value))
        points.append((x, y))

    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">']
    lines.append('<rect width="100%" height="100%" fill="#ffffff"/>')
    lines.append(f'<text x="20" y="32" font-size="20" font-family="Arial" fill="#111">{title}</text>')
    lines.append(f'<text x="20" y="50" font-size="12" font-family="Arial" fill="#666">Pairs per day</text>')
    lines.append(f'<line x1="{left_pad}" y1="{height - bottom_pad}" x2="{width - right_pad}" y2="{height - bottom_pad}" stroke="#bdbdbd"/>')
    lines.append(f'<line x1="{left_pad}" y1="{top_pad}" x2="{left_pad}" y2="{height - bottom_pad}" stroke="#bdbdbd"/>')

    grid_lines = 4
    for i in range(1, grid_lines + 1):
        y = top_pad + (height - top_pad - bottom_pad) * (i / (grid_lines + 1))
        lines.append(f'<line x1="{left_pad}" y1="{y:.1f}" x2="{width - right_pad}" y2="{y:.1f}" stroke="#efefef"/>')

    if points:
        path_data = "M " + " L ".join([f"{x:.1f} {y:.1f}" for x, y in points])
        lines.append(f'<path d="{path_data}" fill="none" stroke="#F58518" stroke-width="2.5"/>')
        for x, y in points:
            lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="#F58518"/>')

    for idx, (label, _) in enumerate(rows):
        if idx % max(1, int(len(rows) / 8)) == 0:
            x = left_pad + idx * step
            lines.append(f'<text x="{x:.1f}" y="{height - bottom_pad + 24}" font-size="10" text-anchor="middle" font-family="Arial" fill="#444">{escape_xml(label)}</text>')

    lines.append(f'<text x="{left_pad}" y="{top_pad - 14}" font-size="10" font-family="Arial" fill="#444">max: {max_value}</text>')

    lines.append("</svg>")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def escape_xml(text):
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def truncate(text, limit):
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def main():
    parser = argparse.ArgumentParser(description="Generate stats and graphs from pairs.jsonl")
    parser.add_argument("--in", dest="input_path", default="output/pairs.jsonl")
    parser.add_argument("--out-dir", dest="output_dir", default="output")
    parser.add_argument("--top-sessions", type=int, default=20)
    args = parser.parse_args()

    input_path = os.path.expanduser(args.input_path)
    output_dir = os.path.expanduser(args.output_dir)
    pairs = load_pairs(input_path)
    if not pairs:
        raise SystemExit("No pairs found. Run export_pairs.py first.")

    sessions = Counter()
    days = Counter()
    sources = Counter()
    models = Counter()
    providers = Counter()
    agents = Counter()
    modes = Counter()
    tools = Counter()

    for row in pairs:
        session_id = row.get("session_id") or "unknown"
        sessions[session_id] += 1
        day = parse_day(row.get("prompt_time"))
        if day:
            days[day] += 1
        sources[row.get("source") or "unknown"] += 1
        if row.get("answer_model"):
            models[row.get("answer_model")] += 1
        if row.get("answer_provider"):
            providers[row.get("answer_provider")] += 1
        if row.get("answer_agent"):
            agents[row.get("answer_agent")] += 1
        if row.get("answer_mode"):
            modes[row.get("answer_mode")] += 1
        for tool in row.get("answer_tools") or []:
            tools[tool] += 1

    top_sessions = sessions.most_common(args.top_sessions)
    top_models = models.most_common(args.top_sessions)
    top_providers = providers.most_common(args.top_sessions)
    top_agents = agents.most_common(args.top_sessions)
    top_modes = modes.most_common(args.top_sessions)
    top_tools = tools.most_common(args.top_sessions)
    top_sources = sources.most_common(args.top_sessions)
    session_rows = [[sid, count] for sid, count in top_sessions]
    model_rows = [[name, count] for name, count in top_models]
    provider_rows = [[name, count] for name, count in top_providers]
    agent_rows = [[name, count] for name, count in top_agents]
    mode_rows = [[name, count] for name, count in top_modes]
    tool_rows = [[name, count] for name, count in top_tools]
    source_rows = [[name, count] for name, count in top_sources]
    day_rows = [[day, count] for day, count in sorted(days.items())]

    write_csv(os.path.join(output_dir, "messages_per_session.csv"), session_rows, ["session_id", "pairs"])
    write_csv(os.path.join(output_dir, "messages_per_day.csv"), day_rows, ["day", "pairs"])
    write_csv(os.path.join(output_dir, "pairs_per_model.csv"), model_rows, ["model", "pairs"])
    write_csv(os.path.join(output_dir, "pairs_per_provider.csv"), provider_rows, ["provider", "pairs"])
    write_csv(os.path.join(output_dir, "pairs_per_agent.csv"), agent_rows, ["agent", "pairs"])
    write_csv(os.path.join(output_dir, "pairs_per_mode.csv"), mode_rows, ["mode", "pairs"])
    write_csv(os.path.join(output_dir, "pairs_per_tool.csv"), tool_rows, ["tool", "pairs"])
    write_csv(os.path.join(output_dir, "pairs_per_source.csv"), source_rows, ["source", "pairs"])

    plotted = generate_plots(session_rows, day_rows, output_dir)
    if model_rows:
        write_bar_svg(os.path.join(output_dir, "pairs_per_model.svg"), model_rows, "Pairs by model")
    if provider_rows:
        write_bar_svg(os.path.join(output_dir, "pairs_per_provider.svg"), provider_rows, "Pairs by provider")
    if agent_rows:
        write_bar_svg(os.path.join(output_dir, "pairs_per_agent.svg"), agent_rows, "Pairs by agent")
    if mode_rows:
        write_bar_svg(os.path.join(output_dir, "pairs_per_mode.svg"), mode_rows, "Pairs by mode")
    if tool_rows:
        write_bar_svg(os.path.join(output_dir, "pairs_per_tool.svg"), tool_rows, "Pairs by tool")
    if source_rows:
        write_bar_svg(os.path.join(output_dir, "pairs_per_source.svg"), source_rows, "Pairs by source")
    if plotted:
        print(f"Wrote stats, SVG, and PNG graphs to {output_dir}")
    else:
        print(f"matplotlib not available; wrote CSV stats and SVG graphs to {output_dir}")


if __name__ == "__main__":
    main()
