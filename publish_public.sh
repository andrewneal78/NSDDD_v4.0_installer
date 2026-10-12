#!/bin/bash
# Publish the current main to the public repo as one new commit on the 'public' branch.
# usage: ./publish_public.sh "message"   (bump VERSION and push main to origin first)
set -e
cd "$(dirname "$0")"
git diff --quiet && git diff --cached --quiet || { echo "Commit your changes on main first."; exit 1; }
[ "$(git branch --show-current)" = main ] || { echo "Run this from the main branch."; exit 1; }
git checkout -q public
git checkout main -- .
# files deleted or renamed on main must disappear from the public branch too
git ls-files -z | while IFS= read -r -d '' f; do git cat-file -e "main:$f" 2>/dev/null || git rm -q -f -- "$f"; done
git rm -q -r --cached --ignore-unmatch FIXES_REPORT_*.md INSTALLATION_AUDIT_*.md WORKSPACE_NOTES.md >/dev/null
git commit -q -m "${1:-NSDDD 4.0 pre-release $(cat VERSION)}" || echo "Nothing new to publish."
git push public public:main
git checkout -q main
echo "Published version $(cat VERSION)."
