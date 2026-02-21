# Top 10 Refactor Tickets (Complexity/Size Hotspots)

Date: 2026-02-21
Source: `scripts/refactor_hotspots.py` run with `--top-functions 20 --min-function-lines 40 --min-complexity 10`

## Priority rubric
- P0: score >= 440
- P1: score 360-439
- P2: score < 360

---

## T01 (P0) — Split `MibRegistrar._build_table_symbols`
- Location: `app/mib_registrar.py:616-976`
- Hotspot: score=520, cc=75, branches=74, lines=361
- Why now: deepest mixed concerns (schema parsing, type conversion, instance construction, write hooks)

### Suggested split boundaries
1. `resolve_table_entry(mib_json, table_name)`
   - Current block: ~lines 628-657
   - Output: `(entry_name, entry_info, entry_oid, index_names)`
2. `collect_table_columns(mib_json, entry_oid, type_registry)`
   - Current block: ~lines 669-726
   - Output: `columns_by_name` + registered column symbols
3. `build_index_tuple(row_data, index_names, columns_by_name, row_idx)`
   - Current block: ~lines 747-772
4. `resolve_row_values(row_data)`
   - Current block: ~lines 779-783
5. `create_column_instance(...)`
   - Current block: ~lines 785-854
6. `attach_instance_write_hooks(inst, ...)`
   - Current block: ~lines 858-969

### Acceptance
- No behavior change in table registration output symbols.
- Existing SET behavior/logging unchanged for writable/read-only columns.

---

## T02 (P0) — Split `api.create_table_row`
- Location: `app/api.py:1723-1982`
- Hotspot: score=482, cc=72, branches=71, lines=260
- Why now: endpoint combines validation, schema fetch, index conversion, defaults merge, persistence

### Suggested split boundaries
1. `load_schema_context(table_oid)`
   - Current block: ~1730-1761
2. `extract_index_columns_fallback(request, columns)`
   - Current block: ~1809-1848
3. `convert_index_value(col_name, value, columns)`
   - Keep but move to module-level utility
   - Current block: ~1850-1888
4. `build_instance_index(index_columns, request_index_values, columns, entry_oid)`
   - Current block: ~1898-1931
5. `merge_column_defaults(columns, incoming_values, default_row, excluded_index_cols)`
   - Current blocks: ~1823-1838 and ~1934-1947 (dedupe)
6. `persist_table_row(table_oid, index_values, merged_values)`
   - Current block: ~1950-1962

### Acceptance
- Same JSON response format and status codes.
- No duplicate default-merge logic remains.

---

## T03 (P0) — Split `api.get_tree_bulk_data`
- Location: `app/api.py:950-1166`
- Hotspot: score=449, cc=68, branches=67, lines=217

### Suggested split boundaries
1. `extract_objects(schema)`
   - Repeated pattern throughout
2. `build_index_source_map(schemas)`
   - Current first pass: ~965-993
3. `find_table_entry(objects, table_oid_parts)`
   - Current: ~1010-1018
4. `collect_parent_instances(table_oid, obj_name, source_info, schemas)`
   - Current block: ~1026-1103
5. `collect_table_rows_instances(obj_data, index_columns, objects)`
   - Current block: ~1113-1130
6. `merge_dynamic_instances(table_oid, entry_obj, index_source_map, instances)`
   - Current block: ~1137-1149

### Acceptance
- Returned `tables` structure remains identical.
- Augmented-table behavior stays parent-driven only.

---

## T04 (P0) — Split `MibRegistrar._build_mib_symbols`
- Location: `app/mib_registrar.py:249-555`
- Hotspot: score=443, cc=64, branches=63, lines=307

### Suggested split boundaries
1. `iter_scalar_candidates(mib_json, table_related_objects)`
2. `resolve_scalar_type_and_value(name, info, type_registry)`
   - Current block: ~276-336
3. `build_scalar_instance(...)`
   - Current block: ~337-367
4. `attach_scalar_sysuptime_read_hook(...)`
   - Current block: ~370-393
5. `attach_scalar_write_hooks(...)`
   - Current block: ~406-531
6. `register_all_tables(...)`
   - Current block: ~538-554

### Acceptance
- Scalar and table symbol export keys unchanged.
- `sysUpTime` dynamic behavior unchanged.

---

## T05 (P1) — Split `SNMPTableResponder._get_oid_value`
- Location: `app/snmp_table_responder.py:225-380`
- Hotspot: score=425, cc=66, branches=65, lines=156

