#!/usr/bin/env bash
# Hygiene scan. Usage: secret_scan.sh [paths...]  (default: spike/dograh and docs/phase-0)
# Exit 1 if a token pattern, auth header value, unmasked phone number, owned test number or raw capture is found.
set -u
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT" || exit 2
PATHS=("$@"); [ ${#PATHS[@]} -eq 0 ] && PATHS=(spike/dograh docs/phase-0)
SELF="spike/dograh/tools/secret_scan.sh"
fail=0
report() { echo "SECRET-SCAN FAIL: $1"; fail=1; }

# Raw captures must never exist inside tracked/scanned paths.
if find "${PATHS[@]}" -path '*/raw/*' -type f 2>/dev/null | grep -q .; then report "file under a raw/ folder"; fi

FILES=$(grep -rIl --exclude-dir=.git --exclude-dir=__pycache__ --exclude-dir=.pytest_cache -e '' "${PATHS[@]}" 2>/dev/null | grep -v "^$SELF$")
[ -z "$FILES" ] && { echo "SECRET-SCAN OK (no files)"; exit 0; }

scan() { # label regex [exclude-grep-regex-for-path]
  local hits
  hits=$(echo "$FILES" | { [ -n "${3:-}" ] && grep -Ev "$3" || cat; } | xargs -r grep -InE "$2" 2>/dev/null | sed -E 's/(.{0,60}).*/\1.../')
  [ -n "$hits" ] && { report "$1"; echo "$hits" | head -5; }
}
scan "token pattern"        'ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}'
scan "auth header value"    '(Authorization|X-API-Key)[:=] *"?(Bearer |Basic )?[A-Za-z0-9._~+/=-]{16,}'
scan "long hex/base64 blob" '[A-Fa-f0-9]{40,}|[A-Za-z0-9+/]{64,}={0,2}'
scan "signed URL"           '(token|signature|X-Amz-Signature)=[A-Za-z0-9%._-]{16,}'
# Unmasked E.164 numbers (masked form contains '*'); test code may use clearly fake numbers.
scan "unmasked phone number" '\+[0-9]{10,15}' '^spike/dograh/tests/'
IFS=',' read -ra OWNED <<< "${SPIKE_TEST_NUMBERS:-}"
for n in "${OWNED[@]:-}"; do [ -n "$n" ] && scan "owned test number" "$(printf '%s' "$n" | sed 's/+/\\+/')"; done

[ $fail -eq 0 ] && echo "SECRET-SCAN OK"
exit $fail
