#!/usr/bin/env bash
#
# The demonstration, as one command. Runs the tool twice -- once on the sample
# pair and once on the corrected pair -- because "it found 16 things" means
# nothing without the control that shows it finds none when there is nothing to
# find. Exists so a live demo does not depend on typing four long paths.
#
#     ./demo.sh
#
set -euo pipefail
cd "$(dirname "$0")"

PY=./.venv/bin/python
[ -x "$PY" ] || PY=python3

hr() { printf '\n\033[1m%s\033[0m\n' "$1"; }

hr "1/2  The sample pair — a report that departs from its protocol"
$PY run.py \
    --protocol sample-a-test-protocol-nv-200.pdf \
    --report   sample-b-verification-report-nv-200.pdf \
    --out out/original

hr "2/2  The corrected pair — the same tool, the same rules, nothing to raise"
$PY run.py \
    --protocol corrected/corrected-a-test-protocol-nv-200.pdf \
    --report   corrected/corrected-b-verification-report-nv-200.pdf \
    --out out/corrected

hr "Open the review sheets"
echo "  out/original/review-sheet.html    16 findings, with citations"
echo "  out/corrected/review-sheet.html   0 findings, 18 checks recorded as clean"
echo
echo "  Neither one says pass or fail. That is the reviewer's call."

if command -v open >/dev/null 2>&1; then
    open out/original/review-sheet.html
fi
