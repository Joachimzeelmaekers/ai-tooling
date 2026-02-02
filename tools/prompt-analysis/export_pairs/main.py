#!/usr/bin/env python3
import argparse
import json
import os
import re
from datetime import datetime


def expand_path(path):
    return os.path.expanduser(path)


def load_tokenizer(model=None, encoding_name=None):
    try:
        import tiktoken
    except Exception:
        return None
    if model:
        try:
            return tiktoken.encoding_for_model(model)
        except Exception:
            pass
    if encoding_name:
        try:
            return tiktoken.get_encoding(encoding_name)
        except Exception:
            pass
    for name in ("o200k_base", "cl100k_base"):
        try:
            return tiktoken.get_encoding(name)
        except Exception:
            continue
    return None


def count_tokens(text, tokenizer):
    if not text:
        return 0
    if tokenizer is None:
        return len(text.split())
    return len(tokenizer.encode(text))


def ensure_parent_dir(path):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def parse_iso(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def extract_claude_text(content, include_tool_output=False, max_tool_len=2000, include_ide_events=False):
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for item in content:
        if not isinstance(item, dict):
            continue
        typ = item.get("type")
        if typ == "text":
            text = item.get("text")
            if text:
                if not include_ide_events and "<ide_opened_file>" in text:
                    continue
                if text.strip().startswith("[Request interrupted by user for tool use]"):
                    continue
                parts.append(text)
            continue
        if typ == "tool_result" and include_tool_output:
            output = item.get("content")
            out_text = ""
            if isinstance(output, str):
                out_text = output
            elif isinstance(output, list):
                chunk = []
                for child in output:
                    if isinstance(child, dict):
                        if isinstance(child.get("text"), str):
                            chunk.append(child.get("text"))
                        if isinstance(child.get("content"), str):
                            chunk.append(child.get("content"))
                out_text = "\n".join(chunk)
            out_text = out_text.strip()
            if out_text:
                if max_tool_len > 0 and len(out_text) > max_tool_len:
                    out_text = out_text[:max_tool_len] + "..."
                parts.append("TOOL_OUTPUT: " + out_text)
    return "\n".join(parts)


def extract_claude_tools(content):
    if not isinstance(content, list):
        return []
    tools = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "tool_use":
            name = item.get("name")
            if isinstance(name, str) and name:
                tools.append(name)
    return tools


def load_claude_messages(root, include_tool_output=False, max_tool_len=2000, include_system=False, include_subagents=False, exclude_suggestion_mode=True, include_ide_events=False):
    messages = {}
    if not os.path.isdir(root):
        return messages
    for dirpath, _, filenames in os.walk(root):
        if not include_subagents and f"{os.sep}subagents{os.sep}" in dirpath:
            continue
        for name in filenames:
            if not name.endswith(".jsonl"):
                continue
            path = os.path.join(dirpath, name)
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    for line in handle:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                        except Exception:
                            continue
                        if not include_system and rec.get("type") not in ("user", "assistant"):
                            continue
                        msg = rec.get("message")
                        if not isinstance(msg, dict):
                            continue
                        role = msg.get("role")
                        if not include_system and role not in ("user", "assistant"):
                            continue
                        model = msg.get("model") if isinstance(msg.get("model"), str) else None
                        content = msg.get("content")
                        text = extract_claude_text(content, include_tool_output, max_tool_len, include_ide_events)
                        if exclude_suggestion_mode and text.lstrip().startswith("[SUGGESTION MODE:"):
                            continue
                        if not include_ide_events and "<ide_opened_file>" in text:
                            continue
                        if text.strip().startswith("[Request interrupted by user for tool use]"):
                            continue
                        tools = extract_claude_tools(content) if role == "assistant" else []
                        if not text.strip():
                            continue
                        session_id = rec.get("sessionId", "unknown")
                        ts = parse_iso(rec.get("timestamp"))
                        messages.setdefault(session_id, []).append(
                            {
                                "source": "claude",
                                "session_id": session_id,
                                "role": role,
                                "text": text,
                                "time": ts,
                                "title": None,
                                "model": model,
                                "provider": "claude" if model else None,
                                "agent": None,
                                "mode": None,
                                "tools": tools,
                            }
                        )
            except Exception:
                continue
    return messages


def load_opencode_session_titles(root):
    titles = {}
    if not os.path.isdir(root):
        return titles
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            if not name.endswith(".json"):
                continue
            path = os.path.join(dirpath, name)
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            if payload.get("id") and payload.get("title"):
                titles[payload.get("id")] = payload.get("title")
    return titles


def extract_opencode_parts(part_dir, message_id, include_tool_output=False, max_tool_len=2000):
    if not message_id:
        return ""
    dir_path = os.path.join(part_dir, message_id)
    if not os.path.isdir(dir_path):
        return ""
    files = [f for f in os.listdir(dir_path) if f.endswith(".json")]
    files.sort()
    parts = []
    for name in files:
        try:
            with open(os.path.join(dir_path, name), "r", encoding="utf-8") as handle:
                part = json.load(handle)
        except Exception:
            continue
        if not isinstance(part, dict):
            continue
        text_value = part.get("text")
        if part.get("type") == "text" and isinstance(text_value, str):
            text = text_value.strip()
            if text:
                parts.append(text)
            continue
        if part.get("type") == "tool" and include_tool_output:
            state = part.get("state", {})
            output = state.get("output") if isinstance(state, dict) else None
            if isinstance(output, str):
                out_text = output.strip()
                if out_text:
                    if max_tool_len > 0 and len(out_text) > max_tool_len:
                        out_text = out_text[:max_tool_len] + "..."
                    parts.append("TOOL_OUTPUT: " + out_text)
    return "\n".join(parts)


def load_opencode_messages(root, include_tool_output=False, max_tool_len=2000, include_system=False, exclude_suggestion_mode=True, include_ide_events=False):
    messages = {}
    storage_dir = os.path.join(root, "storage")
    message_dir = os.path.join(storage_dir, "message")
    part_dir = os.path.join(storage_dir, "part")
    titles = load_opencode_session_titles(os.path.join(storage_dir, "session"))
    if not os.path.isdir(message_dir):
        return messages
    for dirpath, _, filenames in os.walk(message_dir):
        for name in filenames:
            if not name.endswith(".json"):
                continue
            path = os.path.join(dirpath, name)
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    msg = json.load(handle)
            except Exception:
                continue
            if not isinstance(msg, dict):
                continue
            session_id = msg.get("sessionID", "unknown")
            role = msg.get("role")
            if not include_system and role not in ("user", "assistant"):
                continue
            message_id = msg.get("id")
            model_id = msg.get("modelID") or None
            provider_id = msg.get("providerID") or None
            if not model_id and isinstance(msg.get("model"), dict):
                model_id = msg.get("model", {}).get("modelID")
                provider_id = msg.get("model", {}).get("providerID")
            agent = msg.get("agent") or None
            mode = msg.get("mode") or None
            created = None
            time_block = msg.get("time", {}) if isinstance(msg.get("time"), dict) else {}
            created_ms = time_block.get("created")
            if isinstance(created_ms, int):
                created = datetime.fromtimestamp(created_ms / 1000.0)
            text = extract_opencode_parts(part_dir, message_id, include_tool_output, max_tool_len)
            if exclude_suggestion_mode and text.lstrip().startswith("[SUGGESTION MODE:"):
                continue
            if not include_ide_events and "<ide_opened_file>" in text:
                continue
            if text.strip().startswith("[Request interrupted by user for tool use]"):
                continue
            if not text.strip():
                continue
            messages.setdefault(session_id, []).append(
                {
                    "source": "opencode",
                    "session_id": session_id,
                    "role": role,
                    "text": text,
                    "time": created,
                    "title": titles.get(session_id),
                    "model": model_id,
                    "provider": provider_id,
                    "agent": agent,
                    "mode": mode,
                    "tools": [],
                }
            )
    return messages


def pair_messages(session_messages):
    pairs = []
    current_prompt = None
    prompt_time = None
    title = None
    prompt_meta = {}
    answer_parts = []
    answer_time = None
    answer_meta = {}
    for msg in session_messages:
        if msg.get("role") == "user":
            if current_prompt and answer_parts:
                pairs.append((current_prompt, "\n".join(answer_parts), prompt_time, answer_time, title, prompt_meta, answer_meta))
            current_prompt = msg.get("text")
            prompt_time = msg.get("time")
            title = msg.get("title")
            prompt_meta = {
                "source": msg.get("source"),
                "model": msg.get("model"),
                "provider": msg.get("provider"),
                "agent": msg.get("agent"),
                "mode": msg.get("mode"),
            }
            answer_parts = []
            answer_time = None
            answer_meta = {
                "model": None,
                "provider": None,
                "agent": None,
                "mode": None,
                "tools": set(),
            }
        elif msg.get("role") == "assistant" and current_prompt:
            answer_parts.append(msg.get("text", ""))
            answer_time = msg.get("time")
            if msg.get("model"):
                answer_meta["model"] = msg.get("model")
            if msg.get("provider"):
                answer_meta["provider"] = msg.get("provider")
            if msg.get("agent"):
                answer_meta["agent"] = msg.get("agent")
            if msg.get("mode"):
                answer_meta["mode"] = msg.get("mode")
            for tool in msg.get("tools", []):
                answer_meta["tools"].add(tool)
    if current_prompt and answer_parts:
        pairs.append((current_prompt, "\n".join(answer_parts), prompt_time, answer_time, title, prompt_meta, answer_meta))
    return pairs


def sort_messages(messages):
    def key(m):
        t = m.get("time")
        return t or datetime.min
    return sorted(messages, key=key)


def main():
    parser = argparse.ArgumentParser(description="Export prompt/answer pairs with token counts.")
    parser.add_argument("--claude-dir", default="~/.claude/projects")
    parser.add_argument("--opencode-dir", default="~/.local/share/opencode")
    parser.add_argument("--out", default="output/pairs.jsonl")
    parser.add_argument("--model", default="")
    parser.add_argument("--encoding", default="")
    parser.add_argument("--include-tool-output", action="store_true")
    parser.add_argument("--include-system", action="store_true")
    parser.add_argument("--include-subagents", action="store_true")
    parser.add_argument("--include-suggestion-mode", action="store_true")
    parser.add_argument("--include-ide-events", action="store_true")
    parser.add_argument("--tool-output-max-len", type=int, default=2000)
    args = parser.parse_args()

    claude_dir = expand_path(args.claude_dir)
    opencode_dir = expand_path(args.opencode_dir)
    out_path = expand_path(args.out)

    tokenizer = load_tokenizer(args.model, args.encoding)
    if tokenizer is None:
        print("tiktoken not available; using whitespace token counts", flush=True)

    claude_messages = load_claude_messages(
        claude_dir,
        args.include_tool_output,
        args.tool_output_max_len,
        args.include_system,
        args.include_subagents,
        not args.include_suggestion_mode,
        args.include_ide_events,
    )
    opencode_messages = load_opencode_messages(
        opencode_dir,
        args.include_tool_output,
        args.tool_output_max_len,
        args.include_system,
        not args.include_suggestion_mode,
        args.include_ide_events,
    )

    all_sessions = {}
    all_sessions.update(claude_messages)
    for key, value in opencode_messages.items():
        all_sessions.setdefault(key, []).extend(value)

    total_pairs = 0
    ensure_parent_dir(out_path)
    with open(out_path, "w", encoding="utf-8") as out:
        for session_id, msgs in all_sessions.items():
            msgs_sorted = sort_messages(msgs)
            pairs = pair_messages(msgs_sorted)
            for prompt, answer, pt, at, title, prompt_meta, answer_meta in pairs:
                prompt_tokens = count_tokens(prompt, tokenizer)
                answer_tokens = count_tokens(answer, tokenizer)
                tools = sorted(list(answer_meta.get("tools", [])))
                row = {
                    "session_id": session_id,
                    "session_title": title,
                    "source": prompt_meta.get("source"),
                    "prompt": prompt,
                    "answer": answer,
                    "prompt_tokens": prompt_tokens,
                    "answer_tokens": answer_tokens,
                    "total_tokens": prompt_tokens + answer_tokens,
                    "prompt_time": pt.isoformat() if pt else None,
                    "answer_time": at.isoformat() if at else None,
                    "prompt_model": prompt_meta.get("model"),
                    "prompt_provider": prompt_meta.get("provider"),
                    "answer_model": answer_meta.get("model"),
                    "answer_provider": answer_meta.get("provider"),
                    "answer_agent": answer_meta.get("agent"),
                    "answer_mode": answer_meta.get("mode"),
                    "answer_tools": tools,
                }
                out.write(json.dumps(row, ensure_ascii=True) + "\n")
                total_pairs += 1

    print(f"Wrote {total_pairs} prompt/answer pairs to {out_path}")


if __name__ == "__main__":
    main()
