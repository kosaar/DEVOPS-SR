#!/bin/sh
# Write CI results back to the YouTrack request(s) referenced by this pipeline.
# Uses the documented YouTrack REST API (POST /api/issues/{id}, /api/issues/{id}/comments).
# Requires: YOUTRACK_URL, YOUTRACK_TOKEN (CI/CD variables). busybox wget only, no extra packages.
set -eu
: "${YOUTRACK_URL:?}" "${YOUTRACK_TOKEN:?}"
PROJECT_KEY="${YOUTRACK_PROJECT:-DEVOPS}"
STAGE="${1:-pipeline}"   # pipeline | deployed

ids=$(printf '%s\n%s\n%s\n%s\n' "${CI_COMMIT_REF_NAME:-}" "${CI_MERGE_REQUEST_TITLE:-}" \
        "${CI_MERGE_REQUEST_SOURCE_BRANCH_NAME:-}" "${CI_COMMIT_MESSAGE:-}" \
      | grep -oE "$PROJECT_KEY-[0-9]+" | sort -u || true)
if [ -z "$ids" ]; then echo "No $PROJECT_KEY-<n> reference found; nothing to sync."; exit 0; fi

json_escape() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }

yt_post() { # path body
  wget -q -O - --header "Authorization: Bearer $YOUTRACK_TOKEN" --header "Content-Type: application/json" \
       --header "Accept: application/json" --post-data "$2" "$YOUTRACK_URL/api/$1?fields=id" >/dev/null
}

if [ -n "${CI_MERGE_REQUEST_IID:-}" ]; then
  ref="$CI_PROJECT_PATH!$CI_MERGE_REQUEST_IID"
  where="merge request [$ref]($CI_PROJECT_URL/-/merge_requests/$CI_MERGE_REQUEST_IID)"
else
  ref=""
  where="branch \`$CI_COMMIT_REF_NAME\`"
fi

for id in $ids; do
  fields="{\"\$type\":\"SimpleIssueCustomField\",\"name\":\"GitLab Project\",\"value\":\"$CI_PROJECT_PATH\"},{\"\$type\":\"SimpleIssueCustomField\",\"name\":\"Pipeline reference\",\"value\":\"$CI_PIPELINE_URL\"}"
  if [ -n "$ref" ]; then
    fields="$fields,{\"\$type\":\"SimpleIssueCustomField\",\"name\":\"GitLab Issue/MR reference\",\"value\":\"$ref\"}"
  fi
  yt_post "issues/$id" "{\"customFields\":[$fields]}"
  if [ "$STAGE" = "deployed" ]; then
    text="Deployed to **${CI_ENVIRONMENT_NAME:-demo}** (${CI_ENVIRONMENT_URL:-}) by pipeline [#$CI_PIPELINE_ID]($CI_PIPELINE_URL), commit \`$CI_COMMIT_SHORT_SHA\`. Smoke test passed."
  else
    text="GitLab pipeline [#$CI_PIPELINE_ID]($CI_PIPELINE_URL) passed (test + build) for $where, commit \`$CI_COMMIT_SHORT_SHA\`."
  fi
  yt_post "issues/$id/comments" "{\"text\":\"$(json_escape "$text")\"}"
  echo "Updated $id: $text"
done
