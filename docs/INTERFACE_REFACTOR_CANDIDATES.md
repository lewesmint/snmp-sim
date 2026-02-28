# Interface/Protocol Refactor Candidates

Date: 2026-02-28

## Goal
Replace repeated `object`/`Any` + `hasattr`/`getattr` usage with explicit structural protocols in `app/interface_types.py`, similar to the recent `PrettyPrintable` and composed index protocols.

## Architecture Note (Scope)

We are **not** building full type coverage for all of PySNMP/SMI internals.

Instead, we use a two-layer approach:

1. **Small capability protocols** in [app/interface_types.py](app/interface_types.py)
  - Example: `HasName`, `HasSyntax`, `HasGetMaxAccess`, `HasIndexNames`
  - Purpose: narrow dynamic objects safely at boundaries.

2. **Richer typed snapshots/adapters** in [app/mib_builder_adapters.py](app/mib_builder_adapters.py)
  - Example: `MibSymbolSnapshot`
  - Purpose: represent multi-field symbol data in one stable internal type.

Rule of thumb:
- If you need 3+ capabilities together repeatedly, extract through an adapter snapshot.
- Avoid creating large, monolithic protocols that mirror entire PySNMP classes.

## Priority Candidates

### P0 (high value, low risk)

1. `generator` symbol extraction path
   - Location: [app/generator.py](app/generator.py#L313-L326)
   - Current pattern:
     - `hasattr(symbol_obj, "getName")`
     - `hasattr(symbol_obj, "getSyntax")`
     - `getattr(symbol_obj, "getMaxAccess", ...)`
   - Suggested protocol(s):
     - `HasNameAndSyntax`
       - `getName() -> Iterable[int]`
       - `getSyntax() -> object`
     - `HasOptionalMaxAccess`
       - `getMaxAccess() -> object`
   - Benefit: removes multiple dynamic checks in a hot path and improves pyright inference.

2. `mib_browser` OID metadata extraction
   - Location: [ui/mib_browser.py](ui/mib_browser.py#L769-L784)
   - Current pattern:
     - `hasattr(..., "getName"|"getMaxAccess"|"getSyntax"|"getDescription")`
   - Suggested protocol(s):
     - `HasName`
     - `HasOptionalMetadataMethods` (composed from optional access/syntax/description protocols)
   - Benefit: clearer contract for objects displayed in UI tree metadata.

3. `snmp_agent` writable scalar capture
   - Location: [app/snmp_agent.py](app/snmp_agent.py#L2396-L2437)
   - Current pattern:
     - `hasattr(symbol_obj, "name")`
     - `hasattr(symbol_obj, "getMaxAccess")` / `hasattr(symbol_obj, "maxAccess")`
   - Suggested protocol(s):
     - `HasNameTuple` (`name: tuple[int, ...]`)
     - `HasGetMaxAccess` (`getMaxAccess() -> object`)
     - `HasMaxAccessAttr` (`maxAccess: object`)
   - Benefit: narrows dynamic MIB symbol paths and reduces defensive branching.

### P1 (good value, medium risk)

4. `snmp_agent` table update column OID lookup
   - Location: [app/snmp_agent.py](app/snmp_agent.py#L2095-L2105)
   - Current pattern:
     - `hasattr(col_obj, "name") and isinstance(col_obj.name, tuple)`
   - Suggested protocol(s):
     - `HasNameTuple`
   - Benefit: straightforward narrowing and better readability in update loop.

5. `snmp_agent` template instance column derivation
   - Location: [app/snmp_agent.py](app/snmp_agent.py#L1952-L1966)
   - Current pattern:
     - same `name` tuple shape checks for template instances.
   - Suggested protocol(s):
     - `HasNameTuple`
   - Benefit: unify table-instance handling contracts.

6. `generator` trap extraction object methods
   - Location: [app/generator.py](app/generator.py#L459-L485)
   - Current pattern:
     - `hasattr(symbol_obj, "getObjects"|"getDescription"|"getStatus")`
   - Suggested protocol(s):
     - `NotificationLike`
       - `getName()`, optional `getObjects()`, `getDescription()`, `getStatus()`
   - Benefit: less ad-hoc reflection in trap extraction.

### P2 (optional / situational)

7. `generator` type info extraction
   - Location: [app/generator.py](app/generator.py#L606-L623)
   - Current pattern:
     - `getattr(..., "namedValues"|"subtypeSpec"|"values")`
   - Suggested protocol(s):
     - `HasNamedValues`
     - `HasSubtypeSpec`
     - `HasConstraintValues`
   - Benefit: stronger typing, but many variations in pysnmp objects may still require fallbacks.

8. Generic `self` attribute introspection in UI mixins
   - Location examples:
     - [ui/snmp_gui_traps_mixin.py](ui/snmp_gui_traps_mixin.py#L45)
     - [ui/snmp_gui_trap_overrides_mixin.py](ui/snmp_gui_trap_overrides_mixin.py#L79)
   - Suggested approach:
     - typed mixin state attrs on class rather than protocolization first.
   - Benefit: may reduce `getattr(self, ...)` clutter, but touches class design broadly.

## Proposed Additions to `app/interface_types.py`

Candidate protocols to add incrementally:
- `HasNameAndSyntax`
- `HasGetMaxAccess`
- `HasMaxAccessAttr`
- `HasNameTuple`
- `HasDescription`
- `HasStatus`
- `HasObjects`
- `NotificationLike` (composed protocol)

Keep each protocol small and compose via inheritance (as already done with `HasGetIndexNames`).

## Suggested Execution Plan

1. **Pass 1 (safe):** Add `HasNameTuple`, `HasGetMaxAccess`, `HasMaxAccessAttr`, apply in `snmp_agent` only.
2. **Pass 2 (safe):** Add `HasNameAndSyntax` and apply in `generator` symbol extraction.
3. **Pass 3 (medium):** Add `NotificationLike` and refactor `generator` trap extraction.
4. **Pass 4 (optional):** Evaluate `generator` subtype/namedValues protocols after confirming no behavior regressions.

## Success Criteria

- No behavioral changes.
- `pyright` clean on modified files.
- `mypy` clean in configured scope.
- Reduced `hasattr`/`getattr` occurrences in targeted paths.

## Note

Some dynamic checks (platform gates, optional module features) are intentionally reflective and should remain as-is unless we have a stable contract to model.
