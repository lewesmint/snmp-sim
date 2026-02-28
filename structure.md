# PySNMP Typed Wrapper & App — Project Setup Guide

## Overview

This document captures the full architecture, workspace layout, tooling decisions, and configuration
for two related Python projects:

- **`pysnmp-type-wrapper`** — a reusable, fully type-hinted façade and stub library over PySNMP 7.x
- **`pysnmp-app`** — an SNMP Agent Simulator with a REST API (FastAPI) and UI (CustomTkinter)

These are two separate Git repositories managed together via a VS Code multi-root workspace.

### Runtime split (important)

The app package has two runtime parts that should be treated as separate processes:

- **Server process**: FastAPI + SNMP agent runtime (state, MIB loading, SNMP I/O)
- **UI process**: CustomTkinter client that talks to the server only via REST/WebSocket

The UI should not import or instantiate SNMP runtime internals directly.

---

## Background & Problem Statement

PySNMP 7.x has no type stubs package (`types-pysnmp` does not exist on PyPI). This means:

- mypy, pyright/pylance, and ruff will treat all PySNMP internals as `Any`
- MIB-derived types are constructed dynamically at runtime by `MibBuilder` — they have no static
  representation anywhere
- Writing a fully type-hinted application on top of PySNMP without resorting to `cast()`, `Any`,
  `object`, or `getattr` is not straightforward

### Solution: Option 3 — Stubs + Typed Wrapper (Hybrid)

1. Write minimal `.pyi` stubs covering only the PySNMP surface your wrapper touches
2. Build a typed façade/wrapper over those stubs — all `# type: ignore` comments are quarantined here
3. Use build-time codegen for MIB-derived types — the `MibBuilder` runs at dev/build time and emits
   proper Python `dataclass` definitions into the codebase as static, checked types
4. The app imports only from the wrapper — it never touches PySNMP directly

---

## Key Concepts

### `py.typed` (PEP 561 marker)

An **empty file** placed at the root of your package (`src/pysnmp_type_wrapper/py.typed`).  
Its sole purpose is to tell mypy and pyright that this package is typed and its annotations should
be trusted. Without it, type checkers silently ignore your types and fall back to `Any`.

### `.pyi` stub files

Stub files live in `typings/` at the repo root (top-level, not inside `src/`). Each `.pyi` mirrors
a `.py` file in the real pysnmp/pyasn1 packages and contains only type signatures — no
implementation. You only need to stub the parts your wrapper actually uses, not the entire library.

Example:

```python
# typings/pysnmp/hlapi/asyncio/__init__.pyi

class SnmpEngine: ...

class UdpTransportTarget:
    def __init__(self, transportAddr: tuple[str, int], timeout: float = ...,
                 retries: int = ...) -> None: ...
```

### MIB-derived types

`MibBuilder` dynamically constructs Python classes at runtime. These can't be statically typed
directly. The solution is a **codegen script** (`scripts/generate_mib_types.py`) that:

1. Loads your MIBs via `MibBuilder` at build/dev time
2. Emits proper `@dataclass` definitions into `src/pysnmp_type_wrapper/mib/generated/`
3. These generated files are committed to the repo and become statically checkable types

Example generated output:

```python
# src/pysnmp_type_wrapper/mib/generated/if_mib.py  (auto-generated — do not edit)
from dataclasses import dataclass

@dataclass
class IfEntry:
    if_index: int
    if_descr: str
    if_type: int
    if_mtu: int
    if_speed: int
```

---

## Workspace Layout

