#!/usr/bin/env bash
# Fail if application Python modules exceed the 200-line budget.
#
# Scans vanessa/, services/, and scripts/. Tests are out of scope.
# Allowlisted files may exceed 200 until they are split, but they
# must not grow past the recorded newline count.
#
#   bash scripts/check_python_file_length.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MAX=200
ALLOWLIST="scripts/python_file_length_allowlist.txt"
SCAN_DIRS=(vanessa services scripts)

if [[ ! -f "$ALLOWLIST" ]]; then
  echo "Error: allowlist not found: ${ALLOWLIST}"
  exit 1
fi

declare -A BASELINE=()
declare -A SEEN=()

while IFS= read -r line || [[ -n "$line" ]]; do
  line="${line%$'\r'}"
  [[ -z "$line" || "$line" == \#* ]] && continue
  path="${line% *}"
  count="${line##* }"
  if [[ -z "$path" ]] || ! [[ "$count" =~ ^[0-9]+$ ]]; then
    echo "Error: invalid allowlist line: ${line}"
    exit 1
  fi
  BASELINE["$path"]="$count"
done < "$ALLOWLIST"

found=0

report() {
  echo "$1"
  found=1
}

scan_dirs=()
for dir in "${SCAN_DIRS[@]}"; do
  [[ -d "$dir" ]] && scan_dirs+=("$dir")
done

if (( ${#scan_dirs[@]} == 0 )); then
  echo "Error: none of the scan directories exist: ${SCAN_DIRS[*]}"
  exit 1
fi

while IFS= read -r -d '' file; do
  rel="${file#./}"
  rel="${rel//\\//}"
  SEEN["$rel"]=1
  lines="$(wc -l < "$file")"
  lines="${lines//[[:space:]]/}"

  if [[ -n "${BASELINE[$rel]+x}" ]]; then
    baseline="${BASELINE[$rel]}"
    if (( lines > baseline )); then
      report "Error: ${rel} contains ${lines} lines (allowlist baseline: ${baseline}; max allowed: ${MAX})"
    elif (( lines <= MAX )); then
      report "Error: ${rel} is at ${lines} lines (at or under ${MAX}); remove it from ${ALLOWLIST}"
    fi
    continue
  fi

  if (( lines > MAX )); then
    report "Error: ${rel} contains ${lines} lines (max allowed: ${MAX})"
  fi
done < <(
  find "${scan_dirs[@]}" \
    \( \
      -name .venv -o -name venv -o -name __pycache__ -o -name .ruff_cache \
      -o -name site-packages -o -name dist -o -name build -o -name .tox \
      -o -name .eggs -o -name .mypy_cache -o -name .pytest_cache \
      -o -name .git -o -name '*.egg-info' \
    \) -prune -o \
    -type f -name '*.py' -print0
)

for path in "${!BASELINE[@]}"; do
  if [[ -z "${SEEN[$path]+x}" ]]; then
    report "Error: allowlisted file is missing: ${path}; remove it from ${ALLOWLIST}"
  fi
done

if (( found )); then
  echo
  echo "Python file-length check failed (max ${MAX} lines in vanessa/, services/, scripts/)."
  echo "Split the module instead of growing it or extending the allowlist."
  exit 1
fi
