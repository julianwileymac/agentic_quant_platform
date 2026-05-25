#!/usr/bin/env bash
# check-doc-links.sh — CI guard that fails the build if any file
# anywhere in the repo still references a legacy ``aqp_docs/<path>.md``
# shape that did not survive the Phase-0 sweep.
#
# Run as a PR gate; also runnable locally:
#
#   bash aqp_docs/scripts/check-doc-links.sh
#
# Excludes:
#   - aqp_docs/docs/**            (the new canonical content tree)
#   - aqp_docs/scripts/**         (this script + the migration helpers
#                                  reference the legacy paths by design)
#   - aqp_docs/static/_redirects  (the redirects themselves map legacy
#                                  routes)
#   - aqp_index/**                (sole-writer; curator handles refresh)
#   - .cursor/plans/aqp-index-*   (the debt notes)
#   - aqp_docs/docs/archive/**    (frozen history)

set -euo pipefail

PATTERNS=(
  "aqp_docs/architecture/"
  "aqp_docs/operations/"
  "aqp_docs/runbooks/"
  "aqp_docs/mlops/"
  "aqp_docs/archive/"
)

EXCLUDE_GLOBS=(
  "--glob" "!aqp_docs/docs/**"
  "--glob" "!aqp_docs/scripts/**"
  "--glob" "!aqp_docs/static/_redirects"
  "--glob" "!aqp_index/**"
  "--glob" "!.cursor/plans/aqp-index-*"
  "--glob" "!**/*.tsbuildinfo"
  "--glob" "!**/node_modules/**"
  "--glob" "!**/.next/**"
  "--glob" "!**/.docusaurus/**"
  "--glob" "!**/build/**"
  "--glob" "!**/dist/**"
)

if ! command -v rg >/dev/null 2>&1; then
  echo "ERROR: ripgrep (rg) is required. Install via 'apt install ripgrep' or 'brew install ripgrep'." >&2
  exit 2
fi

# Pattern for any concept slug still using the legacy aqp_docs/<slug>.md shape.
CONCEPT_RE='aqp_docs/[a-zA-Z0-9_-]+\.md'

FAILED=0

echo "Checking for legacy concept-level links..."
if rg -n --color=never "${EXCLUDE_GLOBS[@]}" "${CONCEPT_RE}" .; then
  echo "" >&2
  echo "FAIL: legacy aqp_docs/<slug>.md references remain." >&2
  echo "      Run 'python aqp_docs/scripts/sweep-links.py' to fix." >&2
  FAILED=1
fi

echo "Checking for legacy subdirectory prefixes..."
for prefix in "${PATTERNS[@]}"; do
  # Sweep rules already rewrite these; if any survive, the build fails.
  if rg -n --color=never "${EXCLUDE_GLOBS[@]}" -F "${prefix}" .; then
    echo "" >&2
    echo "FAIL: legacy prefix '${prefix}' still appears." >&2
    FAILED=1
  fi
done

if [[ "${FAILED}" -ne 0 ]]; then
  exit 1
fi

echo ""
echo "OK — no legacy aqp_docs/ link shapes remain."
