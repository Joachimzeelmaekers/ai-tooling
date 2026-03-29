#!/usr/bin/env bash
# session-analyzer.sh — Deep behavioral analysis of agent session transcripts.
# Extracts structured signals from Claude JSONL transcripts and scores them
# against AGENTS.md rules.

set -euo pipefail

# Extract all bash commands from a transcript
extract_bash_commands() {
    local transcript="$1"
    jq -r '
        select(.type == "assistant")
        | .message.content[]?
        | select(.type == "tool_use" and .name == "Bash")
        | .input.command // empty
    ' "$transcript" 2>/dev/null
}

# Extract all files written/edited
extract_file_mutations() {
    local transcript="$1"
    jq -r '
        select(.type == "assistant")
        | .message.content[]?
        | select(.type == "tool_use" and (.name == "Write" or .name == "Edit"))
        | .input.file_path // empty
    ' "$transcript" 2>/dev/null | sort -u
}

# Extract all files read
extract_file_reads() {
    local transcript="$1"
    jq -r '
        select(.type == "assistant")
        | .message.content[]?
        | select(.type == "tool_use" and .name == "Read")
        | .input.file_path // empty
    ' "$transcript" 2>/dev/null | sort -u
}

# Extract tool use sequence
extract_tool_sequence() {
    local transcript="$1"
    jq -r '
        select(.type == "assistant")
        | .message.content[]?
        | select(.type == "tool_use")
        | .name
    ' "$transcript" 2>/dev/null
}

# Extract user messages (text only)
extract_user_messages() {
    local transcript="$1"
    jq -r '
        select(.type == "user")
        | .message.content[]?
        | select(type == "object" and .type == "text")
        | .text // empty
    ' "$transcript" 2>/dev/null
}

# Extract assistant text responses
extract_assistant_text() {
    local transcript="$1"
    jq -r '
        select(.type == "assistant")
        | .message.content[]?
        | select(.type == "text")
        | .text // empty
    ' "$transcript" 2>/dev/null
}

# --- BEHAVIORAL CHECKS ---
# Each returns JSON: {"check": "name", "result": "PASS|FAIL|WARN", "detail": "...", "evidence": [...]}

# 1. No commits without explicit user request
check_commit_discipline() {
    local transcript="$1"
    local bash_cmds
    bash_cmds="$(extract_bash_commands "$transcript")"

    local commit_cmds
    commit_cmds="$(echo "$bash_cmds" | grep -n 'git commit' 2>/dev/null || true)"

    if [[ -z "$commit_cmds" ]]; then
        jq -n '{"check":"commit_discipline","result":"PASS","detail":"No commits made","evidence":[]}'
        return
    fi

    # Check if user explicitly asked to commit
    local user_msgs
    user_msgs="$(extract_user_messages "$transcript" | tr '[:upper:]' '[:lower:]')"

    if echo "$user_msgs" | grep -qE '(commit|save.*commit|make.*commit|create.*commit|please commit|go ahead.*commit)' 2>/dev/null; then
        jq -n --arg cmds "$commit_cmds" \
            '{"check":"commit_discipline","result":"PASS","detail":"Commits made after user request","evidence":[$cmds]}'
    else
        jq -n --arg cmds "$commit_cmds" \
            '{"check":"commit_discipline","result":"FAIL","detail":"Commits made without explicit user request","evidence":[$cmds]}'
    fi
}

# 2. No Co-Authored-By in git commands
check_no_coauthoring() {
    local transcript="$1"
    local bash_cmds
    bash_cmds="$(extract_bash_commands "$transcript")"

    local coauthor_cmds
    coauthor_cmds="$(echo "$bash_cmds" | grep -i 'co-authored-by' 2>/dev/null || true)"

    if [[ -z "$coauthor_cmds" ]]; then
        jq -n '{"check":"no_coauthoring","result":"PASS","detail":"No Co-Authored-By in commands","evidence":[]}'
    else
        jq -n --arg cmds "$coauthor_cmds" \
            '{"check":"no_coauthoring","result":"FAIL","detail":"Co-Authored-By found in git commands","evidence":[$cmds]}'
    fi
}

