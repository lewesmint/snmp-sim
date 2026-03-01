#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

LOCAL_WRAPPER_DIR="$REPO_ROOT/pysnmp_type_wrapper"
CANONICAL_WRAPPER_DIR_DEFAULT="$(cd "$REPO_ROOT/.." && pwd)/pysnmp-type-wrapper/pysnmp_type_wrapper"
CANONICAL_WRAPPER_DIR="${1:-$CANONICAL_WRAPPER_DIR_DEFAULT}"

if [[ -d "$LOCAL_WRAPPER_DIR" ]]; then
  echo "Wrapper sync check: FAILED" >&2
  echo "Reason: vendored wrapper directory still exists: $LOCAL_WRAPPER_DIR" >&2
  echo "Post-vendoring policy requires consuming only installed canonical package." >&2
  exit 1
fi

if [[ ! -d "$CANONICAL_WRAPPER_DIR" ]]; then
  echo "ERROR: canonical wrapper dir not found: $CANONICAL_WRAPPER_DIR" >&2
  echo "Usage: $0 /absolute/path/to/pysnmp-type-wrapper/pysnmp_type_wrapper" >&2
  exit 2
fi

SOURCE_PATH="$($SCRIPT_DIR/check_wrapper_package_source.sh --probe-installed --require-external | awk -F': ' '/^Wrapper import source:/{print $2}')"

if [[ -z "$SOURCE_PATH" ]]; then
  echo "Wrapper sync check: FAILED" >&2
  echo "Reason: unable to determine wrapper import source path." >&2
  exit 1
fi

case "$SOURCE_PATH" in
  "$CANONICAL_WRAPPER_DIR"/*|"$CANONICAL_WRAPPER_DIR" )
    echo "Wrapper sync check: OK"
    echo "Mode: post-vendoring external package"
    echo "Canonical: $CANONICAL_WRAPPER_DIR"
    echo "Resolved:  $SOURCE_PATH"
    exit 0
    ;;
esac

echo "Wrapper sync check: FAILED"
echo "Reason: wrapper resolved outside canonical path."
echo "Canonical: $CANONICAL_WRAPPER_DIR"
echo "Resolved:  $SOURCE_PATH"
echo "Hint: ensure the active environment installs ../pysnmp-type-wrapper in editable mode."
exit 1
