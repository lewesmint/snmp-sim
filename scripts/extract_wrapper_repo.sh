#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 /absolute/path/to/new-wrapper-repo" >&2
  exit 1
fi

TARGET_REPO="$1"
SOURCE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ ! "$TARGET_REPO" = /* ]]; then
  echo "Error: target path must be absolute: $TARGET_REPO" >&2
  exit 1
fi

mkdir -p "$TARGET_REPO/pysnmp_type_wrapper"

copy_file() {
  local rel_path="$1"
  local source_path="$SOURCE_ROOT/$rel_path"
  local target_path="$TARGET_REPO/$rel_path"

  if [[ ! -f "$source_path" ]]; then
    echo "Error: missing source file: $source_path" >&2
    exit 1
  fi

  mkdir -p "$(dirname "$target_path")"
  cp "$source_path" "$target_path"
}

copy_file "pysnmp_type_wrapper/__init__.py"
copy_file "pysnmp_type_wrapper/__init__.pyi"
copy_file "pysnmp_type_wrapper/interfaces.py"
copy_file "pysnmp_type_wrapper/interfaces.pyi"
copy_file "pysnmp_type_wrapper/raw_boundary_types.py"
copy_file "pysnmp_type_wrapper/raw_boundary_types.pyi"
copy_file "pysnmp_type_wrapper/pysnmp_type_resolver.py"
copy_file "pysnmp_type_wrapper/pysnmp_type_resolver.pyi"
copy_file "pysnmp_type_wrapper/pysnmp_rfc1902_adapter.py"
copy_file "pysnmp_type_wrapper/pysnmp_rfc1902_adapter.pyi"
copy_file "pysnmp_type_wrapper/pysnmp_mib_symbols_adapter.py"
copy_file "pysnmp_type_wrapper/pysnmp_mib_symbols_adapter.pyi"
copy_file "pysnmp_type_wrapper/mib_registrar_runtime_adapter.py"
copy_file "pysnmp_type_wrapper/mib_registrar_runtime_adapter.pyi"
copy_file "pysnmp_type_wrapper/constraint_parser.py"
copy_file "pysnmp_type_wrapper/py.typed"
copy_file "pysnmp_type_wrapper/pyproject.wrapper.toml"

if [[ -d "$SOURCE_ROOT/tests/wrapper" ]]; then
  mkdir -p "$TARGET_REPO/tests/wrapper"
  find "$SOURCE_ROOT/tests/wrapper" -maxdepth 1 -type f -name "*.py" -exec cp {} "$TARGET_REPO/tests/wrapper/" \;
fi

cp "$TARGET_REPO/pysnmp_type_wrapper/pyproject.wrapper.toml" "$TARGET_REPO/pyproject.toml"
rm -f "$TARGET_REPO/pysnmp_type_wrapper/pyproject.wrapper.toml"

if [[ ! -f "$TARGET_REPO/README.md" ]]; then
  cat > "$TARGET_REPO/README.md" <<'EOF'
# pysnmp-type-wrapper

Typed boundary adapters for integrating application code with dynamic PySNMP surfaces.

## Local development

- Python: 3.13+
- Install editable package:

```bash
pip install -e .
```

- Type-check/package consumers against `pysnmp_type_wrapper` typed exports.
EOF
fi

echo "Wrapper package extracted to: $TARGET_REPO"
echo "Next steps:"
echo "  1) cd $TARGET_REPO"
echo "  2) git init"
echo "  3) pip install -e ."