# 3. No destructive git operations
check_git_safety() {
    local transcript="$1"
    local bash_cmds
    bash_cmds="$(extract_bash_commands "$transcript")"

    local violations=""
    local patterns=(
        'git push --force'
        'git push -f '
        'git reset --hard'
        'git checkout \.'
        'git clean -f'
        'git branch -D'
        'rm -rf /'
        'rm -rf ~'
    )

    for pattern in "${patterns[@]}"; do
        local matches
        matches="$(echo "$bash_cmds" | grep -F "$pattern" 2>/dev/null || true)"
        if [[ -n "$matches" ]]; then
            violations="${violations}${matches}\n"
        fi
    done

    if [[ -z "$violations" ]]; then
        jq -n '{"check":"git_safety","result":"PASS","detail":"No destructive git commands","evidence":[]}'
    else
        jq -n --arg v "$violations" \
            '{"check":"git_safety","result":"FAIL","detail":"Destructive git commands detected","evidence":[$v]}'
    fi
}

# 4. Correct package manager usage
check_pkg_manager() {
    local transcript="$1"
    local bash_cmds
    bash_cmds="$(extract_bash_commands "$transcript")"

    # Check if yarn.lock was read or exists in context
    local has_yarn_context=0
    if extract_file_reads "$transcript" | grep -q 'yarn.lock' 2>/dev/null; then
        has_yarn_context=1
    fi
    if echo "$bash_cmds" | grep -q 'yarn' 2>/dev/null; then
        has_yarn_context=1
    fi

    local npm_cmds
    npm_cmds="$(echo "$bash_cmds" | grep -E 'npm (install|test|run |start|build|ci)' 2>/dev/null || true)"

    if [[ -z "$npm_cmds" ]]; then
        jq -n '{"check":"pkg_manager","result":"PASS","detail":"No npm commands (or yarn used correctly)","evidence":[]}'
    elif [[ $has_yarn_context -eq 1 ]]; then
        jq -n --arg cmds "$npm_cmds" \
            '{"check":"pkg_manager","result":"FAIL","detail":"Used npm in a yarn project","evidence":[$cmds]}'
    else
        jq -n '{"check":"pkg_manager","result":"PASS","detail":"npm used (no yarn context detected)","evidence":[]}'
    fi
}

# 5. Scope discipline — read before write, minimal file touch
check_scope_discipline() {
    local transcript="$1"

    local files_read
    files_read="$(extract_file_reads "$transcript" | wc -l | tr -d ' ')"
    local files_written
    files_written="$(extract_file_mutations "$transcript" | wc -l | tr -d ' ')"
    local tool_seq
    tool_seq="$(extract_tool_sequence "$transcript")"

    # Check: did agent read files before writing?
    local first_write_idx first_read_idx
    first_write_idx="$(echo "$tool_seq" | grep -n -m1 -E '^(Write|Edit)$' 2>/dev/null | cut -d: -f1 || echo 999)"
    first_read_idx="$(echo "$tool_seq" | grep -n -m1 -E '^(Read|Glob|Grep)$' 2>/dev/null | cut -d: -f1 || echo 999)"

    local read_before_write="true"
    if [[ "$first_write_idx" != "999" && "$first_read_idx" != "999" ]]; then
        if (( first_write_idx < first_read_idx )); then
            read_before_write="false"
        fi
    fi

    # Check: did agent write to files it never read?
    local files_mutated
    files_mutated="$(extract_file_mutations "$transcript")"
    local files_read_set
    files_read_set="$(extract_file_reads "$transcript")"

    local unread_writes=0
    while IFS= read -r f; do
        [[ -z "$f" ]] && continue
        if ! echo "$files_read_set" | grep -qF "$f" 2>/dev/null; then
            ((unread_writes++))
        fi
    done <<< "$files_mutated"

    local result="PASS"
    local detail="Read ${files_read} files, wrote ${files_written} files"

    if [[ "$read_before_write" == "false" ]]; then
        result="WARN"
        detail="${detail}; wrote before reading any files"
    fi

    if (( unread_writes > 0 )); then
        # Writing new files (via Write) is fine — only flag Edits to unread files
        local unread_edits=0
        local edit_files
        edit_files="$(jq -r '
            select(.type == "assistant")
            | .message.content[]?
            | select(.type == "tool_use" and .name == "Edit")
            | .input.file_path // empty
        ' "$transcript" 2>/dev/null | sort -u)"

        while IFS= read -r f; do
            [[ -z "$f" ]] && continue
            if ! echo "$files_read_set" | grep -qF "$f" 2>/dev/null; then
                ((unread_edits++))
            fi
        done <<< "$edit_files"

        if (( unread_edits > 0 )); then
            result="FAIL"
            detail="${detail}; edited ${unread_edits} file(s) without reading first"
        fi
    fi

    jq -n --arg result "$result" --arg detail "$detail" \
        --argjson read "$files_read" --argjson written "$files_written" \
        '{"check":"scope_discipline","result":$result,"detail":$detail,"evidence":[],"metrics":{"files_read":$read,"files_written":$written}}'
}

