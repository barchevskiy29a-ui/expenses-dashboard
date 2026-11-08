# Contributing

Thanks for your interest!

## Setup

```bash
git clone https://github.com/quicksnapper/expenses-dashboard.git
cd expenses-dashboard
python -m venv .venv
# activate venv
pip install -r requirements.txt
pytest tests/ -q
```

## Guidelines

- Keep the project dependency-light: no new runtime dependencies unless
  really needed.
- All new behavior ships with tests (`pytest`).
- Keep the demo data synthetic. Never add real transactions to the repo.
- Update the README (RU and EN) when user-facing behavior changes.

## Pull requests

- Branch from `main`.
- Run `pytest tests/ -q` and make sure it is green.
- Keep the diff focused.
