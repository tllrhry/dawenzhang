#!/usr/bin/env sh
set -u
root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
logs="${TMPDIR:-/tmp}/dawenzhang-gates.$$"; mkdir -p "$logs"
trap 'rm -rf "$logs"' EXIT HUP INT TERM
failed=0; summary=""
run_gate() {
  name="$1"; shift; log="$logs/$name.log"; start="$(date +%s)"
  "$@" >"$log" 2>&1; code=$?; elapsed=$(( $(date +%s) - start ))
  if [ "$code" -eq 0 ]; then status=PASS; else status=FAIL; failed=1; echo "--- $name failure ---" >&2; tail -n 40 "$log" >&2; fi
  summary="${summary}${name} ${status} ${elapsed}s exit=${code}
"
}

# 后端：pytest 全量
run_gate BackendPytest sh -c "cd '$root' && PYTHONPATH=backend python -m pytest backend/tests -q"

# 前端：类型检查（npm run test = tsc --noEmit）
run_gate FrontendTypecheck sh -c "cd '$root/frontend' && npm run test --silent"

printf '%s' "$summary"
[ "$failed" -eq 0 ] && overall=PASS || overall=FAIL
printf 'OVERALL %s exit=%s\n' "$overall" "$failed"
exit "$failed"
