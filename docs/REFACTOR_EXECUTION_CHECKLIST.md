# Refactor Execution Checklist

Date: 2026-02-21
Plan source: `docs/REFACTOR_TICKETS_TOP10.md`

Use this as the working checklist while implementing the 10-ticket refactor plan.

## Session metadata
- [ ] Owner assigned
- [ ] Branch created for refactor work
- [ ] Baseline saved (`ruff --select C90,PLR --statistics`)
- [ ] Baseline hotspots saved (`python scripts/refactor_hotspots.py ...`)

---

## Phase 1 — API refactors

### T02 — Split `api.create_table_row`
- [x] Extract `load_schema_context(...)`
- [x] Extract index parsing/fallback helper
- [x] Move `convert_index_value(...)` to shared utility scope
- [x] Extract `build_instance_index(...)`
- [x] Deduplicate default-merge logic into one helper
- [x] Keep response/status behavior unchanged
- [x] Run: `ruff check app/api.py --select C90,PLR`
- [x] Run: `pytest -q tests -k "table_row"`

### T08 — Split `api.get_table_schema`
- [x] Extract table/entry resolver
- [x] Extract column collector
- [x] Extract instance normalizer
- [x] Extract virtual index injector
- [x] Keep response schema unchanged
- [x] Run: `ruff check app/api.py --select C90,PLR`
- [x] Run: `pytest -q tests -k "table_schema"`

### Phase 1 exit criteria
- [x] No new API contract changes
- [x] Complexity reduced in touched functions
- [x] Phase tests pass

---

## Phase 2 — Registrar decomposition

### T01 — Split `MibRegistrar._build_table_symbols`
- [x] Extract entry resolver
- [x] Extract column collector
- [x] Extract index tuple builder
- [x] Extract row value resolver
- [x] Extract instance creator
- [x] Extract write hook attacher
- [x] Keep symbol names/instance naming unchanged
- [x] Run: `ruff check app/mib_registrar.py --select C90,PLR`
- [x] Run: `pytest -q tests -k "mib_registrar"`

### T04 — Split `MibRegistrar._build_mib_symbols`
- [x] Extract scalar candidate iterator
- [x] Extract type/value resolver
- [x] Extract scalar builder
- [x] Extract sysUpTime hook setup
- [x] Extract scalar write hook setup
- [x] Extract table registration path
- [x] Keep registration behavior unchanged
- [x] Run: `ruff check app/mib_registrar.py --select C90,PLR`
- [x] Run: `pytest -q tests -k "mib_registrar"`

### Phase 2 exit criteria
- [x] Scalar/table export behavior unchanged
- [x] SET hook behavior unchanged
- [x] Phase tests pass

---

## Phase 3 — Table lookup correctness

### T05 — Split `SNMPTableResponder._get_oid_value`
- [x] Extract column collector helper
- [x] Extract instance parser helper
- [x] Extract single-column lookup helper
- [x] Extract multi-column lookup helper
- [x] Deduplicate row-index string builder
- [x] Keep OID-to-value behavior identical
- [x] Run: `ruff check app/snmp_table_responder.py --select C90,PLR`
- [x] Run: `pytest -q tests -k "table_responder or getnext or table"`

### Phase 3 exit criteria
- [x] No regressions in table lookups
- [x] Phase tests pass

---

## Phase 4 — Type recorder cleanup

### T07 — Split `TypeRecorder.build`
- [x] Extract compiled module loader
- [x] Extract textual-convention symbol processor
- [x] Extract object-type symbol processor
- [x] Consolidate metadata derivation logic
- [x] Keep registry output semantically equivalent
- [x] Run: `ruff check app/type_recorder.py --select C90,PLR`
- [x] Run: `pytest -q tests -k "type_recorder"`

### Phase 4 exit criteria
- [x] Type registry equivalence spot-checked
- [x] Phase tests pass

---

## Phase 5 — UI decomposition

### T06 — Split `SNMPGUI._discover_table_instances`
- [x] Extract entry metadata resolver
- [x] Extract schema instance loader
- [x] Extract fallback probe path
- [x] Extract grouped cell builder
- [x] Extract UI apply/update path
- [x] Keep tree display behavior unchanged

### T10 — Split `SNMPGUI._add_instance`
- [x] Extract selected-table resolver
- [x] Extract schema fetch helper
- [x] Extract default-value collector
- [x] Extract dialog renderer
- [x] Extract submit handler
- [x] Keep add-instance behavior unchanged

### T09 — Split `SNMPGUI._open_link_dialog`
- [x] Extract dialog shell builder
- [x] Extract selected/available tree builders
- [x] Extract endpoint computation
- [x] Extract existing-link loader
- [x] Extract payload save handler
- [x] Keep UX and payload unchanged

### Phase 5 validation
- [x] Run: `ruff check ui/snmp_gui.py --select C90,PLR`
- [ ] Run manual UI smoke checks in `manual-tests/ui/`

### Phase 5 exit criteria
- [ ] No UI workflow regressions observed
- [ ] Manual checks pass

---

## Final verification
- [x] Run: `ruff check . --select C90,PLR --statistics`
- [x] Run: `python scripts/refactor_hotspots.py . --top-functions 20 --min-function-lines 40 --min-complexity 10`
- [x] Run: `pytest -q`
- [x] Compare pre/post hotspot rankings
- [x] Confirm no new lint/type errors in touched files
	- Note: refactored targets validate clean in current diagnostics; `app/api.py` still has pre-existing lint debt outside this refactor scope.

## Closeout
- [x] Update `docs/REFACTOR_TICKETS_TOP10.md` with completed ticket notes
- [x] Add brief changelog summary (files touched + risk notes)
- [x] Prepare PR description with before/after complexity stats
