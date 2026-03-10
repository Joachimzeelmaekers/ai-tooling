"""Codex CLI provider — reads from ~/.codex/sessions/ JSONL files.

Each session has:
  - session_meta: id, timestamp, cwd, model_provider, cli_version
  - event_msg with type=token_count: total_token_usage and last_token_usage
  - We use total_token_usage from the last token_count event per session
    (it's cumulative, so the final one has the full session total).
"""

import glob
import json
import os
from datetime import datetime, timezone

from .base import TokenMessage, ProviderResult

CODEX_DIR = os.path.expanduser("~/.codex")
SESSIONS_DIR = os.path.join(CODEX_DIR, "sessions")
CONFIG_FILE = os.path.join(CODEX_DIR, "config.toml")

PROVIDER_NAME = "codex"


def _get_configured_model() -> str:
    """Read model from config.toml."""
    if not os.path.exists(CONFIG_FILE):
        return "gpt-5.3-codex"
    try:
        with open(CONFIG_FILE) as f:
            for line in f:
                line = line.strip()
                if line.startswith("model") and "=" in line:
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return "gpt-5.3-codex"


def load() -> ProviderResult:
    if not os.path.exists(SESSIONS_DIR):
        return ProviderResult(name=PROVIDER_NAME, source="not found")

    model = _get_configured_model()
    files = glob.glob(f"{SESSIONS_DIR}/**/*.jsonl", recursive=True)

    messages = []
    session_ids = set()

    for filepath in files:
        meta = None
        last_total_usage = None

        with open(filepath) as f:
            for line in f:
                try:
                    d = json.loads(line)
                except Exception:
                    continue

                t = d.get("type")
                p = d.get("payload", {})

                if t == "session_meta":
                    meta = p
                elif t == "event_msg" and isinstance(p, dict) and p.get("type") == "token_count":
                    info = p.get("info")
                    if info and info.get("total_token_usage"):
                        last_total_usage = info["total_token_usage"]

        if not meta or not last_total_usage:
            continue

        sid = meta.get("id", "")
        session_ids.add(sid)

        ts_ms = 0
        ts_str = meta.get("timestamp", "")
        if ts_str:
            try:
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                ts_ms = int(dt.timestamp() * 1000)
            except Exception:
                pass

        project = meta.get("cwd", "")

        inp = last_total_usage.get("input_tokens", 0)
        out = last_total_usage.get("output_tokens", 0)
        cached = last_total_usage.get("cached_input_tokens", 0)
        reasoning = last_total_usage.get("reasoning_output_tokens", 0)

        messages.append(TokenMessage(
            provider=PROVIDER_NAME,
            model=model,
            input_tokens=inp,
            output_tokens=out,
            reasoning_tokens=reasoning,
            cache_read_tokens=cached,
            cache_write_tokens=0,
            cost=0.0,
            timestamp_ms=ts_ms,
            session_id=sid,
            project=project,
        ))

    return ProviderResult(
        name=PROVIDER_NAME,
        messages=messages,
        sessions=len(session_ids),
        source="jsonl",
    )
