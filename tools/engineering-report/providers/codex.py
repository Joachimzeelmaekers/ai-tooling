"""Codex CLI provider — reads from Codex session JSONL files.

Each session has:
  - session_meta: id, timestamp, cwd, model_provider, cli_version
  - event_msg with type=token_count: total_token_usage and last_token_usage

Token totals are computed by summing per-turn `last_token_usage` deltas. This
is more robust than reading the final `total_token_usage`: it tolerates
truncated sessions and any future Codex change to the cumulative semantics.

Model attribution is "sticky": once a session has been recorded in a prior
snapshot, that model is reused. config.toml is only consulted for sessions
the snapshot has never seen. Without this, every config.toml change
re-stamps all historical sessions with the new model — and the merge layer
then keeps both attributions side by side.
"""

import glob
import json
import os
from datetime import datetime, timezone

from .base import TokenMessage, ProviderResult

PROVIDER_NAME = "codex"

_DEFAULT_MODEL = "gpt-5.3-codex"


def _installation_dirs() -> list[str]:
    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, ".codex"),
        os.path.join(home, ".codex-local"),
        os.path.join(home, "codex"),
        os.path.join(home, "codex-local"),
        os.path.join(home, ".config", "codex"),
        os.path.join(home, ".local", "share", "codex"),
    ]
    return [p for p in sorted(set(candidates)) if os.path.exists(p)]


def _get_configured_model(config_file: str) -> str:
    """Read model from config.toml."""
    if not os.path.exists(config_file):
        return _DEFAULT_MODEL
    try:
        with open(config_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("model") and "=" in line:
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return _DEFAULT_MODEL


def _load_prior_session_models() -> dict[str, str]:
    """Map session_id -> model from the latest snapshot, for sticky attribution."""
    snapshots_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "snapshots",
    )
    snapshots = sorted(glob.glob(os.path.join(snapshots_dir, "*.json")))
    if not snapshots:
        return {}
    try:
        with open(snapshots[-1]) as f:
            snap = json.load(f)
    except Exception:
        return {}
    out = {}
    for msg in snap.get(PROVIDER_NAME, {}).get("messages", []):
        sid = msg.get("session_id")
        model = msg.get("model")
        if sid and model and sid not in out:
            out[sid] = model
    return out


def load() -> ProviderResult:
    install_dirs = _installation_dirs()
    if not install_dirs:
        return ProviderResult(name=PROVIDER_NAME, source="not found")

    prior_models = _load_prior_session_models()

    messages = []
    session_ids = set()

    files = []
    models_by_root = {}
    for root in install_dirs:
        models_by_root[root] = _get_configured_model(os.path.join(root, "config.toml"))
        files.extend(glob.glob(os.path.join(root, "sessions", "**", "*.jsonl"), recursive=True))
        files.extend(glob.glob(os.path.join(root, "projects", "**", "*.jsonl"), recursive=True))
    files = sorted(set(files))

    for filepath in files:
        root = ""
        for r in install_dirs:
            if filepath.startswith(r):
                root = r
                break
        config_model = models_by_root.get(root, _DEFAULT_MODEL)

        meta = None
        first_event_model = None
        sum_input = 0
        sum_output = 0
        sum_cached = 0
        sum_reasoning = 0
        any_token_event = False

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
                    info = p.get("info") or {}
                    last = info.get("last_token_usage") or {}
                    if last:
                        any_token_event = True
                        sum_input += last.get("input_tokens", 0) or 0
                        sum_output += last.get("output_tokens", 0) or 0
                        sum_cached += last.get("cached_input_tokens", 0) or 0
                        sum_reasoning += last.get("reasoning_output_tokens", 0) or 0
                elif t == "event_msg" and isinstance(p, dict) and p.get("type") == "agent_message":
                    if first_event_model is None:
                        candidate = p.get("model") or p.get("modelId")
                        if candidate:
                            first_event_model = candidate

        if not meta and not any_token_event:
            continue

        sid = (meta or {}).get("id", "") or os.path.splitext(os.path.basename(filepath))[0]
        session_ids.add(sid)

        # Sticky model attribution: snapshot first, then JSONL evidence, then config default.
        model = prior_models.get(sid) or first_event_model or config_model

        ts_ms = 0
        ts_str = (meta or {}).get("timestamp", "")
        if ts_str:
            try:
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                ts_ms = int(dt.timestamp() * 1000)
            except Exception:
                pass

        project = (meta or {}).get("cwd", "")

        messages.append(TokenMessage(
            provider=PROVIDER_NAME,
            model=model,
            input_tokens=sum_input,
            output_tokens=sum_output,
            reasoning_tokens=sum_reasoning,
            cache_read_tokens=sum_cached,
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
