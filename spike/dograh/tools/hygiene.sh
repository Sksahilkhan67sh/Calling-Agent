#!/usr/bin/env bash
# Pre-commit hygiene gate (Phase 0 plan section 6.4). Run from anywhere inside the repo.
set -u -o pipefail
cd "$(git rev-parse --show-toplevel)" || exit 2
rc=0
echo "== 1. secret scan (working tree)"; spike/dograh/tools/secret_scan.sh || rc=1
echo "== 2. staged diff patterns"
if git diff --cached -U0 -- . ':!spike/dograh/tools/' ':!spike/dograh/tests/' ':!ai_calling agent/' \
   | grep -E '^\+' | grep -InE 'Bearer [A-Za-z0-9._-]{12,}|X-API-Key: *[A-Za-z0-9]{12,}|(token|signature|X-Amz-[A-Za-z-]+)=[A-Za-z0-9%._-]{12,}'; then
  echo "FAIL: suspicious pattern in staged diff"; rc=1; else echo "ok"; fi
echo "== 3. nothing under raw/ staged"
if git diff --cached --name-only | grep -q '/raw/'; then echo "FAIL: raw/ staged"; rc=1; else echo "ok"; fi
echo "== 4. staged files"; git diff --cached --stat | tail -25
echo "== 5. pytest"; (cd spike/dograh && python3 -m pytest -q 2>&1 | tail -3) || rc=1
[ $rc -eq 0 ] && echo "HYGIENE OK" || echo "HYGIENE FAILED"
exit $rc
