# AI Agent Eval Harness

Test whether changes to your agent configuration (AGENTS.md, skills, hooks) make AI agents better or worse.

## What this does

This framework runs AI agents headlessly against controlled tasks, then scores their behavior against your rules. It answers questions like:

- Does my agent respect "never commit unless asked"?
- Does it use yarn instead of npm when yarn.lock exists?
- Does it stay focused on the requested change or refactor everything?
- Does it plan before jumping into complex tasks?

## Quick start

```bash
# List available evals
make -C tools/evals list

# Dry run (see what would execute, no agent calls)
make -C tools/evals dry-run TAG=test

# Run all behavioral evals with your current dotfiles harness
make -C tools/evals run TAG=baseline

# Run with a specific model
make -C tools/evals run TAG=baseline MODEL=opus

# Run with a different agent CLI
make -C tools/evals run TAG=baseline AGENT=opencode
```

## A/B testing harnesses

```bash
# Run with your current config
make -C tools/evals run HARNESS=harnesses/default.yaml TAG=baseline

# Create a modified harness, run again
make -C tools/evals run HARNESS=harnesses/slim-v2.yaml TAG=slim-v2

# Compare results
make -C tools/evals compare TAG1=baseline TAG2=slim-v2

# View history of all runs
make -C tools/evals history
```

## Adding a new harness

Create a YAML file in `harnesses/` pointing to your agent config files:

```yaml
name: my-experiment
description: Testing minimal AGENTS.md
agents_md: ~/experiments/slim-agents/AGENTS.md
skills_dir: ~/experiments/slim-agents/skills
hooks_dir: ~/experiments/slim-agents/hooks
memory_md: ~/experiments/slim-agents/MEMORY.md
```

See `harnesses/README.md` for details.

## Adding a new eval

Create a YAML file in `evals/behavioral/` (or `evals/capability/`):

```yaml
name: my-new-check
description: What this tests
category: behavioral
suite: behavioral

setup:
  type: init
  language: typescript
  files:
    - path: src/example.ts
      content: |
        export const x = 1;

prompt: |
  The task prompt given to the agent.

behavioral_checks:
  - check: my_check
    description: What the agent should or shouldn't do
    grep_transcript_absent: "pattern that should NOT appear"

expected:
  files_changed:
    - src/example.ts
```

### Check types

- `grep_transcript_absent`: PASS if the pattern is NOT found in the transcript
- `grep_transcript_present`: PASS if the pattern IS found in the transcript
- `grep_diff_absent`: PASS if the pattern is NOT found in the git diff
- Named checks: `no_commit`, `no_coauthoring`, `pkg_manager`, `scope`, `no_destructive`, `plan_first`, `minimal_diff`

## Interpreting results

Each run produces:

- **PASS**: The agent followed the rule correctly
- **FAIL**: The agent violated the rule
- **SKIP**: The check couldn't run (e.g., no transcript available)

A good harness should produce mostly PASS results across all behavioral evals. When comparing two harnesses, look for:

- **IMPROVED**: A check that went from FAIL to PASS
- **REGRESSED**: A check that went from PASS to FAIL
- **Unchanged**: Same result in both runs

## Scoring

Scoring is deterministic -- it greps transcripts, diffs, and git logs for specific patterns. No LLM-as-judge. This means:

- Results are reproducible (same artifacts = same scores)
- You can inspect exactly why something passed or failed
- Adding new checks is straightforward (grep patterns or shell functions)

## Architecture

```
bin/ai-eval         CLI entrypoint
lib/
  runner.sh         Setup eval env, run agent, capture artifacts
  scorer.sh         Check artifacts against behavioral rules
  reporter.sh       Format results as tables
  utils.sh          Colors, logging, YAML parsing, temp dirs
harnesses/          Agent config definitions (YAML)
evals/
  behavioral/       Rule-compliance evals (YAML)
  capability/       Task-completion evals (future)
fixtures/           Pinned repos for capability evals
results/            Timestamped run data (gitignored)
```

## Dependencies

- bash
- jq
- git
- An agent CLI (claude, opencode, or codex)

## Results directory

Results are gitignored. Each run creates:

```
results/YYYYMMDD-HHMMSS-TAG/
  meta.json           Run metadata (harness, model, timestamp)
  summary.json        Aggregated pass/fail/skip counts
  evals/
    eval-name/
      transcript.json Agent output
      diff.patch      Git diff after agent ran
      score.json      Check results (JSON lines)
      meta.json       Per-eval metadata (duration, etc.)
```
