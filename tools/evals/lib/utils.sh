#!/usr/bin/env bash
set -euo pipefail

# Colors (disabled when stdout is not a terminal)
if [[ -t 1 ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    BLUE='\033[0;34m'
    BOLD='\033[1m'
    DIM='\033[2m'
    RESET='\033[0m'
else
    RED='' GREEN='' YELLOW='' BLUE='' BOLD='' DIM='' RESET=''
fi

log_info()  { echo -e "${BLUE}[info]${RESET}  $*" >&2; }
log_ok()    { echo -e "${GREEN}[ok]${RESET}    $*" >&2; }
log_warn()  { echo -e "${YELLOW}[warn]${RESET}  $*" >&2; }
log_error() { echo -e "${RED}[error]${RESET} $*" >&2; }
log_dim()   { echo -e "${DIM}$*${RESET}" >&2; }

die() { log_error "$@"; exit 1; }

# Generate a run ID: YYYYMMDD-HHMMSS[-TAG]
generate_run_id() {
    local tag="${1:-}"
    local ts
    ts="$(date +%Y%m%d-%H%M%S)"
    if [[ -n "$tag" ]]; then
        echo "${ts}-${tag}"
    else
        echo "$ts"
    fi
}

# Create a temp directory, print its path
make_temp_dir() {
    local prefix="${1:-ai-eval}"
    mktemp -d "${TMPDIR:-/tmp}/${prefix}.XXXXXX"
}

# Remove a directory if it exists
cleanup_dir() {
    local dir="$1"
    if [[ -d "$dir" ]]; then
        rm -rf "$dir"
    fi
}

# Read a YAML value (simple key: value on its own line). Requires no deps beyond grep/sed.
yaml_val() {
    local file="$1" key="$2"
    grep "^${key}:" "$file" 2>/dev/null | sed "s/^${key}:[[:space:]]*//" | sed 's/[[:space:]]*$//'
}

# Read a YAML block (indented lines under a key). Returns lines without leading indent.
yaml_block() {
    local file="$1" key="$2"
    sed -n "/^${key}:/,/^[^[:space:]]/p" "$file" | tail -n +2 | grep '^  ' | sed 's/^  //'
}

# Emit a JSON key-value pair (strings only)
json_kv() {
    local key="$1" val="$2"
    printf '"%s": "%s"' "$key" "$val"
}

# Check if a command exists
require_cmd() {
    local cmd="$1"
    command -v "$cmd" >/dev/null 2>&1 || die "Required command not found: $cmd"
}

# Pretty-print a duration in seconds
format_duration() {
    local secs="$1"
    if (( secs < 60 )); then
        echo "${secs}s"
    elif (( secs < 3600 )); then
        echo "$(( secs / 60 ))m $(( secs % 60 ))s"
    else
        echo "$(( secs / 3600 ))h $(( (secs % 3600) / 60 ))m"
    fi
}

# Resolve ~ in paths
expand_path() {
    local p="$1"
    echo "${p/#\~/$HOME}"
}

# Print a fixed-width table row
table_row() {
    printf "%-35s %-8s %s\n" "$1" "$2" "${3:-}"
}

# Print a separator line
table_sep() {
    printf '%0.s-' {1..70}
    printf '\n'
}
