# Fixtures

Pinned repositories and task prompts for capability evals.

## How to add a fixture

1. Create a directory here with a descriptive name (e.g., `express-api/`).
2. Include the actual repo files (or a script to clone/setup).
3. Add a `task.yaml` describing the eval task:

```yaml
name: express-add-endpoint
description: Add a new REST endpoint to an Express API
repo: fixtures/express-api
prompt: |
  Add a GET /health endpoint that returns {"status": "ok"}.
expected:
  files_changed:
    - src/routes.ts
```

4. Reference the fixture in an eval YAML under `evals/capability/`.

## Guidelines

- Keep fixtures small (minimal repos that test one thing).
- Pin dependencies to avoid flaky setups.
- Include a README in each fixture explaining what it tests.
