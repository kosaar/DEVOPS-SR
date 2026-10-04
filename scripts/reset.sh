#!/usr/bin/env bash
# DESTRUCTIVE: stop the stack and delete all its data volumes and local state.
source "$(dirname "$0")/lib.sh"
read -r -p "This deletes ALL YouTrack/GitLab data of the POC. Type 'yes' to continue: " ok
[ "$ok" = yes ] || exit 1
$DC --profile tools down -v --remove-orphans
docker volume rm devops-poc-demo-app-www 2>/dev/null || true
rm -rf "$ROOT/.state"
say "Reset complete. Run ./scripts/setup.sh to reinstall."
