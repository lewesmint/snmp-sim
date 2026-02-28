# TypeRecorder typing-hardening plan

## Goal
Reduce dynamic-typing risk in `app/type_recorder.py` by systematically replacing broad `object`/reflection-heavy call paths with narrow capability protocols and typed helper boundaries, without changing runtime behavior.

## Process
1. Identify one hotspot category at a time (callables, enum extraction, symbol surface, exception narrowing).
2. Introduce the smallest possible typed helper/protocol for that category.
3. Refactor call sites to use the helper and remove casts/defensive reflection where safe.
4. Run targeted checks (`pyright`, `mypy`) and focused tests.
5. Record progress and move to next category.

## Candidate list (priority order)
- [x] C1: Zero-arg callable boundary
  - Replace ad-hoc callable casting in `safe_call_zero_arg` with a typed resolver helper.
- [x] C2: Enum extraction boundary
  - Replace `items` callable cast and broad exception handling with protocol + narrow exceptions.
- [x] C3: MIB symbol map typing
  - Introduce a dedicated alias for `mibSymbols` shape and move raw map/protocol contracts to adapter boundary modules.
- [x] C4: Symbol processing surface
  - Introduce narrow symbol protocols/aliases for textual convention and object-type paths.
- [ ] C5: Exception narrowing audit
  - Replace `except Exception` where known exception families are sufficient.

## Progress tracker
- [x] P0: Plan created with goal/process/candidates.
- [x] P1: Implement C1-C3 in `app/type_recorder.py`.
- [x] P2: Run diagnostics on touched targets (no file errors).
- [x] P3: Run focused unit tests for `type_recorder` paths.
- [x] P4: Update this file with results and next slice.

## Next slice
- C5 exception narrowing pass in `_seed_base_types_impl`, `_load_mib_symbols`, and `_process_object_type_symbol`.
- Consolidate remaining direct PySNMP runtime interactions in `type_recorder` into boundary adapters where practical.
