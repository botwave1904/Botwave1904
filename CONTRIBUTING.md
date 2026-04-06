# Contributing to Botwave

## Setup

1. Python 3.10+ recommended:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

2. Install dev deps:
   ```bash
   pip install -r requirements.txt
   pip install ruff pytest
   ```

## Run tests

```bash
pytest -q
```

## Linting

```bash
ruff check src tests
```

## Branching & PRs

- Create a feature branch from main:
  ```bash
  git checkout -b feature/your-feature-name
  ```
- Keep changes focused and add tests where applicable
- Open a PR and ensure CI passes

## Security & secrets

- Do not commit secrets (.env, keys)
- Add any credentials to repository Secrets in GitHub (CI)
