#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/utils.sh"

# Print a summary table for a single run.
# Args: results_dir
print_summary() {
    local results_dir="$1"
    local summary_file="${results_dir}/summary.json"
    local meta_file="${results_dir}/meta.json"

    if [[ ! -f "$meta_file" ]]; then
        die "No meta.json found in $results_dir"
    fi

    echo ""
    echo -e "${BOLD}Eval Run Summary${RESET}"
    table_sep

    # Print metadata
    if command -v jq >/dev/null 2>&1 && [[ -f "$meta_file" ]]; then
        local run_id harness model suite ts
        run_id="$(jq -r '.run_id // "unknown"' "$meta_file")"
        harness="$(jq -r '.harness // "unknown"' "$meta_file")"
        model="$(jq -r '.model // "unknown"' "$meta_file")"
        suite="$(jq -r '.suite // "unknown"' "$meta_file")"
        ts="$(jq -r '.timestamp // "unknown"' "$meta_file")"
        echo -e "Run:     ${BOLD}${run_id}${RESET}"
        echo -e "Harness: ${harness}"
        echo -e "Model:   ${model}"
        echo -e "Suite:   ${suite}"
        echo -e "Time:    ${ts}"
    fi

    table_sep
    printf "${BOLD}%-35s %-8s %s${RESET}\n" "EVAL / CHECK" "RESULT" "DETAIL"
    table_sep

    local total_pass=0 total_fail=0 total_skip=0

    # Iterate over eval result directories
    if [[ -d "${results_dir}/evals" ]]; then
        for eval_dir in "${results_dir}/evals"/*/; do
            [[ -d "$eval_dir" ]] || continue
            local eval_name
            eval_name="$(basename "$eval_dir")"
            echo -e "${BOLD}${eval_name}${RESET}"

            local score_file="${eval_dir}/score.json"
            if [[ -f "$score_file" ]]; then
                while IFS= read -r line; do
                    local check result detail
                    check="$(echo "$line" | jq -r '.check // ""')"
                    result="$(echo "$line" | jq -r '.result // ""')"
                    detail="$(echo "$line" | jq -r '.detail // ""' | cut -c1-40)"

                    local color=""
                    case "$result" in
                        PASS) color="$GREEN"; (( total_pass++ )) ;;
                        FAIL) color="$RED"; (( total_fail++ )) ;;
                        SKIP) color="$YELLOW"; (( total_skip++ )) ;;
                    esac

                    printf "  %-33s ${color}%-8s${RESET} %s\n" "$check" "$result" "$detail"
                done < "$score_file"
            else
                printf "  %-33s ${YELLOW}%-8s${RESET} %s\n" "(no results)" "SKIP" "Score file missing"
                (( total_skip++ ))
            fi
        done
    fi

    table_sep
    echo -e "${GREEN}PASS: ${total_pass}${RESET}  ${RED}FAIL: ${total_fail}${RESET}  ${YELLOW}SKIP: ${total_skip}${RESET}"
    echo ""

    # Write summary JSON
    if command -v jq >/dev/null 2>&1; then
        jq -n \
            --argjson pass "$total_pass" \
            --argjson fail "$total_fail" \
            --argjson skip "$total_skip" \
            '{pass: $pass, fail: $fail, skip: $skip, total: ($pass + $fail + $skip)}' \
            > "$summary_file"
    fi
}

# Print a comparison between two runs.
# Args: results_dir1 results_dir2
print_comparison() {
    local dir1="$1" dir2="$2"

    local name1 name2
    name1="$(basename "$dir1")"
    name2="$(basename "$dir2")"

    echo ""
    echo -e "${BOLD}Comparison: ${name1} vs ${name2}${RESET}"
    table_sep
    printf "${BOLD}%-30s %-12s %-12s %s${RESET}\n" "CHECK" "$name1" "$name2" "DELTA"
    table_sep

    # Collect all checks from both runs
    local -A results1 results2

    if [[ -d "${dir1}/evals" ]]; then
        for eval_dir in "${dir1}/evals"/*/; do
            [[ -d "$eval_dir" ]] || continue
            local eval_name
            eval_name="$(basename "$eval_dir")"
            if [[ -f "${eval_dir}/score.json" ]]; then
                while IFS= read -r line; do
                    local check result
                    check="$(echo "$line" | jq -r '.check // ""')"
                    result="$(echo "$line" | jq -r '.result // ""')"
                    results1["${eval_name}/${check}"]="$result"
                done < "${eval_dir}/score.json"
            fi
        done
    fi

    if [[ -d "${dir2}/evals" ]]; then
        for eval_dir in "${dir2}/evals"/*/; do
            [[ -d "$eval_dir" ]] || continue
            local eval_name
            eval_name="$(basename "$eval_dir")"
            if [[ -f "${eval_dir}/score.json" ]]; then
                while IFS= read -r line; do
                    local check result
                    check="$(echo "$line" | jq -r '.check // ""')"
                    result="$(echo "$line" | jq -r '.result // ""')"
                    results2["${eval_name}/${check}"]="$result"
                done < "${eval_dir}/score.json"
            fi
        done
    fi

    # Merge all keys
    local -A all_keys
    for key in "${!results1[@]}"; do all_keys["$key"]=1; done
    for key in "${!results2[@]}"; do all_keys["$key"]=1; done

    local improved=0 regressed=0 unchanged=0

    for key in $(echo "${!all_keys[@]}" | tr ' ' '\n' | sort); do
        local r1="${results1[$key]:-N/A}"
        local r2="${results2[$key]:-N/A}"
        local delta=""

        if [[ "$r1" == "$r2" ]]; then
            delta="="
            (( unchanged++ ))
        elif [[ "$r1" == "FAIL" && "$r2" == "PASS" ]]; then
            delta="${GREEN}IMPROVED${RESET}"
            (( improved++ ))
        elif [[ "$r1" == "PASS" && "$r2" == "FAIL" ]]; then
            delta="${RED}REGRESSED${RESET}"
            (( regressed++ ))
        else
            delta="~"
            (( unchanged++ ))
        fi

        printf "%-30s %-12s %-12s %b\n" "$key" "$r1" "$r2" "$delta"
    done

    table_sep
    echo -e "${GREEN}Improved: ${improved}${RESET}  ${RED}Regressed: ${regressed}${RESET}  Unchanged: ${unchanged}"
    echo ""
}

# Print run history.
# Args: results_base_dir [limit]
print_history() {
    local results_dir="$1"
    local limit="${2:-20}"

    echo ""
    echo -e "${BOLD}Eval Run History${RESET}"
    table_sep
    printf "${BOLD}%-25s %-15s %-8s %-6s %-6s %-6s${RESET}\n" "RUN ID" "HARNESS" "MODEL" "PASS" "FAIL" "SKIP"
    table_sep

    local count=0
    for run_dir in $(ls -1dr "${results_dir}"/*/  2>/dev/null); do
        [[ -d "$run_dir" ]] || continue
        (( count >= limit )) && break

        local meta="${run_dir}/meta.json"
        local summary="${run_dir}/summary.json"

        if [[ ! -f "$meta" ]]; then continue; fi

        local run_id harness model pass fail skip
        run_id="$(jq -r '.run_id // "?"' "$meta")"
        harness="$(jq -r '.harness // "?"' "$meta")"
        model="$(jq -r '.model // "?"' "$meta")"

        if [[ -f "$summary" ]]; then
            pass="$(jq -r '.pass // 0' "$summary")"
            fail="$(jq -r '.fail // 0' "$summary")"
            skip="$(jq -r '.skip // 0' "$summary")"
        else
            pass="?" fail="?" skip="?"
        fi

        printf "%-25s %-15s %-8s ${GREEN}%-6s${RESET} ${RED}%-6s${RESET} ${YELLOW}%-6s${RESET}\n" \
            "$run_id" "$harness" "$model" "$pass" "$fail" "$skip"

        (( count++ ))
    done

    if (( count == 0 )); then
        echo "  No runs found."
    fi

    table_sep
    echo ""
}
