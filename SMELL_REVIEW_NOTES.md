# Code Smell Review Notes

Date: 2026-04-09
Scope: quick pass focused on app/ with deeper inspection in app/snmp_agent_runtime_workflow_mixin.py.

## Confirmed smells

### 1) Repeated boundary casts and dynamic typing pressure
- File: app/snmp_agent_runtime_workflow_mixin.py
- Symptom: many cast calls around dynamic APIs and schema access.
- Examples:
  - cast(Iterable[object], result)
  - cast(tuple[object, ...], vb)
  - cast("Callable[[str], object]", raw_lookup_fn)
  - cast("dict[str, object]", schema)
  - cast("list[str]", self.app_config.get("mibs", []))
- Why it smells: repeated type re-assertion usually means boundary types are not modeled strongly enough.

### 2) String-literal casts still used in runtime code
- File: app/snmp_agent_runtime_workflow_mixin.py
- Current examples:
  - cast("Callable[[str], object]", raw_lookup_fn)
  - cast("dict[str, object]", schema)
  - cast("list[str]", self.app_config.get("mibs", []))
- Why it smells: weak tooling visibility and less robust rename/refactor behavior.
- Note: cast("SupportsBoundaryMibBuilder", self.mib_builder) is likely intentional because the type is TYPE_CHECKING-only.

### 3) Broad exception handling in operational flow
- File: app/snmp_agent_runtime_workflow_mixin.py
- Examples:
  - except Exception as exc in SNMP response formatting path (now logs debug)
  - except Exception in _reset_rowstatus_column_prototypes import path
- Why it smells: broad catches can hide real behavior drift if they grow over time.

### 4) Heavy use of Any in hook interaction path
- File: app/snmp_agent_runtime_workflow_mixin.py
- Examples:
  - rowstatus_action: Any
  - is_rowstatus_column: Any
  - resolve_table_cell: Any
- Why it smells: behavior is effectively untyped where most control-flow decisions happen.

## Candidate refactors (small, low-risk)

1. Introduce Protocols for runtime hooks
- Define typed call signatures for rowstatus_action, is_rowstatus_column, resolve_table_cell.
- Replace Any locals with Callable Protocol-compatible variables.

2. Normalize cast style
- Prefer runtime type expressions in cast where possible.
- Keep string-based cast only for TYPE_CHECKING-only symbols.

3. Add boundary helpers
- Add tiny parsing helpers for var-binds and schema objects.
- Move repetitive cast + isinstance sequences into one place.

4. Guardrails for broad exceptions
- Where broad catch is required, include debug logs consistently and limit scope to smallest block.

## Tools to add (non-overlapping with current setup)

Current stack already covers: Ruff, pylint, pyright, mypy.

Useful additions for stylistic/design smells:

1. Radon (+ Xenon)
- Detects cyclomatic complexity and maintainability index.
- Good for spotting methods that need decomposition.

2. Vulture
- Dead code and unused function/class detection.
- Catches stale paths that linters often miss.

3. Refurb
- Python-specific refactoring suggestions and code modernizations.
- Often finds clarity improvements not flagged by Ruff defaults.

4. Semgrep (custom rule set)
- Great for project-specific style rules and anti-patterns.
- Can encode your team conventions once and enforce continuously.

5. Import-linter (if architecture boundaries matter)
- Enforces module dependency contracts.
- Good when package layering starts to drift.

## AI usage recommendation

You do not need to manually review the whole project with AI every time.
A practical workflow is:

1. Run automated style/design tools in CI and collect machine findings.
2. Use AI for triage and fix planning on the top N high-signal findings.
3. Run occasional AI-assisted architecture pass (for boundary typing, module coupling, and duplicate logic), not every PR.

This keeps AI effort targeted and avoids replacing objective static checks with subjective manual scans.
