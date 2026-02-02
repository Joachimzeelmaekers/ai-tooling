# Prompt Analysis

Analyze Claude and OpenCode session data for reusable rules and skill candidates.

## Usage

```bash
make all
```

Generate the HTML lab report:

```bash
python3 report_lab/main.py --in output/pairs.jsonl --out output/report.html --format html
```

Generate prompt/answer pairs with token counts:

```bash
python3 export_pairs/main.py --out output/pairs.jsonl
```

Chunk prompt/answer pairs into LLM-ready prompts:

```bash
python3 chunk_pairs/main.py --in output/pairs.jsonl --out output/chunks.jsonl
```

Generate stats and graphs:

```bash
python3 stats/main.py --in output/pairs.jsonl --out-dir output
```

Generate the Markdown report:

```bash
python3 report_lab/main.py --in output/pairs.jsonl --out output/report.md --format md
```

Notes:
- SVG graphs are always generated.
- PNG graphs are generated if matplotlib is installed.

## export_pairs/main.py flags

- `--out`: Output JSONL path (default: `output/pairs.jsonl`)
- `--model`: Tokenizer model name (uses tiktoken if available)
- `--encoding`: Tokenizer encoding name (fallback when model is unknown)
- `--include-tool-output`: Include tool outputs in prompt/answer text
- `--tool-output-max-len`: Max tool output length when included (default: 2000)
- `--include-system`: Include system-role messages (default: false)
- `--include-subagents`: Include Claude subagent sessions (default: false)
- `--include-suggestion-mode`: Include Suggestion Mode prompts (default: false)
- `--include-ide-events`: Include IDE event prompts (default: false)

## chunk_pairs/main.py flags

- `--in`: Input JSONL pairs file (default: `output/pairs.jsonl`)
- `--out`: Output JSONL chunks file (default: `output/chunks.jsonl`)
- `--max-total-tokens`: Max total tokens per chunk (default: 12000)
- `--max-pairs`: Max pairs per chunk (default: 80)
- `--include-times`: Include prompt/answer timestamps in chunks

## stats/main.py flags

- `--in`: Input JSONL pairs file (default: `output/pairs.jsonl`)
- `--out-dir`: Output directory (default: `output`)
- `--top-sessions`: Number of sessions to chart (default: 20)

## Notes

- Ignores tool output dumps and encrypted reasoning.
- Re-runnable without modifying source data.
