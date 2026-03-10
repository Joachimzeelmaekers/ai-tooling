"""Cursor provider — reads from Cursor's state.vscdb (SQLite).

Cursor stores conversation data in cursorDiskKV:
  - composerData:<composerId> — sessions with conversation[], createdAt, forceMode
  - bubbleId:<composerId>:<bubbleId> — individual messages with tokenCount

Model info is not stored locally. The user's configured model is used for pricing.
Tab completions are tracked server-side only (not available locally).
"""

import json
import os
import sqlite3

from .base import TokenMessage, ProviderResult

CURSOR_DB = os.path.expanduser(
    "~/Library/Application Support/Cursor/User/globalStorage/state.vscdb"
)

PROVIDER_NAME = "cursor"


def load() -> ProviderResult:
    if not os.path.exists(CURSOR_DB):
        return ProviderResult(name=PROVIDER_NAME, source="not found")

    try:
        conn = sqlite3.connect(f"file:{CURSOR_DB}?mode=ro", uri=True)
    except Exception:
        return ProviderResult(name=PROVIDER_NAME, source="db error")

    messages = []
    session_ids = set()

    # -------------------------------------------------------------------------
    # Step 1: Load composer metadata (mode, timestamps)
    # -------------------------------------------------------------------------
    composers = {}  # composerId -> {created_at, mode, bubble_timestamps}

    rows = conn.execute(
        "SELECT key, value FROM cursorDiskKV WHERE key LIKE 'composerData:%'"
    ).fetchall()

    for key, value in rows:
        if value is None:
            continue
        try:
            d = json.loads(value)
        except Exception:
            continue

        cid = d.get("composerId", key.split(":", 1)[1])
        created_at = d.get("createdAt", 0)
        mode = d.get("forceMode", "") or "default"
        session_ids.add(cid)

        # Build bubble -> timestamp map from conversation timingInfo
        bubble_ts = {}
        for msg in d.get("conversation", []):
            bid = msg.get("bubbleId", "")
            if bid:
                ti = msg.get("timingInfo")
                if ti:
                    ts = ti.get("clientStartTime", 0) or ti.get("clientEndTime", 0)
                    if ts:
                        bubble_ts[bid] = ts

        composers[cid] = {
            "created_at": created_at,
            "mode": mode,
            "bubble_ts": bubble_ts,
        }

    # -------------------------------------------------------------------------
    # Step 2: Load bubbles with token data
    # Key format: bubbleId:<composerId>:<bubbleId>
    # -------------------------------------------------------------------------
    rows = conn.execute(
        "SELECT key, value FROM cursorDiskKV WHERE key LIKE 'bubbleId:%'"
    ).fetchall()

    for key, value in rows:
        if value is None:
            continue
        try:
            d = json.loads(value)
        except Exception:
            continue

        tc = d.get("tokenCount")
        if not isinstance(tc, dict):
            continue
        inp = tc.get("inputTokens", 0)
        out = tc.get("outputTokens", 0)
        if inp + out == 0:
            continue

        # Parse key: bubbleId:<composerId>:<bubbleId>
        parts = key.split(":")
        composer_id = parts[1] if len(parts) >= 3 else ""
        bubble_id = parts[2] if len(parts) >= 3 else parts[1] if len(parts) >= 2 else ""

        comp = composers.get(composer_id, {})
        mode = comp.get("mode", "unknown")
        ts_ms = comp.get("bubble_ts", {}).get(bubble_id, 0) or comp.get("created_at", 0)

        messages.append(TokenMessage(
            provider=PROVIDER_NAME,
            model=f"cursor-{mode}",
            input_tokens=inp,
            output_tokens=out,
            reasoning_tokens=0,
            cache_read_tokens=0,
            cache_write_tokens=0,
            cost=0.0,
            timestamp_ms=ts_ms,
            session_id=composer_id,
            project="",
        ))

    conn.close()

    return ProviderResult(
        name=PROVIDER_NAME,
        messages=messages,
        sessions=len(session_ids),
        source="vscdb",
    )
