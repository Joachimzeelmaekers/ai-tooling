"""OpenCode provider — reads from ~/.local/share/opencode/opencode.db or JSON fallback."""

import glob
import json
import os
import sqlite3

from .base import TokenMessage, ProviderResult

OPENCODE_DIR = os.path.expanduser("~/.local/share/opencode")
DB_PATH = os.path.join(OPENCODE_DIR, "opencode.db")
STORAGE_DIR = os.path.join(OPENCODE_DIR, "storage")

PROVIDER_NAME = "opencode"

# Models to exclude (local inference)
EXCLUDE_PATTERNS = ("mlx", "qwen")


def _load_sessions_sqlite():
    sessions = {}
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    for row in conn.execute("SELECT id, directory, title FROM session"):
        sessions[row[0]] = {"id": row[0], "directory": row[1], "title": row[2]}
    conn.close()
    return sessions


def _load_sessions_json():
    sessions = {}
    for f in glob.glob(f"{STORAGE_DIR}/session/**/*.json", recursive=True):
        try:
            d = json.load(open(f))
            sessions[d["id"]] = d
        except Exception:
            pass
    return sessions


def load() -> ProviderResult:
    if not os.path.exists(OPENCODE_DIR):
        return ProviderResult(name=PROVIDER_NAME, source="not found")

    # Load sessions
    sessions = {}
    if os.path.exists(DB_PATH):
        try:
            sessions = _load_sessions_sqlite()
        except Exception:
            sessions = _load_sessions_json()
    else:
        sessions = _load_sessions_json()

    # Load messages
    raw_messages = []
    source = "json"

    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
            for row in conn.execute("SELECT session_id, data FROM message"):
                d = json.loads(row[1])
                d["sessionID"] = row[0]
                if d.get("role") == "assistant" and "tokens" in d:
                    raw_messages.append(d)
            conn.close()
            source = "sqlite"
        except Exception:
            raw_messages = []

    if not raw_messages:
        for f in glob.glob(f"{STORAGE_DIR}/message/**/*.json", recursive=True):
            try:
                d = json.load(open(f))
                if d.get("role") == "assistant" and "tokens" in d:
                    raw_messages.append(d)
            except Exception:
                pass
        source = "json"

    # Normalize
    messages = []
    session_ids = set()
    for msg in raw_messages:
        provider_id = msg.get("providerID", "unknown")
        model_id = msg.get("modelID", "unknown")
        model_key = f"{provider_id}/{model_id}"

        if any(p in model_key.lower() for p in EXCLUDE_PATTERNS):
            continue

        t = msg["tokens"]
        ts_ms = msg.get("time", {}).get("created", 0)

        # Resolve project from message or session
        project = msg.get("path", {}).get("root") or ""
        if not project:
            sess = sessions.get(msg.get("sessionID", ""), {})
            project = sess.get("directory", "")

        sid = msg.get("sessionID", "")
        session_ids.add(sid)

        messages.append(TokenMessage(
            provider=PROVIDER_NAME,
            model=model_id,
            input_tokens=t.get("input", 0),
            output_tokens=t.get("output", 0),
            reasoning_tokens=t.get("reasoning", 0),
            cache_read_tokens=t.get("cache", {}).get("read", 0),
            cache_write_tokens=t.get("cache", {}).get("write", 0),
            cost=msg.get("cost", 0.0) or 0.0,
            timestamp_ms=ts_ms,
            session_id=sid,
            project=project,
        ))

    return ProviderResult(
        name=PROVIDER_NAME,
        messages=messages,
        sessions=len(session_ids),
        source=source,
    )
