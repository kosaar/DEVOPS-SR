#!/usr/bin/env bash
# Restore a backup created by backup.sh into the running stack (same versions).
# Usage: ./scripts/restore.sh backups/<timestamp>
source "$(dirname "$0")/lib.sh"
src=$(cd "${1:?usage: restore.sh backups/<timestamp>}" && pwd)
ts=$(basename "$(ls "$src"/*_gitlab_backup.tar)" _gitlab_backup.tar)

say "Restoring YouTrack database (stop, replace the database directories, start)"
$DC stop youtrack-loopback youtrack
docker run --rm -v devops-poc_youtrack-data:/data -v "$src":/b:ro alpine:3.20 \
  sh -c 'cd /data && rm -rf youtrack hub conf && tar -xzf /b/youtrack-db.tar.gz -C /data && chown -R 13001:13001 /data'
$DC start youtrack youtrack-loopback
wait_healthy youtrack 900

say "Restoring GitLab (gitlab-backup restore)"
docker cp "$src/${ts}_gitlab_backup.tar" devops-poc-gitlab:/var/opt/gitlab/backups/
docker cp "$src/gitlab-secrets.json" devops-poc-gitlab:/etc/gitlab/gitlab-secrets.json
$DC exec -T gitlab chown git:git "/var/opt/gitlab/backups/${ts}_gitlab_backup.tar"
$DC exec -T gitlab gitlab-ctl stop puma
$DC exec -T gitlab gitlab-ctl stop sidekiq
$DC exec -T gitlab gitlab-backup restore BACKUP="$ts" force=yes
$DC exec -T gitlab gitlab-ctl reconfigure >/dev/null
$DC restart gitlab
wait_healthy gitlab 1500

say "Restoring POC state"
tar -xzf "$src/state.tar.gz" -C "$ROOT"
[ -f "$src/runner-config.toml" ] && docker cp "$src/runner-config.toml" devops-poc-gitlab-runner:/etc/gitlab-runner/config.toml
say "Restore complete"
