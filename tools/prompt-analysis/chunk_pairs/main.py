#!/usr/bin/env python3
import argparse
import json
import os
from datetime import datetime, timezone


DEFAULT_TEMPLATE = """You are analyzing prompt/answer pairs from an AI coding assistant.
Your tasks:
1) Identify instructions that should become durable rules in AGENTS.md or CLAUDE.md.
2) Identify repeated workflows that should become skills (slash commands).
3) Flag any corrections or constraints that should be enforced globally.

Return JSON with keys:
{\n  \"rules\": [{\"text\": \"...\", \"reason\": \"...\"}],\n  \"skills\": [{\"name\": \"...\", \"reason\": \"...\"}],\n  \"notes\": [\"...\"]\n}
"""


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


def build_chunk_text(pairs, include_times=False):
    lines = [DEFAULT_TEMPLATE, "", "---", ""]
    for idx, row in enumerate(pairs, 1):
        lines.append(f"PAIR {idx}:")
        if include_times:
            lines.append(f"prompt_time: {row.get('prompt_time')}")
            lines.append(f"answer_time: {row.get('answer_time')}")
        lines.append("PROMPT:")
        lines.append(row.get("prompt", ""))
        lines.append("ANSWER:")
        lines.append(row.get("answer", ""))
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def ensure_parent_dir(path):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Chunk prompt/answer pairs into LLM-ready prompts.")
    parser.add_argument("--in", dest="input_path", default="output/pairs.jsonl")
    parser.add_argument("--out", dest="output_path", default="output/chunks.jsonl")
    parser.add_argument("--max-total-tokens", type=int, default=12000)
    parser.add_argument("--max-pairs", type=int, default=80)
    parser.add_argument("--include-times", action="store_true")
    args = parser.parse_args()

    input_path = os.path.expanduser(args.input_path)
    output_path = os.path.expanduser(args.output_path)
    pairs = load_pairs(input_path)
    if not pairs:
        raise SystemExit("No pairs found. Run export_pairs.py first.")

    chunks = []
    current = []
    current_tokens = 0
    chunk_id = 1

    for row in pairs:
        total_tokens = row.get("total_tokens") or 0
        if current and (current_tokens + total_tokens > args.max_total_tokens or len(current) >= args.max_pairs):
            chunks.append((chunk_id, current, current_tokens))
            chunk_id += 1
            current = []
            current_tokens = 0
        current.append(row)
        current_tokens += total_tokens

    if current:
        chunks.append((chunk_id, current, current_tokens))

    ensure_parent_dir(output_path)
    with open(output_path, "w", encoding="utf-8") as out:
        for cid, rows, token_sum in chunks:
            chunk_text = build_chunk_text(rows, args.include_times)
            payload = {
                "chunk_id": cid,
                "pair_count": len(rows),
                "token_sum": token_sum,
                "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "prompt": chunk_text,
            }
            out.write(json.dumps(payload, ensure_ascii=True) + "\n")

    print(f"Wrote {len(chunks)} chunks to {output_path}")


if __name__ == "__main__":
    main()
