#!/usr/bin/env bash
# Start the stack and wait until YouTrack and GitLab are healthy.
source "$(dirname "$0")/lib.sh"
say "Starting containers (first start pulls ~11 GB of images and takes 5-10 minutes)"
$DC up -d
say "Waiting for YouTrack ..."
wait_healthy youtrack 900
say "Waiting for GitLab (first boot runs database migrations: ~5 minutes) ..."
wait_healthy gitlab 1500
say "Stack is up:"
echo "  YouTrack  ${YOUTRACK_BASE_URL}"
echo "  GitLab    ${GITLAB_EXTERNAL_URL}"
echo "  Mailpit   http://localhost:${MAILPIT_UI_PORT}"
echo "  Demo app  http://localhost:${DEMO_APP_PORT}"
