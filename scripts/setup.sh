#!/usr/bin/env bash
# One-shot, idempotent installation of the whole POC:
#   start stack -> GitLab API token -> configure YouTrack -> configure GitLab + runner + integrations
#   -> load demo data -> run the end-to-end lifecycle demo -> acceptance checks.
# Usage: ./scripts/setup.sh            (everything)
#        ./scripts/setup.sh youtrack   (a single step: youtrack|gitlab|seed|lifecycle|verify)
source "$(dirname "$0")/lib.sh"
steps=("$@"); [ ${#steps[@]} -eq 0 ] && steps=(youtrack gitlab seed lifecycle verify)

"$ROOT/scripts/up.sh"
say "GitLab root API token (gitlab-rails runner)"
for i in $(seq 1 30); do
  "$ROOT/scripts/gitlab-token.sh" && break
  echo "  GitLab not ready for rails runner yet, retrying in 20s ($i/30)"; sleep 20
done
for step in "${steps[@]}"; do
  say "Setup step: $step"
  $DC run --rm setup "$step"
done
say "Done. Open:"
st() { python3 -c "import json,sys;print(json.load(open('$ROOT/.state/youtrack.json'))[sys.argv[1]])" "$1" 2>/dev/null || echo "?"; }
echo "  Request guide      ${YOUTRACK_BASE_URL}/articles/$(st article)"
echo "  Dashboard          ${YOUTRACK_BASE_URL}/dashboard?id=$(st dashboard)"
echo "  Kanban board       ${YOUTRACK_BASE_URL}/agiles/$(st board)/current"
echo "  GitLab project     ${GITLAB_EXTERNAL_URL}/${GITLAB_DEMO_GROUP}/${GITLAB_DEMO_PROJECT}"
echo "  Demo deployment    http://localhost:${DEMO_APP_PORT}"
echo "  Notification mails http://localhost:${MAILPIT_UI_PORT}"
echo "  Logins: admin / YOUTRACK_ADMIN_PASSWORD, demo users (maria.payments, devops.lead, lee.cicd, eng.manager, ...) / YOUTRACK_DEMO_USER_PASSWORD"
echo "          GitLab root / GITLAB_ROOT_PASSWORD"
