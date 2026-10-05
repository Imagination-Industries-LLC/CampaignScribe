# Contributing to CampaignScribe

CampaignScribe is a Windows desktop application (Python 3.13, Tkinter) for transcribing and summarizing tabletop-RPG sessions. Contributions are welcome — please read this guide before opening a pull request.

## Local Setup

1. **Clone** the repository.
2. **First-time setup:** run `setup_venv.bat` to create `.venv` and install the full ML stack (WhisperX, pyannote, etc.).
3. **Test/lint work only:** you can skip the heavy ML install and just run:
   ```
   .venv\Scripts\python -m pip install -r requirements-dev.txt
   ```

## Before Pushing

Run the following locally and fix any findings before opening a PR:

```
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m ruff format .
.venv\Scripts\python -m pytest
```

Optionally install the pre-commit hook so these run automatically on every commit:

```
.venv\Scripts\python -m pre_commit install
```

## The PR Gauntlet

All of the following must be green (or explicitly triaged) before a PR can be merged.

### CI — GitHub Actions (required status checks)

| Check | What it runs |
|---|---|
| `lint-test-linux` | ruff lint + format, mypy (non-blocking), bandit, semgrep, pip-audit, pytest (non-GUI) on Ubuntu |
| `gui-test-windows` | Full pytest suite including the Tkinter smoke test on Windows |

Both checks are required; a PR cannot be merged until both pass.

### Security Scanning

**CodeQL** code scanning is enabled at the repository level via GitHub's default setup (configured in repo Settings, not a workflow file here).

### AI Code Reviewers

Four AI reviewers auto-review every PR. Their findings must be addressed or explicitly dismissed before merge:

- **CodeRabbit** — automated review with inline comments and high-level summary
- **GitHub Copilot code review** — line-level suggestions from Copilot
- **Qodo** — PR quality and test-coverage analysis
- **Greptile** — codebase-aware review that understands cross-file context

## Tests

- Unit tests: `tests/unit/`
- Integration tests: `tests/integration/`
- GUI smoke test: `tests/smoke/` (marked `gui`; runs on Windows only)

Add tests for any new behavior. Keep the suite green.

## Commit Messages

Use plain, descriptive commit messages. No AI-attribution trailers.
