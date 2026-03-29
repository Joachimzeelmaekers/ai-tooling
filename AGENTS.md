# AI Tooling — Agent Instructions

## Stack
Bash scripts, YAML configs, JSON results. No build step.

## Commands
- Run evals: `make -C tools/evals run`
- Compare runs: `make -C tools/evals compare TAG1=x TAG2=y`

## Conventions
- Scripts must be POSIX-compatible where possible, bash where needed
- Use jq for JSON manipulation
- No external dependencies beyond: bash, jq, git, claude CLI
- Results are gitignored — never commit eval results
