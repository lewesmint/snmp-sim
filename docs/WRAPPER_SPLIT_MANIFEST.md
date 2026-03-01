# Wrapper Split Manifest (Draft)

## Purpose
Define the file-level boundary for extracting `pysnmp_type_wrapper` into a standalone repository while keeping app compatibility shims in this repo during transition.

## Extract to wrapper repo
- `pysnmp_type_wrapper/__init__.py`
- `pysnmp_type_wrapper/__init__.pyi`
- `pysnmp_type_wrapper/interfaces.py`
- `pysnmp_type_wrapper/interfaces.pyi`
- `pysnmp_type_wrapper/raw_boundary_types.py`
- `pysnmp_type_wrapper/raw_boundary_types.pyi`
- `pysnmp_type_wrapper/pysnmp_type_resolver.py`
- `pysnmp_type_wrapper/pysnmp_type_resolver.pyi`
- `pysnmp_type_wrapper/pysnmp_rfc1902_adapter.py`
- `pysnmp_type_wrapper/pysnmp_rfc1902_adapter.pyi`
- `pysnmp_type_wrapper/pysnmp_mib_symbols_adapter.py`
- `pysnmp_type_wrapper/pysnmp_mib_symbols_adapter.pyi`
- `pysnmp_type_wrapper/mib_registrar_runtime_adapter.py`
- `pysnmp_type_wrapper/mib_registrar_runtime_adapter.pyi`
- `pysnmp_type_wrapper/constraint_parser.py`
- `pysnmp_type_wrapper/py.typed`
- `pysnmp_type_wrapper/pyproject.wrapper.toml` (draft metadata seed)
- `tests/wrapper/*.py` (wrapper-owned package tests)

## Keep in app repo (compatibility and app domain)
- `app/interface_types.py` (compatibility aliases + app-domain protocols)
- `app/pysnmp_type_resolver.py` (shim)
- `app/pysnmp_rfc1902_adapter.py` (shim)
- `app/pysnmp_mib_symbols_adapter.py` (shim)
- `app/mib_registrar_runtime_adapter.py` (shim)
- `app/pysnmp_boundary_types.py` (shim)

## Consumer migration status
- Direct wrapper imports already adopted in:
  - `app/base_type_handler.py`
  - `app/table_registrar.py`
  - `app/snmp_agent.py`
  - `app/type_recorder.py`
- Remaining app imports should prefer wrapper modules for boundary contracts when touched.

## Split acceptance checklist
- Wrapper package exports in `pysnmp_type_wrapper/__init__.py` are final and documented.
- No runtime path in app depends on a symbol that exists only in an app shim.
- Unit tests covering resolver/symbol-adapter behavior pass with wrapper as source of truth.
- A new wrapper repo can install and import the package without app repo internals.

## Automated extraction helper
- Script: `scripts/extract_wrapper_repo.sh`
- Usage:
  - `scripts/extract_wrapper_repo.sh /absolute/path/to/new-wrapper-repo`
- Behavior:
  - copies wrapper package `.py` + `.pyi` + `py.typed`
  - seeds target `pyproject.toml` from wrapper draft metadata
  - writes a minimal `README.md` if one does not exist

## Wrapper sync check
- Script: `scripts/check_wrapper_sync.sh`
- Purpose:
  - enforces post-vendoring policy (no local vendored wrapper directory)
  - verifies installed-wrapper resolution maps to canonical
    `../pysnmp-type-wrapper/pysnmp_type_wrapper`
- Usage:
  - `scripts/check_wrapper_sync.sh`
  - or via quality runner: `python scripts/check_all.py --with-wrapper-sync`

## Wrapper package source check
- Script: `scripts/check_wrapper_package_source.sh`
- Purpose:
  - reports whether `pysnmp_type_wrapper` resolves from vendored repo path or an external install
  - provides strict mode (`--require-external`) for de-vendoring cutover gate
- Usage:
  - `scripts/check_wrapper_package_source.sh`
  - installed-package probe: `scripts/check_wrapper_package_source.sh --probe-installed`
  - strict external gate: `scripts/check_wrapper_package_source.sh --require-external`
  - quality runner: `python scripts/check_all.py --with-wrapper-source-check`

## Notes
- This is intentionally a draft manifest for iterative execution.
- Keep compatibility shims in app until all consumers and tests are fully cut over.
