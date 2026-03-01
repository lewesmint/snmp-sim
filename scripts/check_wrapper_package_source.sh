#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

STRICT_EXTERNAL=0
PROBE_INSTALLED=0

for arg in "$@"; do
  case "$arg" in
    --require-external)
      STRICT_EXTERNAL=1
      ;;
    --probe-installed)
      PROBE_INSTALLED=1
      ;;
    *)
      echo "ERROR: unknown argument: $arg" >&2
      echo "Usage: $0 [--probe-installed] [--require-external]" >&2
      exit 2
      ;;
  esac
done

if [[ -n "${PYTHON:-}" ]]; then
  PYTHON_BIN="$PYTHON"
elif [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
  PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
else
  PYTHON_BIN="python"
fi

PYTHON_ARGS=()
if [[ "$PROBE_INSTALLED" -eq 1 ]]; then
  PYTHON_ARGS+=("-P")
fi

SOURCE_PATH="$($PYTHON_BIN "${PYTHON_ARGS[@]}" -c 'import pathlib, pysnmp_type_wrapper; print(pathlib.Path(pysnmp_type_wrapper.__file__).resolve())')"
SOURCE_DIR="$(dirname "$SOURCE_PATH")"
VENDORED_DIR="$REPO_ROOT/pysnmp_type_wrapper"

echo "Wrapper import source: $SOURCE_PATH"
echo "Vendored dir:          $VENDORED_DIR"
if [[ "$PROBE_INSTALLED" -eq 1 ]]; then
  echo "Probe mode:            installed-package probe (-P)"
fi

if [[ "$SOURCE_DIR" == "$VENDORED_DIR" ]]; then
  echo "Resolution mode: vendored (local repo copy)"
  if [[ "$STRICT_EXTERNAL" -eq 1 ]]; then
    echo "ERROR: --require-external set but import resolves to vendored wrapper." >&2
    echo "Hint: install canonical package and remove/rename vendored wrapper path before retry." >&2
    exit 1
  fi
  exit 0
fi

echo "Resolution mode: external (non-vendored)"
exit 0
