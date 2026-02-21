# Full-Repo Flake8 Results

Date: 2026-02-21

## Scope
- Entire repository (`.`)

## Command Run
```bash
flake8 . --count --statistics --output-file docs/flake8_full_repo_raw.txt
```

```bash
flake8 . --count --statistics --output-file docs/flake8_full_repo_raw_after_ws.txt
```

```bash
flake8 . --count --statistics --output-file docs/flake8_full_repo_raw_after_e501_top3.txt
```

## Outcome
- Baseline issues: **2508**
- After whitespace cleanup issues: **1267**
- After top-3 E501 pass issues: **1234**
- Net reduction vs baseline: **1274**
- Incremental reduction from E501 pass: **33**
- Exit status: **1** (expected while any issues remain)
- Raw detailed outputs:
   - `docs/flake8_full_repo_raw.txt`
   - `docs/flake8_full_repo_raw_after_ws.txt`
   - `docs/flake8_full_repo_raw_after_e501_top3.txt`

## Whitespace Pass Performed
- Scope: `tests/` and `manual-tests/` Python files
- Files normalized: **70**
- Normalizations applied:
   - trailing whitespace removal
   - blank-line-with-whitespace cleanup
   - normalized file ending newline (single trailing newline)

## Top Error Codes
- `W293`: 1543 → 336 → 336
- `W291`: 23 → 5 → 5
- `W391`: 24 → 14 → 14
- `W292`: 10 → 4 → 4
- `E501`: 477 → 477 → 444 (**-33** in top-3 pass)
- `N806`: 165 → 165 → 165
- `N802`: 81 → 81 → 81

## E501 Targeted Pass (Top 3 Files)
- Files:
   - `app/api.py`
   - `app/snmp_agent.py`
   - `tests/misc/test_generator_more.py`
- Tooling:
   - installed `autopep8`
   - ran `autopep8 --in-place --max-line-length 100 --select E501` on the 3 files
- E501 in the 3 files: **91 → 58** (**-33**)

## Top Files by Issue Count
- `app/api.py`: 123
- `app/snmp_agent.py`: 120
- `tests/misc/test_generator_more.py`: 66
- `tests/unit/mib/test_mib_registrar_more.py`: 48
- `tests/unit/agent/test_snmp_agent_additional.py`: 44
- `tests/unit/table/test_table_registrar.py`: 43
- `tests/unit/type_system/test_type_recorder_unit.py`: 42
- `app/cli_bake_state.py`: 37
- `manual-tests/snmp/test_snmp_operations.py`: 35
- `app/mib_registrar.py`: 34

## Notes
- The whitespace cleanup removed roughly half of all flake8 findings in one pass.
- The top-3 E501 pass reduced another 33 issues without broad refactors.
- Remaining volume is now concentrated in line-length and naming-rule findings.
- Existing `.flake8` per-file ignores still only target `ui/mib_browser.py` and `ui/snmp_gui.py`.

## Suggested Cleanup Order
1. Continue line-length pass (`E501`) in current top files (`app/api.py`, `app/snmp_agent.py`, `tests/misc/test_generator_more.py`).
2. Naming-rule review (`N806`, `N802`) where SNMP/pysnmp naming is intentional; apply targeted ignores only where justified.
3. Fix remaining newline/whitespace residue (`W391`, `W292`, `W291`) in the remaining hotspots.
4. Re-run:
   ```bash
   flake8 . --count --statistics
   ```