```
/Users/<you>/code/
│
├── pysnmp-type-wrapper/                    # Repo 1: reusable typed library
│   ├── .git/
│   ├── .venv/                              # local only — git-ignored
│   ├── .python-version                     # 3.13.x (honoured by pyenv)
│   ├── pyproject.toml
│   ├── poetry.lock
│   ├── README.md
│   ├── CHANGELOG.md
│   │
│   ├── src/
│   │   └── pysnmp_type_wrapper/
│   │       ├── __init__.py
│   │       ├── py.typed                    # PEP 561 marker (empty file)
│   │       ├── client.py                   # High-level typed SNMP client
│   │       ├── protocols.py                # Protocol / ABC definitions
│   │       ├── types.py                    # Typed domain model (OID, VarBind, Trap etc.)
│   │       ├── exceptions.py               # Typed exception hierarchy
│   │       ├── agent.py                    # Typed agent façade
│   │       ├── manager.py                  # Typed manager façade
│   │       ├── trap.py                     # Typed trap sender/receiver façade
│   │       └── mib/
│   │           ├── __init__.py
│   │           ├── loader.py               # MibBuilder wrapper — returns typed objects
│   │           └── generated/              # Auto-generated MIB dataclasses (committed)
│   │               └── .gitkeep
│   │
│   ├── typings/                            # Hand-written .pyi stubs for pysnmp/pyasn1
│   │   ├── pysnmp/
│   │   │   ├── __init__.pyi
│   │   │   ├── hlapi/
│   │   │   │   └── asyncio/
│   │   │   │       └── __init__.pyi
│   │   │   └── smi/
│   │   │       └── rfc1902.pyi
│   │   └── pyasn1/
│   │       ├── __init__.pyi
│   │       └── type/
│   │           └── univ.pyi
│   │
│   ├── scripts/
│   │   └── generate_mib_types.py           # Build-time MIB → dataclass codegen
│   │
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_types.py
│   │   ├── test_agent.py
│   │   ├── test_manager.py
│   │   ├── test_trap.py
│   │   └── test_mib_loader.py
│   │
│   └── docs/
│       └── workspace-layout.md
│
├── pysnmp-app/                             # Repo 2: SNMP Agent Simulator
│   ├── .git/
│   ├── .venv/                              # local only — git-ignored
│   ├── .python-version                     # 3.13.x
│   ├── pyproject.toml
│   ├── poetry.lock
│   └── README.md
│   │
│   ├── src/
│   │   └── pysnmp_app/
│   │       ├── __init__.py
│   │       ├── agent/
│   │       │   ├── __init__.py
│   │       │   └── simulator.py            # Core agent simulation logic
│   │       ├── api/                        # FastAPI REST layer
│   │       │   ├── __init__.py
│   │       │   ├── models.py               # Pydantic request/response models
│   │       │   └── routes/
│   │       │       ├── __init__.py
│   │       │       ├── agent.py
│   │       │       └── trap.py
│   │       ├── ui/                         # CustomTkinter UI
│   │       │   ├── __init__.py
│   │       │   └── app.py
│   │       └── shared/
│   │           ├── __init__.py
│   │           └── services.py
│   │
│   └── tests/
│       ├── conftest.py
│       ├── test_simulator.py
│       ├── test_api.py
│       └── test_ui.py
│
└── pysnmp-workspace.code-workspace         # VS Code multi-root workspace file
```

### App runtime topology (server + UI)

Recommended logical split inside `pysnmp_app`:

- `server/` (or keep `api/` + `agent/` but treat as one deployable server unit)
  - REST routes, lifecycle, SNMP engine orchestration, persistence
- `ui/`
  - presentation, local state, API client
- `shared/`
  - DTOs/config/constants that are safe for both sides

Whether you rename folders now is optional; the hard requirement is process and dependency separation.

---

## Configuration Files

### `pysnmp-workspace.code-workspace`

```json
{
    "folders": [
        {
            "name": "wrapper",
            "path": "pysnmp-type-wrapper"
        },
        {
            "name": "app",
            "path": "pysnmp-app"
        }
    ],
    "settings": {
        "python.analysis.typeCheckingMode": "strict"
    }
}
```

### `.vscode/settings.json` (place a copy in each repo root)

```json
{
    "python.analysis.typeCheckingMode": "strict",
    "python.analysis.autoImportCompletions": true,
    "python.analysis.stubPath": "typings",
    "editor.formatOnSave": true,
    "editor.rulers": [88],
    "[python]": {
        "editor.defaultFormatter": "charliermarsh.ruff",
        "editor.codeActionsOnSave": {
            "source.fixAll.ruff": "explicit",
            "source.organizeImports.ruff": "explicit"
        }
    },
    "mypy-type-checker.runUsingActiveInterpreter": true,
    "ruff.lint.enable": true
}
```

### `.vscode/extensions.json` (place a copy in each repo root)

```json
{
    "recommendations": [
        "ms-python.python",
        "ms-python.pylance",
        "charliermarsh.ruff",
        "ms-python.mypy-type-checker",
        "tamasfe.even-better-toml",
        "editorconfig.editorconfig",
        "github.vscode-github-actions"
    ]
}
```

### `.vscode/launch.json` (place in each repo root as appropriate)

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Run app API",
            "type": "debugpy",
            "request": "launch",
            "module": "uvicorn",
            "args": ["pysnmp_app.api:app", "--reload"],
            "cwd": "${workspaceFolder}",
            "python": "${workspaceFolder}/.venv/bin/python"
        },
        {
            "name": "Run app UI",
            "type": "debugpy",
            "request": "launch",
            "module": "pysnmp_app.ui.app",
            "cwd": "${workspaceFolder}",
            "python": "${workspaceFolder}/.venv/bin/python"
        },
        {
            "name": "pytest",
            "type": "debugpy",
            "request": "launch",
            "module": "pytest",
            "args": ["tests/", "-v"],
            "cwd": "${workspaceFolder}",
            "python": "${workspaceFolder}/.venv/bin/python"
        }
    ]
}
```

### `.gitignore` (both repos)

```gitignore
# Virtual environments
.venv/
__pycache__/
*.pyc
*.pyo

