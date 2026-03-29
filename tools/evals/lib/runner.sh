#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/utils.sh"

# Setup an isolated eval environment.
# Args: eval_yaml harness_yaml
# Prints: path to the temp dir
setup_eval_env() {
    local eval_yaml="$1"
    local harness_yaml="$2"

    local tmpdir
    tmpdir="$(make_temp_dir "eval")"

    # Init a git repo in the temp dir
    git -C "$tmpdir" init -q
    git -C "$tmpdir" config user.email "eval@localhost"
    git -C "$tmpdir" config user.name "eval-harness"

    # Create files defined in the eval YAML
    local in_files=0
    local current_path=""
    local collecting_content=0
    local content_file=""

    while IFS= read -r line; do
        # Detect file path entries
        if [[ "$line" =~ ^[[:space:]]*-[[:space:]]*path:[[:space:]]*(.*) ]]; then
            # Flush previous file
            if [[ -n "$current_path" && -n "$content_file" ]]; then
                mkdir -p "$(dirname "${tmpdir}/${current_path}")"
                cp "$content_file" "${tmpdir}/${current_path}"
                rm -f "$content_file"
            fi
            current_path="${BASH_REMATCH[1]}"
            collecting_content=0
            content_file=""
            continue
        fi

        if [[ "$line" =~ ^[[:space:]]*content:[[:space:]]*\|[[:space:]]*$ ]]; then
            collecting_content=1
            content_file="$(mktemp)"
            continue
        fi

        if (( collecting_content )); then
            # Content lines are indented by at least 8 spaces under the YAML block
            if [[ "$line" =~ ^[[:space:]]{8}(.*) ]]; then
                echo "${BASH_REMATCH[1]}" >> "$content_file"
            elif [[ "$line" =~ ^[[:space:]]*$ ]]; then
                echo "" >> "$content_file"
            else
                collecting_content=0
                # Flush current file
                if [[ -n "$current_path" && -n "$content_file" ]]; then
                    mkdir -p "$(dirname "${tmpdir}/${current_path}")"
                    cp "$content_file" "${tmpdir}/${current_path}"
                    rm -f "$content_file"
                    current_path=""
                    content_file=""
                fi
            fi
        fi
    done < "$eval_yaml"

    # Flush last file if any
    if [[ -n "$current_path" && -n "$content_file" ]]; then
        mkdir -p "$(dirname "${tmpdir}/${current_path}")"
        cp "$content_file" "${tmpdir}/${current_path}"
        rm -f "$content_file"
    fi

    # Inject harness files
    local agents_md skills_dir hooks_dir memory_md
    agents_md="$(expand_path "$(yaml_val "$harness_yaml" "agents_md")")"
    skills_dir="$(expand_path "$(yaml_val "$harness_yaml" "skills_dir")")"
    hooks_dir="$(expand_path "$(yaml_val "$harness_yaml" "hooks_dir")")"
    memory_md="$(expand_path "$(yaml_val "$harness_yaml" "memory_md")")"

    if [[ -f "$agents_md" ]]; then
        cp "$agents_md" "${tmpdir}/AGENTS.md"
        log_dim "  Injected AGENTS.md from $agents_md"
    fi

    if [[ -d "$skills_dir" ]]; then
        cp -r "$skills_dir" "${tmpdir}/.skills"
        log_dim "  Injected skills from $skills_dir"
    fi

    if [[ -d "$hooks_dir" ]]; then
        mkdir -p "${tmpdir}/.claude"
        cp -r "$hooks_dir" "${tmpdir}/.claude/hooks"
        log_dim "  Injected hooks from $hooks_dir"
    fi

    if [[ -f "$memory_md" ]]; then
        cp "$memory_md" "${tmpdir}/MEMORY.md"
        log_dim "  Injected MEMORY.md from $memory_md"
    fi

    # Initial commit so the repo has a clean baseline
    git -C "$tmpdir" add -A
    git -C "$tmpdir" commit -q -m "eval: initial setup" --allow-empty

    echo "$tmpdir"
}

# Run the agent headlessly in the eval environment.
# Args: eval_dir prompt model agent max_turns
# Outputs: transcript to stdout
run_agent() {
    local eval_dir="$1"
    local prompt="$2"
    local model="${3:-sonnet}"
    local agent="${4:-claude}"
    local max_turns="${5:-20}"

    local start_time
    start_time="$(date +%s)"

    case "$agent" in
        claude)
            if ! command -v claude >/dev/null 2>&1; then
                log_error "claude CLI not found in PATH"
                echo '{"error": "claude CLI not found", "agent": "claude"}'
                return 1
            fi
            cd "$eval_dir"
            claude -p \
                --model "$model" \
                --max-turns "$max_turns" \
                --output-format json \
                <<< "$prompt" 2>/dev/null || true
            ;;
        opencode)
            if ! command -v opencode >/dev/null 2>&1; then
                log_error "opencode CLI not found in PATH"
                echo '{"error": "opencode CLI not found", "agent": "opencode"}'
                return 1
            fi
            cd "$eval_dir"
            echo "$prompt" | opencode run --json 2>/dev/null || true
            ;;
        codex)
            if ! command -v codex >/dev/null 2>&1; then
                log_error "codex CLI not found in PATH"
                echo '{"error": "codex CLI not found", "agent": "codex"}'
                return 1
            fi
            cd "$eval_dir"
            codex --quiet --json "$prompt" 2>/dev/null || true
            ;;
        *)
            die "Unknown agent: $agent"
            ;;
    esac

    local end_time
    end_time="$(date +%s)"
    local duration=$(( end_time - start_time ))
    echo "$duration" > "${eval_dir}/.eval_duration"
}

# Capture artifacts from a completed eval run.
# Args: eval_dir output_dir
capture_artifacts() {
    local eval_dir="$1"
    local output_dir="$2"

    mkdir -p "$output_dir"

    # Git diff from initial commit
    git -C "$eval_dir" diff HEAD~1..HEAD > "${output_dir}/diff.patch" 2>/dev/null || \
        git -C "$eval_dir" diff > "${output_dir}/diff.patch" 2>/dev/null || true

    # Full diff (staged + unstaged)
    git -C "$eval_dir" diff HEAD > "${output_dir}/diff-unstaged.patch" 2>/dev/null || true

    # Git log
    git -C "$eval_dir" log --oneline --all > "${output_dir}/git-log.txt" 2>/dev/null || true

    # List of changed files
    git -C "$eval_dir" diff --name-only HEAD~1..HEAD > "${output_dir}/files-changed.txt" 2>/dev/null || \
        git -C "$eval_dir" diff --name-only > "${output_dir}/files-changed.txt" 2>/dev/null || true

    # Duration
    if [[ -f "${eval_dir}/.eval_duration" ]]; then
        cp "${eval_dir}/.eval_duration" "${output_dir}/duration.txt"
    fi
}

# Cleanup the eval environment.
# Args: eval_dir
cleanup_eval_env() {
    local eval_dir="$1"
    if [[ -d "$eval_dir" && "$eval_dir" == *eval* ]]; then
        rm -rf "$eval_dir"
        log_dim "  Cleaned up $eval_dir"
    fi
}
