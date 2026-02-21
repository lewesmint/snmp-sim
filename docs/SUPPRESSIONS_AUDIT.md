# Suppressions Audit

Date: 2026-02-21
Scope: Python codebase scan excluding configured generated/archive folders

## Excluded paths for this audit

- .venv/**
- .pyenv/**
- compiled-mibs/**
- compiled-mibs-test/**
- minimal-for-reference/**
- manual-tests/**
- retired/**
- logs/**
- ui/logs/**
- .git/**
- __pycache__/**

## Suppression totals

- noqa: 1
- type: ignore: 13
- pyright: ignore: 1
- pylint: disable: 6
- pragma: no cover: 7
- warnings.filterwarnings/simplefilter("ignore", ...): 7

## Inline suppression locations

### noqa

- app/snmp_agent.py:22  (`# noqa: F401`)

### type: ignore

- app/app_logger.py:59  (`# type: ignore[type-arg]`)
- tests/misc/test_coverage_gaps.py:55  (`# type: ignore[method-assign]`)
- tests/misc/test_coverage_gaps.py:84  (`# type: ignore[method-assign]`)
- tests/misc/test_coverage_gaps.py:109  (`# type: ignore[method-assign]`)
- tests/misc/test_coverage_gaps.py:133  (`# type: ignore[method-assign]`)
- tests/misc/test_generator_more.py:599  (`# type: ignore[comparison-overlap]`)
- tests/unit/agent/test_snmp_agent_additional.py:211  (`# type: ignore`)
- tests/unit/agent/test_snmp_agent_additional.py:298  (`# type: ignore[comparison-overlap]`)
- tests/unit/ui/test_mib_browser_unit.py:262  (`# type: ignore[method-assign]`)
- ui/mib_browser.py:1410  (`# type: ignore[no-any-return]`)
- ui/mib_browser.py:1495  (`# type: ignore[no-any-return]`)
- ui/mib_browser.py:1688  (`# type: ignore[no-any-return]`)
- ui/snmp_gui.py:6778  (`# type: ignore[no-untyped-call]`)

### pyright: ignore

- tests/unit/trap/test_trap_sender.py:56  (`# pyright: ignore[reportArgumentType]`)

### pylint: disable

- tests/unit/mib/test_mib_registrar_more.py:1
- tests/unit/scripts/test_run_agent_with_rest.py:1
- tests/unit/scripts/test_run_agent_with_rest.py:2
- tests/unit/scripts/test_run_agent_with_rest.py:3
- ui/mib_browser.py:5
- ui/snmp_gui.py:1

### pragma: no cover

- app/cli_build_model.py:112
- app/cli_compile_mib.py:58
- app/cli_run_agent.py:79
- app/cli_trap_sender.py:108
- app/snmp_agent.py:1878
- app/type_recorder.py:956
- run_agent_with_rest.py:24

### warnings filter ignores

- tests/conftest.py:15
- tests/conftest.py:16
- tests/conftest.py:18
- tests/unit/type_system/test_type_registry.py:27
- tests/unit/type_system/test_type_registry.py:64
- tests/unit/type_system/test_type_registry.py:110
- tests/unit/type_system/test_type_registry.py:143

## Config-level suppression settings

### pyproject.toml

- [tool.mypy]
  - ignore_missing_imports = true
  - disable_error_code = ["import-untyped"]
  - exclude includes: retired, compiled-mibs-test, compiled-mibs, minimal-for-reference, manual-tests, logs, ui, tests, ui/logs
- [tool.ruff.lint]
  - ignore = ["E501", "E741"]
- [tool.pytest.ini_options]
  - addopts includes multiple --ignore=... paths
  - filterwarnings includes: ignore::DeprecationWarning

### .flake8

- extend-ignore: E203, W503
- per-file-ignores:
  - ui/mib_browser.py: E128,E501,N806,W291,W293
  - ui/snmp_gui.py: E501
- exclude includes generated/archive folders

## Notes

- This audit captures suppression markers, not whether each suppression is currently necessary.
- The biggest concentration of broad suppressions is in UI modules and some unit tests.
- Recommended first pass for cleanup: narrow module-level pylint disables, replace broad warning ignores with targeted matchers, and remove stale type ignores after local typing fixes.