# Build artefacts
dist/
build/
*.egg-info/

# Type checking caches
.mypy_cache/
.ruff_cache/
.pyright/

# Test coverage
.coverage
htmlcov/
.pytest_cache/

# OS
.DS_Store
Thumbs.db

# IDE
*.swp
```

### `.editorconfig` (both repos)

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true

[*.py]
indent_style = space
indent_size = 4

[*.toml]
indent_style = space
indent_size = 4

[*.json]
indent_style = space
indent_size = 2

[*.yml]
indent_style = space
indent_size = 2
```

---

## `pyproject.toml` — Wrapper

```toml
[tool.poetry]
name = "pysnmp-type-wrapper"
version = "0.1.0"
description = "Typed façade and stubs for PySNMP 7.x"
authors = ["Mint"]
readme = "README.md"
packages = [{ include = "pysnmp_type_wrapper", from = "src" }]

[tool.poetry.dependencies]
python = "^3.13"
pysnmp = "^7.1.22"

[tool.poetry.group.dev.dependencies]
pytest = "^8.0"
pytest-asyncio = "^0.23"
mypy = "^1.10"
ruff = "^0.4"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"

[tool.mypy]
strict = true
python_version = "3.13"
mypy_path = "src:typings"

[tool.ruff]
line-length = 88
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "ANN"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

---

## `pyproject.toml` — App

```toml
[tool.poetry]
name = "pysnmp-app"
version = "0.1.0"
description = "SNMP Agent Simulator with REST API and CustomTkinter UI"
authors = ["Mint"]
readme = "README.md"
packages = [{ include = "pysnmp_app", from = "src" }]

[tool.poetry.dependencies]
python = "^3.13"
pysnmp-type-wrapper = { path = "../pysnmp-type-wrapper", develop = true }
fastapi = "^0.111"
uvicorn = { extras = ["standard"], version = "^0.30" }
customtkinter = "^5.2"
pydantic = "^2.7"

[tool.poetry.group.dev.dependencies]
pytest = "^8.0"
pytest-asyncio = "^0.23"
httpx = "^0.27"
mypy = "^1.10"
ruff = "^0.4"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"

[tool.mypy]
strict = true
python_version = "3.13"
mypy_path = "src"

[tool.ruff]
line-length = 88
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "ANN"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

---

## GitHub Actions CI

### `.github/workflows/test-wrapper.yml`

```yaml
name: Test wrapper

on:
  push:
    paths:
      - "**"
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: pip install poetry
      - run: poetry install
      - run: poetry run pytest
      - run: poetry run mypy src
      - run: poetry run ruff check src tests
```

### `.github/workflows/test-app.yml`

```yaml
name: Test app

on:
  push:
    paths:
      - "**"
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          # Check out the wrapper alongside the app in CI
          path: pysnmp-app
      - name: Check out wrapper
        uses: actions/checkout@v4
        with:
          repository: <your-github-username>/pysnmp-type-wrapper
          path: pysnmp-type-wrapper
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: pip install poetry
      - name: Install wrapper
        working-directory: pysnmp-type-wrapper
        run: poetry install
      - name: Install app
        working-directory: pysnmp-app
        run: poetry install
      - name: Test
        working-directory: pysnmp-app
        run: poetry run pytest
      - name: Type check
        working-directory: pysnmp-app
        run: poetry run mypy src
      - name: Lint
        working-directory: pysnmp-app
        run: poetry run ruff check src tests
```

---

## First-Time Setup

### Prerequisites (Mac)

```bash
# Install pyenv for Python version management
brew install pyenv

# Add to your shell profile (~/.zshrc or ~/.bash_profile)
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"

# Install Python 3.13
pyenv install 3.13.12

# Install Poetry globally
curl -sSL https://install.python-poetry.org | python3 -

# Tell Poetry to always put .venv inside the project folder
# (critical for VS Code to auto-detect it)
poetry config virtualenvs.in-project true
```

### Setup the wrapper

```bash
cd ~/code/pysnmp-type-wrapper
pyenv local 3.13.12          # writes .python-version
poetry env use python3.13
poetry install
```

### Setup the app

```bash
cd ~/code/pysnmp-app
pyenv local 3.13.12
poetry env use python3.13
poetry install               # picks up wrapper via path dep automatically
```

### Open in VS Code

```bash
code ~/code/pysnmp-workspace.code-workspace
```

VS Code will detect both `.venv` directories automatically. Use the Python interpreter
selector (bottom-right status bar) to confirm each folder is using its own `.venv`.

---

## Prerequisites (Windows)

On Windows, use the same approach but note:

