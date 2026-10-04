#!/bin/sh
# Render site/index.html into public/ with the template catalog and build metadata.
set -eu
mkdir -p public
catalog=""
for f in templates/*.yml; do
  name=$(basename "$f" .yml)
  desc=$(head -1 "$f" | sed 's/^# //')
  catalog="$catalog<li><code>$name</code> - $desc</li>"
done
requests=$(printf '%s %s %s' "${CI_COMMIT_REF_NAME:-}" "${CI_COMMIT_TITLE:-}" "${CI_MERGE_REQUEST_TITLE:-}" \
  | grep -oE "${YOUTRACK_PROJECT:-DEVOPS}-[0-9]+" | sort -u | tr '\n' ' ' || true)
sed -e "s|__CATALOG__|$catalog|" \
    -e "s|__PIPELINE_URL__|${CI_PIPELINE_URL:-#}|" -e "s|__PIPELINE_ID__|${CI_PIPELINE_ID:-local}|" \
    -e "s|__COMMIT__|${CI_COMMIT_SHORT_SHA:-local}|" -e "s|__REF__|${CI_COMMIT_REF_NAME:-local}|" \
    -e "s|__DEPLOYED_AT__|$(date -u +%Y-%m-%dT%H:%M:%SZ)|" -e "s|__REQUESTS__|${requests:-none}|" \
    -e "s|__YOUTRACK_URL__|${YOUTRACK_PUBLIC_URL:-http://localhost:8080}|" \
    site/index.html > public/index.html
echo "${CI_COMMIT_SHORT_SHA:-local}" > public/version.txt
echo "Rendered public/index.html ($(echo "$catalog" | grep -o '<li>' | wc -l) templates)"
