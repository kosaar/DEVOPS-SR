#!/usr/bin/env bash
# Create (idempotently) the GitLab root personal access token used by the setup job.
# Uses `gitlab-rails runner`, GitLab's documented way to create a token programmatically.
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck disable=SC1091
source .env
docker compose exec -T gitlab gitlab-rails runner "
  u = User.find_by_username('root') or abort('root user missing - check the gitlab container logs')
  t = u.personal_access_tokens.active.find_by(name: 'devops-poc-setup')
  unless t
    t = u.personal_access_tokens.create!(name: 'devops-poc-setup',
          scopes: [:api, :read_repository, :write_repository, :create_runner],
          expires_at: 365.days.from_now)
    t.set_token('${GITLAB_ROOT_TOKEN}')
    t.save!
    puts 'created GitLab root token devops-poc-setup'
  else
    puts 'GitLab root token devops-poc-setup already exists'
  end
"
