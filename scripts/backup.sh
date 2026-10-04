#!/usr/bin/env bash
# Online backup with each product's documented mechanism:
#  - YouTrack: database backup via REST API (Administration > Database Backup)
#  - GitLab:   gitlab-backup create + gitlab-secrets.json + gitlab.rb
#  - POC state: .env, .state/ (API tokens), runner config.toml
# Output: backups/<timestamp>/
source "$(dirname "$0")/lib.sh"
ts=$(date +%Y%m%d-%H%M%S); out="$ROOT/backups/$ts"; mkdir -p "$out"

say "YouTrack database backup"
before=$($DC exec -T youtrack sh -c 'ls -1 /opt/youtrack/backups/*.tar.gz 2>/dev/null | wc -l')
curl -fsS -X POST -H "Authorization: Bearer $(yt_token)" -H 'Content-Type: application/json' \
  -d '{"backupStatus":{"backupInProgress":true}}' "http://localhost:${YOUTRACK_PORT}/api/admin/databaseBackup/settings" >/dev/null
for i in $(seq 1 120); do
  inprog=$(curl -fsS -H "Authorization: Bearer $(yt_token)" \
    "http://localhost:${YOUTRACK_PORT}/api/admin/databaseBackup/settings?fields=backupStatus(backupInProgress)" | grep -c '"backupInProgress":true' || true)
  now=$($DC exec -T youtrack sh -c 'ls -1 /opt/youtrack/backups/*.tar.gz 2>/dev/null | wc -l')
  [ "$inprog" = 0 ] && [ "$now" -gt "$before" ] && break; sleep 2
done
latest=$($DC exec -T youtrack sh -c 'ls -1t /opt/youtrack/backups/*.tar.gz | head -1' | tr -d '\r')
docker cp "devops-poc-youtrack:$latest" "$out/youtrack-db.tar.gz"

say "GitLab backup (gitlab-backup create)"
$DC exec -T gitlab gitlab-backup create STRATEGY=copy BACKUP="$ts" >/dev/null
docker cp "devops-poc-gitlab:/var/opt/gitlab/backups/${ts}_gitlab_backup.tar" "$out/"
docker cp devops-poc-gitlab:/etc/gitlab/gitlab-secrets.json "$out/"
docker cp devops-poc-gitlab:/etc/gitlab/gitlab.rb "$out/"

say "POC state"
cp .env "$out/env"
tar -czf "$out/state.tar.gz" .state
docker cp devops-poc-gitlab-runner:/etc/gitlab-runner/config.toml "$out/runner-config.toml" 2>/dev/null || true
ls -lh "$out"
say "Backup written to $out"
