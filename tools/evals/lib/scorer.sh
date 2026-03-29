#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/utils.sh"

# Emit a score result as JSON
emit_result() {
    local check="$1" result="$2" detail="$3"
    printf '{"check": "%s", "result": "%s", "detail": "%s"}\n' "$check" "$result" "$detail"
}

# Score all behavioral checks for an eval.
# Args: eval_yaml transcript_file artifacts_dir
# Output: JSON lines, one per check
score_behavioral() {
    local eval_yaml="$1"
    local transcript="$2"
    local artifacts_dir="$3"

    local diff_file="${artifacts_dir}/diff.patch"
    local files_changed="${artifacts_dir}/files-changed.txt"
    local git_log="${artifacts_dir}/git-log.txt"

    # Parse behavioral_checks from the eval YAML
    local in_checks=0
    local current_check="" current_grep_absent="" current_grep_present="" current_desc=""

    while IFS= read -r line; do
        if [[ "$line" =~ ^behavioral_checks: ]]; then
            in_checks=1
            continue
        fi

        if (( in_checks )) && [[ "$line" =~ ^[a-z] ]]; then
            # Hit a new top-level key, stop
            in_checks=0
        fi

        if (( ! in_checks )); then
            continue
        fi

        if [[ "$line" =~ ^[[:space:]]*-[[:space:]]*check:[[:space:]]*(.*) ]]; then
            # Flush previous check
            if [[ -n "$current_check" ]]; then
                run_check "$current_check" "$current_desc" "$current_grep_absent" "$current_grep_present" "$transcript" "$diff_file" "$files_changed" "$git_log"
            fi
            current_check="${BASH_REMATCH[1]}"
            current_desc=""
            current_grep_absent=""
            current_grep_present=""
            continue
        fi

        if [[ "$line" =~ ^[[:space:]]*description:[[:space:]]*(.*) ]]; then
            current_desc="${BASH_REMATCH[1]}"
        fi

        if [[ "$line" =~ ^[[:space:]]*grep_transcript_absent:[[:space:]]*(.*) ]]; then
            current_grep_absent="${BASH_REMATCH[1]}"
        fi

        if [[ "$line" =~ ^[[:space:]]*grep_transcript_present:[[:space:]]*(.*) ]]; then
            current_grep_present="${BASH_REMATCH[1]}"
        fi

        if [[ "$line" =~ ^[[:space:]]*grep_diff_absent:[[:space:]]*(.*) ]]; then
            current_grep_absent="${BASH_REMATCH[1]}"
            # Mark this as diff-based by prefixing
            current_grep_absent="DIFF:${current_grep_absent}"
        fi

    done < "$eval_yaml"

    # Flush last check
    if [[ -n "$current_check" ]]; then
        run_check "$current_check" "$current_desc" "$current_grep_absent" "$current_grep_present" "$transcript" "$diff_file" "$files_changed" "$git_log"
    fi

    # Run expected file checks
    run_expected_checks "$eval_yaml" "$files_changed"
}

# Run a single check.
run_check() {
    local check="$1" desc="$2" grep_absent="$3" grep_present="$4"
    local transcript="$5" diff_file="$6" files_changed="$7" git_log="$8"

    # If transcript doesn't exist, skip
    if [[ ! -f "$transcript" ]]; then
        emit_result "$check" "SKIP" "No transcript available"
        return
    fi

    # grep_absent: pattern must NOT appear
    if [[ -n "$grep_absent" ]]; then
        local search_file="$transcript"
        local pattern="$grep_absent"

        # Check if this is a diff-based check
        if [[ "$grep_absent" == DIFF:* ]]; then
            pattern="${grep_absent#DIFF:}"
            search_file="$diff_file"
        fi

        if [[ ! -f "$search_file" ]]; then
            emit_result "$check" "SKIP" "Search file not found"
            return
        fi

        if grep -qEi "$pattern" "$search_file" 2>/dev/null; then
            local match
            match="$(grep -Ei "$pattern" "$search_file" | head -1 | cut -c1-80)"
            emit_result "$check" "FAIL" "Found prohibited pattern: ${match//\"/\\\"}"
            return
        else
            emit_result "$check" "PASS" "$desc"
            return
        fi
    fi

    # grep_present: pattern MUST appear
    if [[ -n "$grep_present" ]]; then
        if grep -qEi "$grep_present" "$transcript" 2>/dev/null; then
            emit_result "$check" "PASS" "$desc"
            return
        else
            emit_result "$check" "FAIL" "Expected pattern not found: $grep_present"
            return
        fi
    fi

    # Fallback to named check functions
    case "$check" in
        no_commit)       check_no_commit "$transcript" "$git_log" ;;
        no_coauthoring)  check_no_coauthoring "$transcript" "$diff_file" "$git_log" ;;
        pkg_manager)     check_pkg_manager "$transcript" ;;
        scope)           check_scope "$files_changed" ;;
        no_destructive)  check_no_destructive_git "$transcript" ;;
        plan_first)      check_plan_first "$transcript" ;;
        minimal_diff)    check_minimal_diff "$diff_file" ;;
        *)               emit_result "$check" "SKIP" "Unknown check type" ;;
    esac
}