### Suggested split boundaries
1. `collect_table_columns(objects, entry_oid)`
   - Current block: ~246-260
2. `parse_instance_parts(oid, entry_oid)`
3. `resolve_single_column_table_value(...)`
   - Current block: ~268-321
4. `resolve_multi_column_table_value(...)`
   - Current block: ~332-379
5. `build_row_index_string(row, index_columns)`
   - Deduplicate repeated row-index assembly logic

### Acceptance
- Exact OID-to-cell resolution remains equivalent for single/multi-index rows.

---

## T06 (P1) — Split `SNMPGUI._discover_table_instances`
- Location: `ui/snmp_gui.py:5415-5666`
- Hotspot: score=390, cc=57, branches=56, lines=252

### Suggested split boundaries
1. `resolve_entry_metadata(entry_oid)`
   - Current block: ~5419-5443
2. `load_table_schema_instances(entry_oid)`
   - Current block: ~5447-5469
3. `fallback_probe_instances(first_col_oid)`
   - Current block: ~5472-5499
4. `collect_table_columns(entry_tuple)`
   - Current block: ~5509-5515
5. `build_grouped_instance_cells(...)`
   - Current block: ~5538-5604
6. `apply_discovered_instances_to_tree(...)`
   - Current nested `update_ui`: ~5607-5665

### Acceptance
- Tree nodes/values/icons and lazy-load behavior remain unchanged.

---

## T07 (P1) — Split `TypeRecorder.build`
- Location: `app/type_recorder.py:702-929`
- Hotspot: score=385, cc=57, branches=56, lines=228

### Suggested split boundaries
1. `load_compiled_modules(mib_builder)`
   - Current block: ~708-718
2. `process_textual_convention_symbol(...)`
   - Current block: ~729-784
3. `process_object_type_symbol(...)`
   - Current block: ~786-928
4. `derive_metadata_for_syntax(...)`
   - Extract constraints/enums/display logic from duplicated branches

### Acceptance
- Generated type registry content remains semantically identical.

---

## T08 (P1) — Split `api.get_table_schema`
- Location: `app/api.py:478-678`
- Hotspot: score=368, cc=55, branches=54, lines=201

### Suggested split boundaries
1. `find_table_and_entry(parts, schemas)`
   - Current scan block: ~505-547
2. `collect_table_columns(entry_oid, schemas, index_columns, foreign_keys)`
   - Current block: ~565-594
3. `normalize_and_extract_instances(...)`
   - Current block: ~601-647
4. `inject_virtual_index_columns(columns, instances, index_columns)`
   - Current block: ~659-677

### Acceptance
- Response contract unchanged; virtual `__index__` behavior unchanged.

---

## T09 (P1) — Split `SNMPGUI._open_link_dialog`
- Location: `ui/snmp_gui.py:673-932`
- Hotspot: score=362, cc=52, branches=51, lines=260

### Suggested split boundaries
1. `build_link_dialog_shell(link)`
2. `build_selected_tree(frame)` and `build_available_tree(frame)`
3. `compute_available_endpoints(scope, selected_map)`
4. `load_existing_link_selection(link, selected_map)`
5. `save_link_payload(selected_map, vars...)`

### Acceptance
- Dialog UX and persisted link payload stay identical.

---

## T10 (P2) — Split `SNMPGUI._add_instance`
- Location: `ui/snmp_gui.py:4098-4370`
- Hotspot: score=358, cc=51, branches=50, lines=273

### Suggested split boundaries
1. `resolve_selected_table_item()`
   - Current top selection walk: ~4101-4130
2. `fetch_table_schema_or_error(table_oid)`
   - Current block: ~4137-4149
3. `compute_column_defaults(schema)`
   - Current block: ~4189-4227
4. `render_add_instance_dialog(schema, index_columns, column_defaults)`
5. `submit_add_instance(table_oid, index_values, column_defaults)`
   - Current nested `on_add`: ~4333-4368

### Acceptance
- Added instance semantics and follow-up refresh behavior remain the same.

---

## Quick execution order
1. T02 + T08 (API cohesion and duplicated table/index logic)
2. T01 + T04 (registrar split around symbol/writer hooks)
3. T05 (table responder resolution dedupe)
4. T07 (type recorder decomposition)
5. T06 + T10 + T09 (UI method decomposition)