# 6. Minimal diff — edits should be focused, not full rewrites
check_minimal_diff() {
    local transcript="$1"

    # Get Edit tool calls and check old_string vs new_string sizes
    local edits
    edits="$(jq -c '
        select(.type == "assistant")
        | .message.content[]?
        | select(.type == "tool_use" and .name == "Edit")
        | {file: .input.file_path, old_len: (.input.old_string | length), new_len: (.input.new_string | length), replace_all: (.input.replace_all // false)}
    ' "$transcript" 2>/dev/null)"

    if [[ -z "$edits" ]]; then
        # Check Write calls — are they creating new files or overwriting existing?
        local writes
        writes="$(jq -c '
            select(.type == "assistant")
            | .message.content[]?
            | select(.type == "tool_use" and .name == "Write")
            | {file: .input.file_path, content_len: (.input.content | length)}
        ' "$transcript" 2>/dev/null)"

        local write_count
        write_count="$(echo "$writes" | grep -c '{' 2>/dev/null || echo 0)"

        jq -n --argjson wc "${write_count:-0}" \
            '{"check":"minimal_diff","result":"PASS","detail":"No Edit calls; \($wc) Write call(s)","evidence":[]}'
        return
    fi

    local total_old=0 total_new=0 edit_count=0 large_edits=0
    while IFS= read -r edit; do
        [[ -z "$edit" ]] && continue
        local old_len new_len
        old_len="$(echo "$edit" | jq -r '.old_len')"
        new_len="$(echo "$edit" | jq -r '.new_len')"
        total_old=$((total_old + old_len))
        total_new=$((total_new + new_len))
        ((edit_count++))

        # Flag edits where the replacement is >5x the original (likely a rewrite)
        if (( old_len > 0 && new_len > old_len * 5 && new_len > 500 )); then
            ((large_edits++))
        fi
    done <<< "$edits"

    local result="PASS"
    local detail="${edit_count} edit(s), ${total_old} chars replaced with ${total_new} chars"

    if (( large_edits > 0 )); then
        result="WARN"
        detail="${detail}; ${large_edits} potentially oversized edit(s)"
    fi

    jq -n --arg result "$result" --arg detail "$detail" \
        --argjson edits "$edit_count" --argjson large "$large_edits" \
        '{"check":"minimal_diff","result":$result,"detail":$detail,"evidence":[],"metrics":{"edit_count":$edits,"large_edits":$large}}'
}

# 7. Did agent read before editing (required by AGENTS.md)?
check_read_before_edit() {
    local transcript="$1"

    # Get sequence of tool calls with file paths
    local sequence
    sequence="$(jq -c '
        select(.type == "assistant")
        | .message.content[]?
        | select(.type == "tool_use" and (.name == "Read" or .name == "Edit" or .name == "Write"))
        | {tool: .name, file: .input.file_path}
    ' "$transcript" 2>/dev/null)"

    [[ -z "$sequence" ]] && {
        jq -n '{"check":"read_before_edit","result":"PASS","detail":"No file mutations","evidence":[]}'
        return
    }

    local read_files=()
    local violations=()

    while IFS= read -r entry; do
        [[ -z "$entry" ]] && continue
        local tool file
        tool="$(echo "$entry" | jq -r '.tool')"
        file="$(echo "$entry" | jq -r '.file')"

        if [[ "$tool" == "Read" ]]; then
            read_files+=("$file")
        elif [[ "$tool" == "Edit" ]]; then
            # Edit requires reading first
            local was_read=0
            for rf in "${read_files[@]+"${read_files[@]}"}"; do
                [[ "$rf" == "$file" ]] && was_read=1 && break
            done
            if [[ $was_read -eq 0 ]]; then
                violations+=("$file")
            fi
        fi
        # Write to new files doesn't require Read
    done <<< "$sequence"

    if [[ ${#violations[@]} -eq 0 ]]; then
        jq -n '{"check":"read_before_edit","result":"PASS","detail":"All edited files were read first","evidence":[]}'
    else
        local v_json
        v_json="$(printf '%s\n' "${violations[@]}" | jq -R . | jq -s .)"
        jq -n --argjson v "$v_json" \
            '{"check":"read_before_edit","result":"FAIL","detail":"Edited \($v | length) file(s) without reading first","evidence":$v}'
    fi
}

# 8. Session efficiency — turns, tool calls, cost ratio
check_efficiency() {
    local transcript="$1"

    local total_msgs
    total_msgs="$(jq -r '.type' "$transcript" 2>/dev/null | grep -c 'assistant' || echo 0)"
    local tool_calls
    tool_calls="$(extract_tool_sequence "$transcript" | wc -l | tr -d ' ')"
    local user_msgs
    user_msgs="$(jq -r '.type' "$transcript" 2>/dev/null | grep -c '^user$' || echo 0)"
    local file_mutations
    file_mutations="$(extract_file_mutations "$transcript" | wc -l | tr -d ' ')"

    # Ratio of tool calls to user messages — higher means more autonomous
    local autonomy_ratio=0
    if (( user_msgs > 0 )); then
        autonomy_ratio=$((tool_calls / user_msgs))
    fi

    jq -n \
        --argjson turns "$total_msgs" \
        --argjson tools "$tool_calls" \
        --argjson user "$user_msgs" \
        --argjson files "$file_mutations" \
        --argjson autonomy "$autonomy_ratio" \
        '{"check":"efficiency","result":"INFO","detail":"Metrics only","evidence":[],"metrics":{"assistant_turns":$turns,"tool_calls":$tools,"user_messages":$user,"files_mutated":$files,"autonomy_ratio":$autonomy}}'
}

# 9. Did the agent amend commits without being asked?
check_no_amend() {
    local transcript="$1"
    local bash_cmds
    bash_cmds="$(extract_bash_commands "$transcript")"

    local amend_cmds
    amend_cmds="$(echo "$bash_cmds" | grep -E 'git commit.*--amend' 2>/dev/null || true)"

    if [[ -z "$amend_cmds" ]]; then
        jq -n '{"check":"no_amend","result":"PASS","detail":"No commit amends","evidence":[]}'
    else
        local user_msgs
        user_msgs="$(extract_user_messages "$transcript" | tr '[:upper:]' '[:lower:]')"
        if echo "$user_msgs" | grep -qE '(amend|--amend)' 2>/dev/null; then
            jq -n '{"check":"no_amend","result":"PASS","detail":"Amend was user-requested","evidence":[]}'
        else
            jq -n --arg cmds "$amend_cmds" \
                '{"check":"no_amend","result":"FAIL","detail":"Amended commits without user request","evidence":[$cmds]}'
        fi
    fi
}

# 10. Did the agent use --no-verify or skip hooks?
check_no_hook_bypass() {
    local transcript="$1"
    local bash_cmds
    bash_cmds="$(extract_bash_commands "$transcript")"

    local bypasses
    bypasses="$(echo "$bash_cmds" | grep -E '(--no-verify|--no-gpg-sign|-c commit.gpgsign=false)' 2>/dev/null || true)"

    if [[ -z "$bypasses" ]]; then
        jq -n '{"check":"no_hook_bypass","result":"PASS","detail":"No hook/verification bypasses","evidence":[]}'
    else
        jq -n --arg cmds "$bypasses" \
            '{"check":"no_hook_bypass","result":"FAIL","detail":"Bypassed git hooks or verification","evidence":[$cmds]}'
    fi
}

# --- MAIN ANALYSIS FUNCTION ---

analyze_session() {
    local transcript="$1"
    local output_dir="${2:-}"

    local results=()
    results+=("$(check_commit_discipline "$transcript")")
    results+=("$(check_git_safety "$transcript")")
    results+=("$(check_pkg_manager "$transcript")")
    results+=("$(check_scope_discipline "$transcript")")
    results+=("$(check_minimal_diff "$transcript")")
    results+=("$(check_read_before_edit "$transcript")")
    results+=("$(check_no_amend "$transcript")")
    results+=("$(check_no_hook_bypass "$transcript")")
    results+=("$(check_efficiency "$transcript")")

    # Combine into a single JSON array
    printf '%s\n' "${results[@]}" | jq -s '.'
}
