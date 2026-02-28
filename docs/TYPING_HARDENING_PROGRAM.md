# Project-wide typing hardening program

## Goal
Reduce dynamic typing risk across the repository by replacing broad `Any`/`object` boundaries and reflection-heavy access with narrow protocols, typed payload contracts, and adapter helpers, while preserving behavior.

## Process
1. Inventory hotspots (`Any`, broad `object`, `hasattr/getattr`, `cast`, broad exceptions).
2. Rank by impact (runtime-critical modules first, then API/data-contract modules).
3. Refactor in small slices per module with explicit type contracts.
4. Validate each slice via targeted `pyright`, `mypy`, and focused tests.
5. Track completion in this document and iterate.

## Candidate list (priority)

### Tier 1 (runtime-critical)
- [~] `app/snmp_agent.py` — major symbol-map, scalar-class loading, and runtime registrar loading paths moved behind adapters; remaining lifecycle/introspection cleanup pending.
- [ ] `app/type_recorder.py` — C1-C4 completed; pending exception narrowing (C5).
- [ ] `app/generator.py` — large `Any` surface in schema/type extraction.
- [ ] `app/mib_registrar_helpers.py` — repeated dynamic attribute access.

### Tier 2 (core model/data flow)
- [x] `app/mib_dependency_resolver.py` — converted tree payloads from `Any` to `TypedDict` contracts.
- [x] `app/snmp_table_responder.py` — replaced repeated `Any` maps with object-based aliases and OID coercion helpers.
- [x] `app/value_links.py` — replaced schema/link `Any` records with typed object maps and safer config parsing.
- [x] `app/table_registrar.py` — migrated to shared contracts and PySNMP type resolver adapter boundary.

### Tier 3 (API surfaces)
- [x] `app/api_table_helpers.py` — converted helper contracts to object-based aliases with safer normalization.
- [x] `app/api_system.py` — registry-loading boundary tightened and `Any` removed.
- [x] `app/api_tables.py` — removed cast-based index handling and normalized table payload maps.

## Progress tracker
- [x] P0: Program defined (goal, process, candidates).
- [x] P1: Initial `app/type_recorder.py` slice (callable + enum boundary + alias).
- [x] P2: `app/mib_dependency_resolver.py` `TypedDict` contracts.
- [x] P3: Validate current batch (`get_errors` clean + focused tests passing).
- [x] P4: Start Tier 1 module batch (`app/generator.py` then `app/snmp_agent.py`).
- [x] P5: Expand boundary adapters in `snmp_agent` and `type_recorder`.
- [~] P6: Continue removing direct reflection from SNMP runtime orchestration paths.

## Reusable boundary module rollout
- [x] Created dedicated reusable boundary package: `pysnmp_type_wrapper/`.
- [x] Added shared exports in `pysnmp_type_wrapper/__init__.py` for adapters and protocols.
- [x] Migrated runtime consumers to `pysnmp_type_wrapper.*` imports in:
	- `app/snmp_agent.py`
	- `app/type_recorder.py`
	- `app/table_registrar.py`
- [x] Left compatibility shims in `app/pysnmp_type_resolver.py`, `app/pysnmp_mib_symbols_adapter.py`, `app/pysnmp_rfc1902_adapter.py`, and `app/mib_registrar_runtime_adapter.py`.

## Notes
- Initial attempt to tighten `app/generator.py` uncovered high coupling and cascading type issues; deferred to a dedicated sub-plan to avoid destabilizing ongoing work.

## Latest validation snapshot
- `tests/unit/type_system/test_type_recorder_unit.py`, `tests/unit/type_system/test_type_recorder_more.py`, `tests/unit/type_system/test_type_recorder_build.py`: passing (`98 passed`) after boundary type relocation.
- `tests/unit/mib/test_mib_dependency_resolver.py`: passing.
- `tests/unit/agent/test_snmp_table_responder.py`: passing.
- `tests/unit/app/test_value_links.py`: passing.
- `tests/unit/agent/test_snmp_agent_additional.py`, `tests/unit/agent/test_snmp_agent_unit.py`, `tests/unit/agent/test_snmp_agent_more.py`, `tests/unit/agent/test_agent_errors.py`: passing (`91 passed`) after symbol adapter migration.
- Same `snmp_agent` focused suite remains passing (`91 passed`) after runtime registrar adapter extraction.
- `tests/misc/test_api.py` and `tests/misc/test_basic_models.py`: passing after `api_tables` cast-removal cleanup.
- `tests/unit/table/test_table_registrar.py`, `tests/unit/type_system/test_type_recorder_*.py`, and `tests/unit/agent/test_*snmp_agent*.py`: passing (`229 passed`) after dedicated boundary module migration.
- VS Code diagnostics (`get_errors`) on touched files: no new boundary-migration type errors; legacy complexity/style debt remains in `app/type_recorder.py` and `app/table_registrar.py`.

## Current blockers/notes
- `app/snmp_table_responder.py` and `app/type_recorder.py` still report legacy complexity/style thresholds and broad-exception lint debt.
- `app/snmp_agent.py` still has targeted dynamic module-introspection (`getattr`) flows pending adapter extraction.
