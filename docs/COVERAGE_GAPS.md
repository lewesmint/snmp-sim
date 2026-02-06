# Coverage Gaps & Refactor Roadmap ✅

Generated: 2026-02-06

## Quick summary
- Total coverage: **63%** across `app/` (from pytest --cov=app)
- Goal: **>=95% per-file coverage**
- Immediate wins: small modules and pure logic (fast to test)
- Harder work: `mib_registrar`, `generator`, `snmp_agent` — large functions, many nested paths, integration-heavy.

---

## Files below 95% (prioritized)

| File | Coverage | Missing (high level) | Priority |
|---|---:|---|---:|
| `app/mib_registrar.py` | **34%** | Many branches in `_build_mib_symbols`, `_build_table_symbols`, register errors, sysOR logic | 1 ✅
| `app/snmp_agent.py` | **28%** | Full `run()` workflow branches (compilation, preloaded model, engine setup, schema loading) | 1 ✅
| `app/generator.py` | **53%** | MIB extraction, row/index extraction, default plugin behaviour, file I/O error handling | 1 ✅
| `app/base_type_handler.py` | **47%** | Display-hint branches, enums, constraints, `create_pysnmp_value` fallbacks, validation | 2 ⚡️
| `app/type_registry_validator.py` | **81%** | All validation failure and success branches (tests added) | 2 ✅
| `app/cli_mib_to_json.py` | **83%** | CLI paths and error cases for missing compiled MIBs / config | 3 🐎
| `app/default_value_plugins.py` | **69%** | Plugin discovery and per-plugin fallback branches | 3 🐎
| `app/plugin_loader.py` | **76%** | Loader error paths and plugin filtering | 3 🐎
| `app/api.py`, `app/__init__.py`, and several `cli_*` modules | 0-62% | Small modules with missing unit tests for CLI behavior, API helpers | 4 🧪

> Files already at or above 95%: `app/app_config.py`, `app/behaviour_store.py`, `app/compiler.py`, `app/mib_metadata.py`, `app/mib_object.py`, `app/mib_registry.py`, `app/mib_table.py`, `app/snmp_transport.py`, `app/table_registrar.py`, `app/trap_sender.py`, `app/type_recorder.py`, `app/types.py` — keep them green.

---

## Multi-nested hotspots (need focused tests + potential refactor)
These are functions with deep nested control flow that make high-percentage coverage hard without refactors.

- `app/generator.py` → generate() → _extract_mib_info() → _get_default_value_from_type_info() → (plugin lookup, enums, constraints). Suggest: unit-test internal functions (or refactor to smaller pure functions), and add plugin mock injection points.

- `app/mib_registrar.py` → `_build_mib_symbols()` → `_build_table_symbols()` → table/object symbolization and `register_mib()` flows. Suggest: break into smaller helpers (build_scalar_symbol, build_table_columns, create_instances), unit-test each with targeted synthetic MIB JSON fixtures.

- `app/snmp_agent.py` → `run()` full workflow. Suggest: split heavy I/O and engine setup into smaller testable methods (already mostly done) and mock `MibCompiler`, `BehaviourGenerator`, and filesystem interactions; add tests for preloaded_model paths and type_registry validation branches.

- `app/base_type_handler.py` → many small branches per type. Suggest: table-driven unit tests covering:
  - display_hint variations
  - enums: common default names vs first value
  - constraints (ValueRangeConstraint, ValueSizeConstraint, size set/range)
  - create_pysnmp_value fallback branches

---

## Concrete next actions (short-term plan)
1. Add unit tests for `BaseTypeHandler` (cover display_hints, enums, constraints, create_pysnmp_value): **1-2 days** (quick wins). ✅
2. Add tests for `type_registry_validator` for both success and multiple failure modes: **0.5-1 day**. ✅
3. Add tests for `generator` internals: extract MIB info and error conditions; mock plugin behavior: **2-3 days**. ⚠️
4. Add tests for `mib_registrar` symbol and table building: cover 4-5 core branches, and refactor helpers if required (**3-5 days**, may overlap with refactor PR). ⚠️
5. Add integration-style tests for `snmp_agent.run()` in isolated modes (preloaded_model, missing compiled MIBs, type registry validation): **2 days**.

---

## Refactor notes / flags for future work
- Flag 1: `mib_registrar` is large and mixes concerns (symbol building, export, table handling). Consider extracting table symbol builder and symbol exporter as separate classes to improve testability.
- Flag 2: `generator.generate()` touches file I/O and data extraction in one function; separate JSON I/O from extraction logic to make extraction pure and testable.
- Flag 3: Add plugin interface docs and explicit injection points for default-value plugins (easier mocking in tests).

---

## Deliverables I can produce now
- Add a new test module `tests/test_base_type_handler.py` with table-driven tests covering 95% of branches.
- Add tests for `type_registry_validator` and `generator` small units.
- Create `docs/COVERAGE_GAPS.md` (this file) and open PR(s) with incremental commits.

---

## Ask / next step
Which file should I start with first? My recommendation: **`base_type_handler.py`** and **`type_registry_validator.py`** for fast wins, then move to **`generator.py`** and **`mib_registrar.py`** for deeper work. Reply with your choice and I'll start adding tests and small refactors. ✅

---

If you want, I can also add GitHub issue templates for each flagged file with checklist items and test ideas. Would you like me to proceed?