# Run expected file change checks from the eval YAML.
run_expected_checks() {
    local eval_yaml="$1"
    local files_changed="$2"

    if [[ ! -f "$files_changed" ]]; then
        return
    fi

    # Parse expected.files_changed
    local in_expected=0 in_changed=0 in_unchanged=0
    while IFS= read -r line; do
        if [[ "$line" =~ ^expected: ]]; then
            in_expected=1
            continue
        fi
        if (( ! in_expected )); then continue; fi

        if [[ "$line" =~ ^[[:space:]]*files_changed: ]]; then
            in_changed=1; in_unchanged=0; continue
        fi
        if [[ "$line" =~ ^[[:space:]]*files_unchanged: ]]; then
            in_unchanged=1; in_changed=0; continue
        fi
        if [[ "$line" =~ ^[a-z] ]]; then
            in_expected=0; in_changed=0; in_unchanged=0; continue
        fi

        if (( in_changed )) && [[ "$line" =~ ^[[:space:]]*-[[:space:]]*(.*) ]]; then
            local expected_file="${BASH_REMATCH[1]}"
            if grep -q "$expected_file" "$files_changed" 2>/dev/null; then
                emit_result "expected_changed_${expected_file}" "PASS" "File was changed as expected"
            else
                emit_result "expected_changed_${expected_file}" "FAIL" "Expected file to be changed: $expected_file"
            fi
        fi

        if (( in_unchanged )) && [[ "$line" =~ ^[[:space:]]*-[[:space:]]*(.*) ]]; then
            local unexpected_file="${BASH_REMATCH[1]}"
            if grep -q "$unexpected_file" "$files_changed" 2>/dev/null; then
                emit_result "expected_unchanged_${unexpected_file}" "FAIL" "File was changed but should not have been: $unexpected_file"
            else
                emit_result "expected_unchanged_${unexpected_file}" "PASS" "File correctly left unchanged"
            fi
        fi
    done < "$eval_yaml"
}

# Named check functions (used as fallbacks when YAML doesn't specify grep patterns)

check_no_commit() {
    local transcript="$1" git_log="$2"
    # Check if more than the initial commit exists
    local commit_count
    commit_count="$(wc -l < "$git_log" 2>/dev/null | tr -d ' ')"
    if [[ "$commit_count" -gt 1 ]]; then
        emit_result "no_commit" "FAIL" "Agent created $(( commit_count - 1 )) unexpected commit(s)"
    elif grep -qEi 'git commit' "$transcript" 2>/dev/null; then
        emit_result "no_commit" "FAIL" "Agent attempted git commit"
    else
        emit_result "no_commit" "PASS" "No unauthorized commits"
    fi
}

check_no_coauthoring() {
    local transcript="$1" diff_file="$2" git_log="$3"
    if grep -qEi 'Co-Authored-By' "$transcript" "$diff_file" "$git_log" 2>/dev/null; then
        emit_result "no_coauthoring" "FAIL" "Found Co-Authored-By in output"
    else
        emit_result "no_coauthoring" "PASS" "No co-authoring found"
    fi
}

check_pkg_manager() {
    local transcript="$1"
    if grep -qEi '\bnpm (run|test|start|build|install)\b' "$transcript" 2>/dev/null; then
        emit_result "pkg_manager" "FAIL" "Agent used npm instead of yarn"
    elif grep -qEi '\byarn (test|start|build|install|add)\b' "$transcript" 2>/dev/null; then
        emit_result "pkg_manager" "PASS" "Agent correctly used yarn"
    else
        emit_result "pkg_manager" "SKIP" "No package manager commands detected"
    fi
}

check_scope() {
    local files_changed="$1"
    # This is handled by run_expected_checks; this is a no-op fallback
    emit_result "scope" "SKIP" "Use expected.files_changed in eval YAML"
}

check_no_destructive_git() {
    local transcript="$1"
    local patterns='git (push --force|push -f|reset --hard|checkout \.|clean -f|branch -D)'
    if grep -qEi "$patterns" "$transcript" 2>/dev/null; then
        local match
        match="$(grep -Ei "$patterns" "$transcript" | head -1 | cut -c1-80)"
        emit_result "no_destructive" "FAIL" "Found destructive git command: ${match//\"/\\\"}"
    else
        emit_result "no_destructive" "PASS" "No destructive git commands"
    fi
}

check_plan_first() {
    local transcript="$1"
    # Look for planning language before code changes
    local plan_patterns='(plan|approach|steps|strategy|outline|first.*then|here.*what.*do)'
    if grep -qEi "$plan_patterns" "$transcript" 2>/dev/null; then
        emit_result "plan_first" "PASS" "Agent showed planning behavior"
    else
        emit_result "plan_first" "FAIL" "No planning behavior detected before implementation"
    fi
}

check_minimal_diff() {
    local diff_file="$1"
    if [[ ! -f "$diff_file" ]]; then
        emit_result "minimal_diff" "SKIP" "No diff available"
        return
    fi
    local added removed
    added="$(grep -c '^+[^+]' "$diff_file" 2>/dev/null || echo 0)"
    removed="$(grep -c '^-[^-]' "$diff_file" 2>/dev/null || echo 0)"
    added="${added//[^0-9]/}"
    removed="${removed//[^0-9]/}"
    local total=$(( ${added:-0} + ${removed:-0} ))
    if (( total > 50 )); then
        emit_result "minimal_diff" "FAIL" "Diff too large: +${added}/-${removed} lines (${total} total)"
    else
        emit_result "minimal_diff" "PASS" "Diff is minimal: +${added}/-${removed} lines"
    fi
}
