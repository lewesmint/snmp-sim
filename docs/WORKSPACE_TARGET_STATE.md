# Workspace Target State (Current vs Desired)

## Scope
This document is the single quick-reference handoff for the multi-repo workspace and the wrapper split trajectory.

## Target structure
- `pysnmp-type-wrapper` (canonical)
  - source of truth for `pysnmp_type_wrapper` runtime adapters and typed exports
- `snmp-sim` (production app)
  - primary runtime app, now consuming canonical wrapper as installed dependency
- `pysnmp-type-wrapper-legacy` (transition source)
  - legacy extraction/reference only
- `pysnmp-app` (minimal proving harness)
  - small validation/integration sandbox

## Current state summary
- Wrapper ownership:
  - wrapper adapter surface is consolidated and typed in canonical wrapper
  - `constraint_parser.py` moved from app orchestration into wrapper package
- App boundaries:
  - `app/type_recorder.py` now delegates parsing helpers to wrapper package
  - app still orchestrates workflow and policy (compiled MIB loading, registry assembly)
- Sync controls:
  - post-vendor wrapper policy check exists: `scripts/check_wrapper_sync.sh`
  - wrapper source resolution check exists: `scripts/check_wrapper_package_source.sh`
  - VS Code task exists: `wrapper: sync-check`
  - quality runner supports opt-in checks:
    - `python scripts/check_all.py --with-wrapper-sync`
    - `python scripts/check_all.py --with-wrapper-source-check`
- Local tooling:
  - workspace-level interpreter/pylint pinning is in place per repo
  - `.pyi` lint noise is suppressed in editor settings

## Gap to final state
- Full acceptance sweep should run once more on post-vendor layout before release.
- Some app compatibility shims remain intentionally until full consumer migration completes.

## Operating rules
- Canonical changes happen in `pysnmp-type-wrapper` first.
- `snmp-sim` must not reintroduce vendored `pysnmp_type_wrapper`.
- Before merge/release, run:
  - `scripts/check_wrapper_sync.sh`
  - `scripts/check_wrapper_package_source.sh --require-external --probe-installed`
  - targeted tests touching wrapper/app boundary

## Commands
- Direct sync check:
  - `scripts/check_wrapper_sync.sh`
- Direct source check:
  - `scripts/check_wrapper_package_source.sh`
- Sync check via runner:
  - `python scripts/check_all.py --with-wrapper-sync`
- Source check via runner:
  - `python scripts/check_all.py --with-wrapper-source-check`
- Run wrapper task in VS Code:
  - `Tasks: Run Task` → `wrapper: sync-check`

## Exit criteria for de-vendoring
- app imports resolve against installed canonical wrapper package only
- vendored `snmp-sim/pysnmp_type_wrapper` remains absent with no runtime/type regression
- wrapper-focused tests pass from canonical package context
- split manifest acceptance checklist is complete (`docs/WRAPPER_SPLIT_MANIFEST.md`)

## Related docs
- `docs/WRAPPER_SPLIT_MANIFEST.md`
- `docs/WRAPPER_MIGRATION_HANDOFF_LOG.md`
- `docs/TYPE_RECORDER_TYPING_HARDENING.md`
