# Refactor Signals & Hotspot Detection

Date: 2026-02-21

## What is now wired in

### 1) Prospector + Pylint + McCabe
- Config: `.prospector.yaml`
- `mccabe` is enabled, along with existing `pylint`.
- This surfaces complexity and refactor-style warnings from Prospector runs.

Run:

```bash
prospector .
```

### 2) Ruff complexity/refactor rules
- Config: `pyproject.toml`
- Added:
  - `C90` (McCabe complexity)
  - `PLR` (Pylint refactor family via Ruff)
  - `tool.ruff.lint.mccabe.max-complexity = 12`

Run:

```bash
ruff check .
```

### 3) Flake8 complexity threshold
- Config: `.flake8`
- Added `max-complexity = 12`.

Run:

```bash
flake8 . --count --statistics
```

### 4) Ranked hotspot scanner (non-gating)
- Script: `scripts/refactor_hotspots.py`
- Reports:
  - largest Python files
  - function hotspots scored by size + complexity + branching

Run:

```bash
python scripts/refactor_hotspots.py .
```

Useful options:

```bash
python scripts/refactor_hotspots.py . --top-files 30 --top-functions 50 --min-function-lines 30 --min-complexity 8
```

## Dependency notes

`requirements.full.txt` now includes tooling entries for:
- `flake8`
- `prospector`
- `pylint`
- `pyflakes`
- `radon`
- `xenon`

Optional extra checks:

```bash
radon cc app -s -a
xenon --max-absolute B --max-modules B --max-average B app
```

## Suggested workflow
1. Run `python scripts/refactor_hotspots.py .` for a ranked target list.
2. Run `ruff check .` to catch complexity/refactor violations.
3. Use `prospector .` for additional Pylint-driven refactor signals.
4. Use `flake8 . --count --statistics` to monitor complexity + style drift.
