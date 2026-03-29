# Harness Definitions

A harness is a YAML file that tells the eval runner where to find your agent configuration files.

## Format

```yaml
name: my-harness            # short identifier
description: What this is   # human-readable description
agents_md: ~/path/to/AGENTS.md
skills_dir: ~/path/to/skills
hooks_dir: ~/path/to/hooks
memory_md: ~/path/to/MEMORY.md
```

All paths support `~` expansion. Missing paths are silently skipped.

## Adding a harness

1. Create a new YAML file in this directory (e.g., `slim-v2.yaml`).
2. Point it at the AGENTS.md, skills, and hooks you want to test.
3. Run: `ai-eval run --harness harnesses/slim-v2.yaml --tag slim-v2`

## A/B testing

Run the same suite with two different harnesses and compare:

```bash
ai-eval run --harness harnesses/default.yaml --tag baseline
ai-eval run --harness harnesses/slim-v2.yaml --tag slim-v2
ai-eval compare baseline slim-v2
```
