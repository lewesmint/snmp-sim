# Ignore/noqa Audit (Codebase-wide)

Scope: Python + lint/type config files; docs/manual/reference/generated folders excluded.

## Totals
- Inline suppressions: **182**
- `noqa`: **83**
- `pylint_disable`: **48**
- `pyright_ignore`: **1**
- `ruff_noqa_file`: **17**
- `type_ignore`: **33**

## Heuristic justification summary
- `justified`: **5**
- `partly-justified`: **93**
- `review`: **84**

## Highest-concentration files
- `ui/mib_browser.py`: 20
- `ui/snmp_gui.py`: 14
- `snmp_wrapper/snmp_wrapper.py`: 13
- `app/snmp_agent.py`: 10
- `app/type_recorder.py`: 9
- `app/cli_mib_to_json.py`: 8
- `tests/misc/test_coverage_gaps.py`: 8
- `tests/unit/mib/test_mib_registrar_more.py`: 7
- `app/generator.py`: 6
- `tests/unit/ui/test_ui_common.py`: 6
- `run_agent_with_rest.py`: 5
- `app/table_registrar.py`: 5
- `app/base_type_handler.py`: 5
- `tests/misc/test_generator_more.py`: 5
- `app/mib_registrar.py`: 4
- `app/app_logger.py`: 4
- `tests/unit/table/test_table_registration.py`: 4
- `app/api_links.py`: 3
- `app/mib_registrar_helpers.py`: 3
- `app/api_table_views.py`: 3
- `app/api_table_helpers.py`: 3
- `app/api_config.py`: 3
- `app/snmp_table_responder.py`: 3
- `tests/unit/ui/test_mib_browser_unit.py`: 3
- `tests/unit/agent/test_snmp_agent_unit.py`: 3
- `tests/unit/scripts/test_run_agent_with_rest.py`: 3
- `ui/snmp_gui_traps_mixin.py`: 2
- `app/api_traps.py`: 2
- `tests/misc/test_pysnmp_type_sources.py`: 2
- `tests/unit/agent/test_snmp_agent_additional.py`: 2

## Config-level ignore settings
### pyproject.toml
- `warn_unused_ignores = true`
- `ignore_missing_imports = false`
- `exclude = '(^|/)(retired|compiled-mibs-test|compiled-mibs|minimal-for-reference|manual-tests|logs|tests)/'`
- `ignore_missing_imports = true`
- `disable_error_code = ["import-untyped"]`
- `ignore_missing_imports = true`
- `disable_error_code = ["import-untyped"]`
- `ignore_missing_imports = true`
- `disable_error_code = ["import-untyped"]`
- `ignore_missing_imports = true`
- `disable_error_code = ["import-untyped"]`
- `exclude = [`
- `ignore = [`
- `disable = [`
- `ignore = ["retired", "compiled-mibs", "compiled-mibs-test", "manual-tests", "tests"]`
- `ignore-paths = [`
- `"--ignore=tests",`
- `"--ignore=minimal-for-reference",`
- `"--ignore=compiled-mibs",`
- `"--ignore=compiled-mibs-test",`
- `"--ignore=retired",`
- `"--ignore=manual-tests",`
- `"--ignore=logs",`
- `"--ignore=snmp_wrapper"`
- `"ignore::DeprecationWarning",`
- `exclude = [`

### .flake8
- `extend-ignore =`
- `per-file-ignores =`
- `exclude =`

