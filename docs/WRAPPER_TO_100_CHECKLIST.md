# Wrapper Migration: To-100 Checklist

## Goal
Reach de-vendoring readiness and complete cutover from vendored `snmp-sim/pysnmp_type_wrapper` to installed canonical `pysnmp-type-wrapper`.

## Baseline (already green)
- [x] Wrapper sync drift gate exists and passes (`scripts/check_wrapper_sync.sh`).
- [x] Wrapper extraction helper exists (`scripts/extract_wrapper_repo.sh`).
- [x] Wrapper public API smoke tests exist (`tests/wrapper/test_wrapper_public_api.py`).

## Phase 1: API and contract freeze
- [x] Freeze and document wrapper package public exports (`pysnmp_type_wrapper/__init__.py`, `__init__.pyi`).
- [x] Keep app-only compatibility symbols in `app/*` shims only.
- [x] Ensure wrapper tests cover exported adapters/protocol contracts.

Validation commands:
- `pytest -q tests/wrapper`
- `python scripts/check_all.py --with-wrapper-sync`

## Phase 2: Installed-package cutover prep
- [x] Verify where `pysnmp_type_wrapper` resolves from in the active environment.
- [x] Add gating command for source resolution (vendored vs external).
- [x] Ensure canonical wrapper is installable in environment (`pip install -e ../pysnmp-type-wrapper`).

Validation commands:
- `bash scripts/check_wrapper_package_source.sh`
- `bash scripts/check_wrapper_package_source.sh --probe-installed`
- `bash scripts/check_wrapper_package_source.sh --require-external`

## Phase 3: De-vendoring execution
- [x] Remove/retire vendored `snmp-sim/pysnmp_type_wrapper` once external import source is proven.
- [x] Re-run app + wrapper boundary tests against external package resolution.
- [x] Confirm no runtime import falls back to removed vendored path.

Validation commands (minimum):
- `pytest -q tests/wrapper tests/unit/table/test_table_registrar.py tests/unit/agent/test_snmp_agent_additional.py tests/unit/type_system/test_base_type_handler.py tests/unit/type_system/test_base_type_handler_more.py`
- `python scripts/check_all.py --with-wrapper-sync --with-wrapper-source-check`

## Exit criteria (100%)
- [x] App imports resolve `pysnmp_type_wrapper` from installed canonical package only.
- [x] Vendored wrapper removal causes no runtime/type regressions.
- [x] Wrapper acceptance checklist in `docs/WRAPPER_SPLIT_MANIFEST.md` is fully satisfied.
- [x] Handoff log is updated with final cutover and verification evidence.

## Execution evidence (2026-03-01)
- Added source-resolution gate: `scripts/check_wrapper_package_source.sh`.
- Added quality-runner integration: `python scripts/check_all.py --with-wrapper-source-check`.
- Installed canonical wrapper in active venv: `.venv/bin/python -m pip install -e ../pysnmp-type-wrapper`.
- External-only rehearsal (temporary vendored-folder hide) passed:
	- strict external gate passed: `scripts/check_wrapper_package_source.sh --require-external`
	- boundary wrapper+app tests passed: `144 passed, 0 failed`.
- Final cutover complete:
	- vendored wrapper retired to `retired/pysnmp_type_wrapper_vendored_2026-03-01`
	- post-vendor sync gate passed (`wrapper: sync-check` task)
	- strict external source gate passed (`scripts/check_wrapper_package_source.sh --probe-installed --require-external`)
	- boundary wrapper+app tests passed on post-vendor layout: `144 passed, 0 failed`.
