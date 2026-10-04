#!/bin/sh
# Static checks for the template catalog. Fails the pipeline on any error.
set -eu
fail=0
for f in templates/*.yml; do
  name=$(basename "$f" .yml)
  # every template must define a hidden job named after the file
  grep -q "^\.$name:" "$f" || { echo "FAIL $f: missing hidden job .$name"; fail=1; }
  # every template must start with a description comment
  head -1 "$f" | grep -q '^# ' || { echo "FAIL $f: first line must be a '# description'"; fail=1; }
  echo "ok   $f"
done
grep -q '__CATALOG__' site/index.html || { echo "FAIL site/index.html: catalog placeholder missing"; fail=1; }
[ "$fail" = 0 ] && echo "All template checks passed"
exit $fail