## Full inline suppression inventory
| File | Line | Kind | Status | Directive |
|---|---:|---|---|---|
| `app/api_config.py` | 3 | `ruff_noqa_file` | `review` | `# ruff: noqa: I001` |
| `app/api_config.py` | 17 | `noqa` | `partly-justified` | `from app.api_shared import JsonObject  # noqa: TC001` |
| `app/api_config.py` | 72 | `noqa` | `partly-justified` | `state.snmp_agent._save_mib_state()  # noqa: SLF001` |
| `app/api_links.py` | 135 | `noqa` | `partly-justified` | `state.snmp_agent._update_table_cell_values(  # noqa: SLF001` |
| `app/api_links.py` | 175 | `noqa` | `partly-justified` | `state.snmp_agent._save_mib_state()  # noqa: SLF001` |
| `app/api_links.py` | 196 | `noqa` | `partly-justified` | `state.snmp_agent._save_mib_state()  # noqa: SLF001` |
| `app/api_table_helpers.py` | 15 | `noqa` | `partly-justified` | `def extract_schema_objects(schema: Any) -> dict[str, Any]:  # noqa: ANN401` |
| `app/api_table_helpers.py` | 43 | `noqa` | `partly-justified` | `def should_use_default_value(val: Any) -> bool:  # noqa: ANN401` |
| `app/api_table_helpers.py` | 107 | `noqa` | `partly-justified` | `def convert_index_value(  # noqa: PLR0912` |
| `app/api_table_views.py` | 176 | `noqa` | `partly-justified` | `def _resolve_table_cell_context(  # noqa: C901, PLR0912` |
| `app/api_table_views.py` | 269 | `noqa` | `partly-justified` | `def _try_schema_row_value(  # noqa: C901, PLR0912` |
| `app/api_table_views.py` | 375 | `noqa` | `partly-justified` | `def get_tree_bulk_data() -> dict[str, object]:  # noqa: C901, PLR0912, PLR0915` |
| `app/api_tables.py` | 10 | `noqa` | `partly-justified` | `from app.api_shared import JsonValue  # noqa: TC001` |
| `app/api_traps.py` | 129 | `noqa` | `partly-justified` | `def get_trap_varbinds(trap_name: str) -> dict[str, object]:  # noqa: C901, PLR0912, PLR0915` |
| `app/api_traps.py` | 285 | `noqa` | `partly-justified` | `async def send_trap(request: TrapSendRequest) -> dict[str, object]:  # noqa: C901, PLR0912` |
| `app/app_logger.py` | 66 | `type_ignore` | `review` | `class FlushingStreamHandler(logging.StreamHandler):  # type: ignore[type-arg]` |
| `app/app_logger.py` | 196 | `noqa` | `partly-justified` | `def warning(msg: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401` |
| `app/app_logger.py` | 201 | `noqa` | `partly-justified` | `def error(msg: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401` |
| `app/app_logger.py` | 206 | `noqa` | `partly-justified` | `def info(msg: str, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401` |
| `app/base_type_handler.py` | 20 | `pylint_disable` | `review` | `class MibBuilder(Protocol):  # pylint: disable=too-few-public-methods` |
| `app/base_type_handler.py` | 25 | `pylint_disable` | `review` | `...  # pylint: disable=unnecessary-ellipsis` |
| `app/base_type_handler.py` | 28 | `pylint_disable` | `review` | `class TypeFactory(Protocol):  # pylint: disable=too-few-public-methods` |
| `app/base_type_handler.py` | 33 | `pylint_disable` | `review` | `...  # pylint: disable=unnecessary-ellipsis` |
| `app/base_type_handler.py` | 208 | `noqa` | `justified` | `return "0.0.0.0"  # noqa: S104` |
| `app/cli_mib_to_json.py` | 24 | `noqa` | `partly-justified` | `print(f"WARNING: MIB source file {mib_txt_path} not found for import check.")  # noqa: T201` |
| `app/cli_mib_to_json.py` | 52 | `noqa` | `partly-justified` | `print(  # noqa: T201` |
| `app/cli_mib_to_json.py` | 100 | `noqa` | `partly-justified` | `print(  # noqa: T201` |
| `app/cli_mib_to_json.py` | 109 | `noqa` | `partly-justified` | `print("No MIBs configured", file=sys.stderr)  # noqa: T201` |
| `app/cli_mib_to_json.py` | 114 | `noqa` | `partly-justified` | `print(  # noqa: T201` |
| `app/cli_mib_to_json.py` | 120 | `noqa` | `partly-justified` | `print(f"Schema JSON written to {json_path}")  # noqa: T201` |
| `app/cli_mib_to_json.py` | 124 | `noqa` | `partly-justified` | `print(  # noqa: T201` |
| `app/cli_mib_to_json.py` | 140 | `noqa` | `partly-justified` | `print(f"Schema JSON written to {json_path}")  # noqa: T201` |
| `app/generator.py` | 54 | `noqa` | `partly-justified` | `def generate(  # noqa: C901, PLR0912, PLR0915` |
| `app/generator.py` | 272 | `noqa` | `partly-justified` | `def _extract_mib_info(  # noqa: C901, PLR0912, PLR0915` |
| `app/generator.py` | 430 | `noqa` | `partly-justified` | `def _extract_traps(  # noqa: C901` |
| `app/generator.py` | 633 | `noqa` | `partly-justified` | `def _get_default_index_value(  # noqa: PLR0911` |
| `app/generator.py` | 704 | `noqa` | `partly-justified` | `def _get_default_value(self, syntax: str, symbol_name: str) -> object:  # noqa: C901, PLR0911` |
| `app/generator.py` | 731 | `noqa` | `justified` | `return "0.0.0.0"  # noqa: S104` |
| `app/mib_registrar.py` | 7 | `pylint_disable` | `review` | `# pylint: disable=broad-exception-caught,logging-fstring-interpolation` |
| `app/mib_registrar.py` | 8 | `pylint_disable` | `review` | `# pylint: disable=redefined-builtin,invalid-name` |
| `app/mib_registrar.py` | 416 | `noqa` | `partly-justified` | `is_writable: bool,  # noqa: FBT001` |
| `app/mib_registrar.py` | 442 | `noqa` | `partly-justified` | `is_writable: bool,  # noqa: FBT001` |
| `app/mib_registrar_helpers.py` | 142 | `noqa` | `partly-justified` | `is_writable: bool,  # noqa: FBT001` |
| `app/mib_registrar_helpers.py` | 214 | `noqa` | `partly-justified` | `is_writable: bool,  # noqa: FBT001` |
| `app/mib_registrar_helpers.py` | 806 | `type_ignore` | `review` | `inst_name_tuple = tuple(inst.name)  # type: ignore[attr-defined]` |
| `app/snmp_agent.py` | 5 | `pylint_disable` | `partly-justified` | `# pylint: disable=invalid-name,line-too-long,too-many-lines,missing-class-docstring` |
| `app/snmp_agent.py` | 6 | `pylint_disable` | `partly-justified` | `# pylint: disable=too-many-instance-attributes,too-many-locals,too-many-branches` |
| `app/snmp_agent.py` | 7 | `pylint_disable` | `partly-justified` | `# pylint: disable=too-many-statements,too-many-nested-blocks,too-many-return-statements` |
| `app/snmp_agent.py` | 8 | `ruff_noqa_file` | `review` | `# ruff: noqa: B007,C901,D101,D107,E501,EM101,EM102,FBT001,FBT002,I001,N806` |
| `app/snmp_agent.py` | 9 | `ruff_noqa_file` | `review` | `# ruff: noqa: PERF102,PERF203,PERF401,PERF403,PLC0415,PLR0911,PLR0912,PLR0914` |
| `app/snmp_agent.py` | 10 | `ruff_noqa_file` | `review` | `# ruff: noqa: PLR0915,PLR2004,PLW2901,PTH103,PTH120,PTH123,PTH204,RET504,RUF005` |
| `app/snmp_agent.py` | 11 | `ruff_noqa_file` | `review` | `# ruff: noqa: RUF059,RUF100,S101,S104,SIM102,SLF001,T201,TC002,TC003,TC006,TRY003` |
| `app/snmp_agent.py` | 12 | `ruff_noqa_file` | `review` | `# ruff: noqa: TRY300,TRY400,TRY401,UP037,UP045` |
| `app/snmp_agent.py` | 29 | `noqa` | `partly-justified` | `import plugins.date_and_time  # noqa: F401  # pylint: disable=unused-import` |
| `app/snmp_agent.py` | 29 | `pylint_disable` | `review` | `import plugins.date_and_time  # noqa: F401  # pylint: disable=unused-import` |
| `app/snmp_table_responder.py` | 8 | `pylint_disable` | `review` | `# pylint: disable=logging-fstring-interpolation,unused-variable` |
| `app/snmp_table_responder.py` | 143 | `noqa` | `partly-justified` | `def _get_all_table_oids(self) -> list[tuple[int, ...]]:  # noqa: C901, PLR0912, PLR0915` |
| `app/snmp_table_responder.py` | 351 | `noqa` | `partly-justified` | `def _get_oid_value(self, oid: tuple[int, ...]) -> object \| None:  # noqa: PLR0911` |
| `app/table_registrar.py` | 7 | `pylint_disable` | `review` | `# pylint: disable=invalid-name` |
| `app/table_registrar.py` | 23 | `noqa` | `partly-justified` | `def __init__(  # noqa: PLR0913` |
| `app/table_registrar.py` | 92 | `noqa` | `partly-justified` | `def register_tables(  # noqa: C901, PLR0912` |
| `app/table_registrar.py` | 186 | `noqa` | `partly-justified` | `def register_single_table(  # noqa: C901` |
| `app/table_registrar.py` | 359 | `noqa` | `partly-justified` | `def _register_row_instances(  # noqa: C901, PLR0912, PLR0913` |
| `app/type_recorder.py` | 3 | `pylint_disable` | `partly-justified` | `# pylint: disable=broad-exception-caught,redefined-outer-name,reimported,too-few-public-methods,too-many-locals,too-many-branches` |
| `app/type_recorder.py` | 4 | `ruff_noqa_file` | `review` | `# ruff: noqa: D205, D401` |
| `app/type_recorder.py` | 57 | `noqa` | `partly-justified` | `def getSyntax(self) -> object:  # pylint: disable=invalid-name  # noqa: N802` |
| `app/type_recorder.py` | 57 | `pylint_disable` | `review` | `def getSyntax(self) -> object:  # pylint: disable=invalid-name  # noqa: N802` |
| `app/type_recorder.py` | 64 | `noqa` | `partly-justified` | `mibSymbols: Mapping[str, Mapping[str, object]]  # noqa: N815` |
| `app/type_recorder.py` | 609 | `noqa` | `partly-justified` | `def _drop_dominated_value_ranges(  # noqa: C901, PLR0912` |
| `app/type_recorder.py` | 808 | `noqa` | `partly-justified` | `allow_metadata: bool,  # noqa: FBT001` |
| `app/type_recorder.py` | 841 | `noqa` | `partly-justified` | `def _process_object_type_symbol(  # noqa: C901, PLR0912` |
| `app/type_recorder.py` | 987 | `noqa` | `partly-justified` | `print(f"Wrote {len(recorder.registry)} types to {args.output}")  # noqa: T201` |
| `app/value_links.py` | 67 | `noqa` | `partly-justified` | `def add_link(  # noqa: PLR0913` |
| `run_agent_with_rest.py` | 39 | `noqa` | `justified` | `API_HOST = "0.0.0.0"  # noqa: S104` |
| `run_agent_with_rest.py` | 116 | `noqa` | `partly-justified` | `["netstat", "-ano"],  # noqa: S607` |
| `run_agent_with_rest.py` | 139 | `noqa` | `partly-justified` | `return subprocess.check_output(  # noqa: S603` |
| `run_agent_with_rest.py` | 214 | `noqa` | `partly-justified` | `subprocess.check_call(  # noqa: S603` |
| `run_agent_with_rest.py` | 215 | `noqa` | `partly-justified` | `["taskkill", "/PID", str(pid), "/T", "/F"],  # noqa: S607` |
| `scripts/check_all.py` | 2 | `ruff_noqa_file` | `review` | `# ruff: noqa: INP001` |
| `scripts/check_all.py` | 109 | `noqa` | `partly-justified` | `completed = subprocess.run(command, cwd=str(cwd), check=False)  # noqa: S603` |
| `scripts/fix_missing_docstrings.py` | 2 | `ruff_noqa_file` | `review` | `# ruff: noqa: INP001` |
| `scripts/fix_missing_docstrings.py` | 36 | `noqa` | `partly-justified` | `result = subprocess.run(  # noqa: S603` |
| `snmp_traps/trap_receiver.py` | 388 | `noqa` | `justified` | `default="0.0.0.0",  # noqa: S104` |
| `snmp_wrapper/snmp_wrapper.py` | 2 | `ruff_noqa_file` | `review` | `# ruff: noqa: INP001` |
| `snmp_wrapper/snmp_wrapper.py` | 3 | `pylint_disable` | `partly-justified` | `# pylint: disable=global-statement,too-many-arguments,too-many-positional-arguments` |
| `snmp_wrapper/snmp_wrapper.py` | 84 | `noqa` | `partly-justified` | `global _GLOBAL_LOOP_THREAD  # noqa: PLW0603` |
| `snmp_wrapper/snmp_wrapper.py` | 131 | `noqa` | `partly-justified` | `async def _get_async(  # noqa: PLR0913` |
| `snmp_wrapper/snmp_wrapper.py` | 150 | `noqa` | `partly-justified` | `async def _set_async(  # noqa: PLR0913` |
| `snmp_wrapper/snmp_wrapper.py` | 169 | `noqa` | `partly-justified` | `async def _next_async(  # noqa: PLR0913` |
| `snmp_wrapper/snmp_wrapper.py` | 212 | `noqa` | `partly-justified` | `def get_sync(  # noqa: PLR0913` |
| `snmp_wrapper/snmp_wrapper.py` | 220 | `noqa` | `partly-justified` | `use_persistent_loop: bool = False,  # noqa: FBT001, FBT002` |
| `snmp_wrapper/snmp_wrapper.py` | 269 | `noqa` | `partly-justified` | `def set_sync(  # noqa: PLR0913` |
| `snmp_wrapper/snmp_wrapper.py` | 277 | `noqa` | `partly-justified` | `use_persistent_loop: bool = False,  # noqa: FBT001, FBT002` |
| `snmp_wrapper/snmp_wrapper.py` | 326 | `noqa` | `partly-justified` | `def get_next_sync(  # noqa: PLR0913` |
| `snmp_wrapper/snmp_wrapper.py` | 334 | `noqa` | `partly-justified` | `use_persistent_loop: bool = False,  # noqa: FBT001, FBT002` |
| `snmp_wrapper/snmp_wrapper.py` | 556 | `noqa` | `partly-justified` | `global _GLOBAL_LOOP_THREAD  # noqa: PLW0603` |
| `snmp_wrapper/test_wrapper.py` | 2 | `ruff_noqa_file` | `review` | `# ruff: noqa: B007, BLE001, ERA001, EXE001, PLC0415, PLR2004, PT018, S101, T201` |
| `tests/misc/test_basic_models.py` | 268 | `type_ignore` | `review` | `AppLogger.configure(cfg)  # type: ignore[arg-type]` |
| `tests/misc/test_coverage_gaps.py` | 54 | `type_ignore` | `review` | `mock_registrar._resolve_snmp_type = mocker.Mock(  # type: ignore[method-assign]` |
| `tests/misc/test_coverage_gaps.py` | 90 | `type_ignore` | `review` | `mock_registrar._resolve_snmp_type = mocker.Mock(return_value=int)  # type: ignore[method-assign]` |
| `tests/misc/test_coverage_gaps.py` | 121 | `type_ignore` | `review` | `mock_registrar._resolve_snmp_type = mocker.Mock(  # type: ignore[method-assign]` |
| `tests/misc/test_coverage_gaps.py` | 154 | `type_ignore` | `review` | `mock_registrar._resolve_snmp_type = mocker.Mock(return_value=int)  # type: ignore[method-assign]` |
| `tests/misc/test_coverage_gaps.py` | 272 | `type_ignore` | `review` | `agent.MibScalarInstance = mocker.Mock()  # type: ignore[attr-defined]` |
| `tests/misc/test_coverage_gaps.py` | 273 | `type_ignore` | `review` | `agent.MibTable = mocker.Mock()  # type: ignore[attr-defined]` |
| `tests/misc/test_coverage_gaps.py` | 274 | `type_ignore` | `review` | `agent.MibTableRow = mocker.Mock()  # type: ignore[attr-defined]` |
| `tests/misc/test_coverage_gaps.py` | 275 | `type_ignore` | `review` | `agent.MibTableColumn = mocker.Mock()  # type: ignore[attr-defined]` |
| `tests/misc/test_generator_more.py` | 3 | `pylint_disable` | `partly-justified` | `# pylint: disable=too-many-lines,missing-function-docstring,protected-access` |
| `tests/misc/test_generator_more.py` | 4 | `pylint_disable` | `review` | `# pylint: disable=missing-class-docstring,invalid-name,too-few-public-methods` |
| `tests/misc/test_generator_more.py` | 5 | `pylint_disable` | `review` | `# pylint: disable=import-outside-toplevel,import-error,unused-argument` |
| `tests/misc/test_generator_more.py` | 6 | `pylint_disable` | `review` | `# pylint: disable=broad-exception-raised,unused-variable` |
| `tests/misc/test_generator_more.py` | 16 | `pylint_disable` | `review` | `from app.generator import BehaviourGenerator  # pylint: disable=import-error` |
| `tests/misc/test_pysnmp_type_sources.py` | 174 | `pylint_disable` | `review` | `# pylint: disable=invalid-name` |
| `tests/misc/test_pysnmp_type_sources.py` | 221 | `pylint_disable` | `review` | `# pylint: disable=invalid-name` |
| `tests/unit/agent/test_snmp_agent_additional.py` | 340 | `type_ignore` | `review` | `assert fake_scalar.syntax == "new_value"  # type: ignore[comparison-overlap]` |
| `tests/unit/agent/test_snmp_agent_additional.py` | 428 | `type_ignore` | `review` | `agent._save_mib_state = lambda: saved.setdefault("called", True)  # type: ignore[method-assign]` |
| `tests/unit/agent/test_snmp_agent_unit.py` | 205 | `type_ignore` | `review` | `mod.MibRegistrar = DummyRegistrar  # type: ignore[attr-defined]` |
| `tests/unit/agent/test_snmp_agent_unit.py` | 238 | `type_ignore` | `review` | `mod.MibRegistrar = DummyReg  # type: ignore[attr-defined]` |
| `tests/unit/agent/test_snmp_agent_unit.py` | 257 | `type_ignore` | `review` | `mod_bad.MibRegistrar = BadMod.MibRegistrar  # type: ignore[attr-defined]` |
| `tests/unit/mib/test_mib_registrar_more.py` | 1 | `pylint_disable` | `review` | `# pylint: disable=protected-access,unused-argument,attribute-defined-outside-init` |
| `tests/unit/mib/test_mib_registrar_more.py` | 2 | `pylint_disable` | `review` | `# pylint: disable=redefined-outer-name,reimported,pointless-string-statement` |
| `tests/unit/mib/test_mib_registrar_more.py` | 3 | `pylint_disable` | `review` | `# pylint: disable=broad-exception-caught,trailing-whitespace,line-too-long` |
| `tests/unit/mib/test_mib_registrar_more.py` | 4 | `pylint_disable` | `partly-justified` | `# pylint: disable=too-many-lines,missing-module-docstring,missing-class-docstring` |
| `tests/unit/mib/test_mib_registrar_more.py` | 5 | `pylint_disable` | `review` | `# pylint: disable=missing-function-docstring,invalid-name,too-few-public-methods` |
| `tests/unit/mib/test_mib_registrar_more.py` | 6 | `pylint_disable` | `review` | `# pylint: disable=import-outside-toplevel,consider-iterating-dictionary` |
| `tests/unit/mib/test_mib_registrar_more.py` | 7 | `pylint_disable` | `review` | `# pylint: disable=use-implicit-booleaness-not-comparison` |
| `tests/unit/scripts/test_run_agent_with_rest.py` | 1 | `pylint_disable` | `review` | `# pylint: disable=missing-module-docstring,missing-function-docstring` |
| `tests/unit/scripts/test_run_agent_with_rest.py` | 2 | `pylint_disable` | `review` | `# pylint: disable=missing-class-docstring,too-few-public-methods` |
| `tests/unit/scripts/test_run_agent_with_rest.py` | 3 | `pylint_disable` | `review` | `# pylint: disable=import-error,no-name-in-module` |
| `tests/unit/table/test_table_registration.py` | 52 | `type_ignore` | `review` | `agent.MibTable = mocker.MagicMock()  # type: ignore[attr-defined]` |
| `tests/unit/table/test_table_registration.py` | 53 | `type_ignore` | `review` | `agent.MibTableRow = mocker.MagicMock()  # type: ignore[attr-defined]` |
| `tests/unit/table/test_table_registration.py` | 54 | `type_ignore` | `review` | `agent.MibTableColumn = mocker.MagicMock()  # type: ignore[attr-defined]` |
| `tests/unit/table/test_table_registration.py` | 55 | `type_ignore` | `review` | `agent.MibScalar = mocker.MagicMock()  # type: ignore[attr-defined]` |
| `tests/unit/trap/test_trap_sender.py` | 57 | `pyright_ignore` | `review` | `trap_sender._coerce_varbind("invalid")  # pyright: ignore[reportArgumentType]` |
| `tests/unit/type_system/test_base_type_handler_more.py` | 268 | `type_ignore` | `review` | `proto_mod.rfc1902 = fake_rfc  # type: ignore[attr-defined]` |
| `tests/unit/type_system/test_base_type_handler_more.py` | 285 | `type_ignore` | `review` | `proto_mod.rfc1902 = original_rfc1902  # type: ignore[attr-defined]` |
| `tests/unit/ui/test_mib_browser_unit.py` | 190 | `pylint_disable` | `review` | `class Sym:  # pylint: disable=too-few-public-methods` |
| `tests/unit/ui/test_mib_browser_unit.py` | 193 | `noqa` | `partly-justified` | `def getName(self) -> tuple[int, ...]:  # noqa: N802  # pylint: disable=invalid-name` |
| `tests/unit/ui/test_mib_browser_unit.py` | 193 | `pylint_disable` | `review` | `def getName(self) -> tuple[int, ...]:  # noqa: N802  # pylint: disable=invalid-name` |
| `tests/unit/ui/test_ui_common.py` | 60 | `type_ignore` | `review` | `logger = Logger(widget)  # type: ignore[arg-type]` |
| `tests/unit/ui/test_ui_common.py` | 74 | `type_ignore` | `review` | `logger = Logger(BrokenTextWidget())  # type: ignore[arg-type]` |
| `tests/unit/ui/test_ui_common.py` | 82 | `type_ignore` | `review` | `logger = Logger(FakeTextWidget())  # type: ignore[arg-type]` |
| `tests/unit/ui/test_ui_common.py` | 84 | `type_ignore` | `review` | `logger.set_log_widget(FakeTextWidget())  # type: ignore[arg-type]` |
| `tests/unit/ui/test_ui_common.py` | 94 | `type_ignore` | `review` | `save_gui_log(widget, "test.log")  # type: ignore[arg-type]` |
| `tests/unit/ui/test_ui_common.py` | 116 | `type_ignore` | `review` | `save_gui_log(BrokenGetWidget(), "test.log")  # type: ignore[arg-type]` |
| `ui/mib_browser.py` | 6 | `pylint_disable` | `review` | `# pylint: disable=broad-exception-caught,attribute-defined-outside-init,no-else-return` |
| `ui/mib_browser.py` | 7 | `pylint_disable` | `partly-justified` | `# pylint: disable=too-many-lines,too-many-instance-attributes,too-many-arguments` |
| `ui/mib_browser.py` | 8 | `pylint_disable` | `partly-justified` | `# pylint: disable=too-many-positional-arguments,too-many-locals,too-many-statements` |
| `ui/mib_browser.py` | 9 | `pylint_disable` | `partly-justified` | `# pylint: disable=too-many-nested-blocks,too-many-branches` |
| `ui/mib_browser.py` | 53 | `noqa` | `partly-justified` | `tk._default_root = tk.Tcl()  # type: ignore[attr-defined]  # noqa: SLF001` |
| `ui/mib_browser.py` | 53 | `type_ignore` | `review` | `tk._default_root = tk.Tcl()  # type: ignore[attr-defined]  # noqa: SLF001` |
| `ui/mib_browser.py` | 64 | `noqa` | `partly-justified` | `def __init__(  # noqa: PLR0913` |
| `ui/mib_browser.py` | 186 | `noqa` | `partly-justified` | `except (AttributeError, LookupError, OSError, TypeError, ValueError):  # noqa: PERF203` |
| `ui/mib_browser.py` | 219 | `noqa` | `partly-justified` | `def _setup_browser_tab(self) -> None:  # noqa: PLR0915` |
| `ui/mib_browser.py` | 465 | `noqa` | `partly-justified` | `def _extract_mib_imports(self, mib_file_path: Path) -> list[str]:  # noqa: C901, PLR0912` |
| `ui/mib_browser.py` | 627 | `noqa` | `partly-justified` | `def load_mib(self, mib_names: list[str] \| str) -> tuple[list[str], list[str]]:  # noqa: PLR0912` |
| `ui/mib_browser.py` | 665 | `noqa` | `partly-justified` | `except (  # noqa: PERF203` |
| `ui/mib_browser.py` | 716 | `noqa` | `partly-justified` | `except (  # noqa: PERF203` |
| `ui/mib_browser.py` | 786 | `noqa` | `partly-justified` | `except (  # noqa: PERF203` |
| `ui/mib_browser.py` | 895 | `noqa` | `partly-justified` | `except (  # noqa: PERF203` |
| `ui/mib_browser.py` | 1071 | `noqa` | `partly-justified` | `def _refresh_cached_mibs(self) -> None:  # noqa: C901, PLR0912, PLR0915` |
| `ui/mib_browser.py` | 1286 | `noqa` | `partly-justified` | `def _show_mib_dependencies(self) -> None:  # noqa: C901, PLR0912` |
| `ui/mib_browser.py` | 1501 | `type_ignore` | `review` | `return await get_cmd(  # type: ignore[no-any-return]` |
| `ui/mib_browser.py` | 1588 | `type_ignore` | `review` | `return await next_cmd(  # type: ignore[no-any-return]` |
| `ui/mib_browser.py` | 1792 | `type_ignore` | `review` | `return await set_cmd(  # type: ignore[no-any-return]` |
| `ui/snmp_gui.py` | 1 | `pylint_disable` | `review` | `# pylint: disable=broad-exception-caught,protected-access,unused-argument` |
| `ui/snmp_gui.py` | 2 | `pylint_disable` | `review` | `# pylint: disable=unused-variable,attribute-defined-outside-init,line-too-long` |
| `ui/snmp_gui.py` | 3 | `pylint_disable` | `partly-justified` | `# pylint: disable=too-many-lines,missing-module-docstring,missing-class-docstring` |
| `ui/snmp_gui.py` | 4 | `pylint_disable` | `partly-justified` | `# pylint: disable=too-many-instance-attributes,too-many-locals,too-many-statements` |
| `ui/snmp_gui.py` | 5 | `pylint_disable` | `partly-justified` | `# pylint: disable=too-many-branches,too-many-nested-blocks,ungrouped-imports` |
| `ui/snmp_gui.py` | 6 | `pylint_disable` | `review` | `# pylint: disable=consider-using-dict-items,consider-iterating-dictionary` |
| `ui/snmp_gui.py` | 7 | `pylint_disable` | `review` | `# pylint: disable=no-else-return,no-else-break,consider-using-max-builtin` |
| `ui/snmp_gui.py` | 8 | `pylint_disable` | `review` | `# pylint: disable=consider-using-in,import-outside-toplevel,use-maxsplit-arg` |
| `ui/snmp_gui.py` | 9 | `pylint_disable` | `partly-justified` | `# pylint: disable=consider-using-f-string,too-many-return-statements` |
| `ui/snmp_gui.py` | 10 | `pylint_disable` | `partly-justified` | `# pylint: disable=too-many-arguments,too-many-positional-arguments,superfluous-parens` |
| `ui/snmp_gui.py` | 11 | `ruff_noqa_file` | `review` | `# ruff: noqa: ANN401, ARG001, ARG002, ARG005, B007, C901, D100, D101, D107` |
| `ui/snmp_gui.py` | 12 | `ruff_noqa_file` | `review` | `# ruff: noqa: D401, DTZ005, ERA001, FBT001, FBT003, PERF203` |
| `ui/snmp_gui.py` | 13 | `ruff_noqa_file` | `review` | `# ruff: noqa: PLR0912, PLR0913, PLR0915, PLR2004, SLF001, TRY300` |
| `ui/snmp_gui.py` | 5250 | `type_ignore` | `review` | `preset_listbox.curselection(),  # type: ignore[no-untyped-call]` |
| `ui/snmp_gui_links_mixin.py` | 3 | `ruff_noqa_file` | `review` | `# ruff: noqa: ANN401, C901, PLR0915, PLR2004` |
| `ui/snmp_gui_trap_overrides_mixin.py` | 3 | `ruff_noqa_file` | `review` | `# ruff: noqa: ANN401, ARG005, C901, PLR0912, PLR0915, PLR2004` |
| `ui/snmp_gui_traps_mixin.py` | 3 | `ruff_noqa_file` | `review` | `# ruff: noqa: PERF203, PLR2004` |
| `ui/snmp_gui_traps_mixin.py` | 232 | `noqa` | `justified` | `host="0.0.0.0",  # noqa: S104` |
