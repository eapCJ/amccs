# Contributing to AMCCS

Thanks for investing time in improving the Android Multi-cam Camera System!

## Development Workflow

1. Fork and clone the repo.
2. Create a virtual environment with Python 3.11+.
3. Install dependencies:
   ```bash
   pip install -e .[test,dev]
   ```
4. Copy `config.example.yaml` to `config.yaml` and adjust it for your adb devices before running the service or tests.

## Coding Standards

- Write typed, documented code that favors clarity over cleverness.
- Keep functions short and testable; prefer dependency injection for hardware/adb boundaries.
- Surface security-sensitive changes in the pull request description.
- Run the automated checks before opening a PR:
  ```bash
  ruff check
  mypy src tests
  pytest
  ```

## Commit & PR Guidelines

- Reference related issues in commits and pull requests.
- Describe *why* a change is needed, not just *what* changed.
- Include tests for regressions and new behavior. Negative-path coverage (timeouts, adb errors, auth failures) is strongly encouraged.

## Reporting Issues

- Use GitHub Issues for bugs and feature requests.
- Include reproduction steps, stack traces, and environment details when applicable.
- For security vulnerabilities, follow the steps in [SECURITY.md](SECURITY.md); please do not open a public issue.

## Code of Conduct

Participation in this project is governed by the [Code of Conduct](CODE_OF_CONDUCT.md). Instances of unacceptable behavior can be reported privately to `security@logiscan.dev`.