- Install pyenv-win: `winget install pyenv-win`
- `poetry shell` can be unreliable in PowerShell — prefer `poetry run <command>` instead
- Use `python` not `python3` in commands
- Path separators in `pyproject.toml` path dependencies use forward slashes — Poetry handles this

---

## Design Principles

| Principle | Rationale |
|-----------|-----------|
| `src/` layout in both repos | Correct packaging hygiene; prevents accidental imports from repo root |
| One `.venv` per repo | Avoids dependency collisions; mirrors real-world usage of wrapper as a library |
| `.venv` git-ignored | Never commit virtual environments |
| Stubs in `typings/` (top-level) | Clean separation of runtime code vs typing overlays; both mypy and pyright look here |
| App never imports pysnmp directly | All PySNMP usage quarantined inside wrapper; app stays clean |
| MIB types via codegen | `MibBuilder` runs at build time; emits static `@dataclass` definitions |
| Lock files committed | `poetry.lock` in both repos ensures reproducible environments across Mac/Windows |
| UI communicates via REST only | Server owns SNMP engine lifecycle; UI is a pure REST/WebSocket client |

---

## Migration Path to Two Published Packages

When the wrapper stabilises and you're ready to publish:

1. Publish `pysnmp-type-wrapper` to PyPI (`poetry publish`)
2. In the app's `pyproject.toml`, change:
   ```toml
   # Before (local path dep)
   pysnmp-type-wrapper = { path = "../pysnmp-type-wrapper", develop = true }

   # After (PyPI dep)
   pysnmp-type-wrapper = "^1.0"
   ```
3. Run `poetry update` in the app
4. No application code changes required

---

## Transition Plan from Current `snmp-sim` Work

This section maps your in-progress implementation to the two-repo hybrid model.

### Current state (already aligned)

You already have the core boundary pattern in place:

- PySNMP interaction isolated in wrapper-style adapters/protocols
- app code increasingly imports typed wrapper contracts instead of direct runtime reflection
- compatibility shims exist for safe migration

This means the target architecture is **evolutionary**, not a rewrite.

### What changes vs what stays the same

**Stays the same (core design):**

- boundary adapters and protocols
- typed façade over dynamic PySNMP behaviour
- strict typing goal: app avoids `Any`/`cast` at business layer

**Changes (packaging + governance):**

- move wrapper code to its own repo/package with clean public API
- add minimal handwritten `.pyi` stubs under `typings/`
- add wrapper release/version policy and compatibility matrix for app

### Incremental migration steps

1. **Freeze wrapper boundary API in-place**
   - define public exports in `pysnmp_type_wrapper/__init__.py`
   - mark internal modules private by convention

2. **Create new wrapper repo scaffold**
   - `pysnmp-type-wrapper/src/pysnmp_type_wrapper/`
   - copy current wrapper modules first (no behaviour change)

3. **Add `py.typed` and minimal `typings/` stubs**
   - stub only the PySNMP/pyasn1 surfaces actually touched by wrapper
   - keep all unavoidable ignores inside wrapper only

4. **Switch app to path dependency**
   - in app `pyproject.toml`: `pysnmp-type-wrapper = { path = "../pysnmp-type-wrapper", develop = true }`
   - replace internal imports to use package import path only

5. **Keep temporary compatibility shims in app**
   - deprecated import paths forward to wrapper package
   - remove in a scheduled cleanup release

6. **Split app runtime concerns explicitly**
   - ensure UI communicates via REST only
   - server owns SNMP engine lifecycle and state

7. **CI hardening**
   - wrapper CI: pytest + mypy + ruff
   - app CI: same, plus integration tests against wrapper dependency

8. **Publish wrapper**
   - tag/release wrapper
   - app switches from path dependency to versioned PyPI dependency

### Compatibility policy during transition

- use semantic versioning in wrapper
- treat exported wrapper protocols/adapters as stable API
- keep app-side shims for at least one minor release after cutover
- add deprecation notes in changelog before shim removal

### Risk controls

- move code first, refactor second
- keep behaviour tests green before and after each move
- avoid simultaneous folder reshuffle + logic rewrite in one step

---

## Summary

```
pysnmp-type-wrapper  →  typings/ (.pyi stubs)
                     →  src/pysnmp_type_wrapper/ (typed façade + codegen MIB types)
                     →  py.typed (PEP 561 marker)

pysnmp-app           →  imports only from pysnmp_type_wrapper
                     →  Server process (FastAPI + SNMP agent runtime)
                     →  UI process (CustomTkinter REST/WebSocket client)
                     →  Never touches pysnmp directly
```

All `cast()`, `Any`, and `# type: ignore` comments live exclusively inside the wrapper.  
The app is clean: strict mypy, ruff, and pylance/pyright with zero suppressions.