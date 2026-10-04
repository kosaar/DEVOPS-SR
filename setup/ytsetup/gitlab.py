"""Idempotent GitLab CE configuration (REST API v4 with the root personal access token).

- instance settings needed for on-prem integrations (local webhooks, no sign-up)
- group `platform` with the demo projects referenced by the demo requests
- `platform/ci-templates`: real code + .gitlab-ci.yml (test -> build -> deploy -> smoke -> report)
- GitLab -> YouTrack: native "YouTrack" project integration (DEVOPS-123 references become links)
- YouTrack -> GitLab: YouTrack's built-in GitLab VCS integration (commits/MRs shown on the request)
- CI/CD variables so pipelines can write back to YouTrack through its REST API
- instance runner (docker executor) written to the runner's config.toml
"""
import base64
import json
import os
import time
import urllib.parse

from .config import CFG, ROOT, STATE_DIR, log
from .http import ApiError, Client, wait_for
from . import youtrack

DEMO_PROJECTS = {
    "ci-templates": "Reusable GitLab CI templates + template catalog site (demo pipeline)",
    "deploy-templates": "Helm/deployment templates used by the squads",
    "k8s-addons": "Cluster add-ons (operators, node pools, policies)",
    "gitlab-config": "GitLab groups, permissions and push rules as code",
    "ops-automation": "Backups, runbooks and operational automation",
}
CI_BOT = ("gitlab.bot", "GitLab CI (bot)")


class GitLab:
    def __init__(self):
        self.base = CFG["GITLAB_INTERNAL_URL"]
        self.public = CFG["GITLAB_EXTERNAL_URL"].rstrip("/")
        self.api = Client(self.base + "/api/v4", {"PRIVATE-TOKEN": CFG["GITLAB_ROOT_TOKEN"]})
        self.group_path = CFG["GITLAB_DEMO_GROUP"]

    def wait_ready(self):
        log("Waiting for GitLab API (root token) ...")
        wait_for("GitLab API", lambda: self.api.get("user")["username"] == "root", timeout=1200, interval=10)

    def pid(self, path):
        return urllib.parse.quote(path, safe="")

    # ------------------------------------------------------------------ instance
    def instance_settings(self):
        log("Instance settings (allow local integrations, disable sign-up)")
        self.api.put("application/settings", {
            "allow_local_requests_from_web_hooks_and_services": True,
            "allow_local_requests_from_system_hooks": True,
            "signup_enabled": False,
            "auto_devops_enabled": False,
        })

    def group(self):
        g = self.api.get(f"groups/{self.pid(self.group_path)}", ok404=True)
        if not g:
            log(f"  + group {self.group_path}")
            g = self.api.post("groups", {"name": self.group_path.capitalize(), "path": self.group_path,
                                         "visibility": "internal",
                                         "description": "DevOps platform team: CI/CD factory, deployment and cluster services"})
        self.group_id = g["id"]
        return g

    def project(self, name, description):
        path = f"{self.group_path}/{name}"
        p = self.api.get(f"projects/{self.pid(path)}", ok404=True)
        if not p:
            log(f"  + project {path}")
            p = self.api.post("projects", {"name": name, "path": name, "namespace_id": self.group_id,
                                           "description": description, "visibility": "internal",
                                           "initialize_with_readme": name != "ci-templates",
                                           "default_branch": "main"})
        return p

    def push_ci_templates(self, project):
        """Initial commit of gitlab/ci-templates (via the commits API, no git client needed)."""
        try:
            self.api.get(f"projects/{project['id']}/repository/files/{self.pid('.gitlab-ci.yml')}", params={"ref": "main"})
            return False
        except ApiError:
            pass
        src = os.path.join(ROOT, "gitlab", "ci-templates")
        actions = []
        for dirpath, _, files in os.walk(src):
            for fn in sorted(files):
                full = os.path.join(dirpath, fn)
                actions.append({"action": "create", "file_path": os.path.relpath(full, src),
                                "encoding": "base64",
                                "content": base64.b64encode(open(full, "rb").read()).decode()})
        log(f"  initial commit of platform/ci-templates ({len(actions)} files)")
        self.api.post(f"projects/{project['id']}/repository/commits", {
            "branch": "main", "commit_message": "Initial import of the CI template catalog", "actions": actions})
        return True

    # ------------------------------------------------------------------ integrations
    def youtrack_integration(self, project):
        """GitLab's native YouTrack integration: DEVOPS-123 in GitLab text links to YouTrack."""
        yt = CFG["YOUTRACK_BASE_URL"].rstrip("/")
        self.api.put(f"projects/{project['id']}/integrations/youtrack", {
            "project_url": f"{yt}/issues/{CFG['YOUTRACK_PROJECT_KEY']}",
            "issues_url": f"{yt}/issue/:id",
        })

    def ci_variables(self, yt_token):
        log("Group CI/CD variables for the YouTrack write-back")
        demo_url = f"http://localhost:{CFG['DEMO_APP_PORT']}"
        wanted = {
            "YOUTRACK_URL": (CFG["YOUTRACK_INTERNAL_URL"], False),
            "YOUTRACK_PUBLIC_URL": (CFG["YOUTRACK_BASE_URL"], False),
            "YOUTRACK_PROJECT": (CFG["YOUTRACK_PROJECT_KEY"], False),
            "YOUTRACK_TOKEN": (yt_token, True),
            "DEMO_APP_PUBLIC_URL": (demo_url, False),
        }
        have = {v["key"] for v in self.api.get(f"groups/{self.group_id}/variables")}
        for k, (v, masked) in wanted.items():
            body = {"key": k, "value": v, "masked": masked, "protected": False}
            if k in have:
                self.api.put(f"groups/{self.group_id}/variables/{k}", body)
            else:
                self.api.post(f"groups/{self.group_id}/variables", body)

    # ------------------------------------------------------------------ runner
    def runner(self):
        conf_path = "/runner-config/config.toml"
        if not os.path.isdir("/runner-config"):
            log("  (runner config volume not mounted - skipping runner registration)")
            return
        state = os.path.join(STATE_DIR, "gitlab-runner.json")
        runners = self.api.get("runners/all", params={"type": "instance_type"})
        existing = next((r for r in runners if r.get("description") == "devops-poc-docker"), None)
        if existing and os.path.exists(state) and os.path.exists(conf_path) and "helper_image" in open(conf_path).read():
            return
        if existing:
            self.api.delete(f"runners/{existing['id']}")
        log("Registering instance runner 'devops-poc-docker' (docker executor)")
        r = self.api.post("user/runners", {"runner_type": "instance_type", "description": "devops-poc-docker",
                                           "run_untagged": True, "tag_list": "docker,poc"})
        toml = f'''concurrent = 2
check_interval = 3
shutdown_timeout = 0

[session_server]
  session_timeout = 1800

[[runners]]
  name = "devops-poc-docker"
  url = "{self.base}"
  clone_url = "{self.base}"
  token = "{r['token']}"
  executor = "docker"
  [runners.docker]
    image = "alpine:3.20"
    # pinned helper image from Docker Hub (mirror it into your internal registry for air-gapped sites)
    helper_image = "{CFG.get('GITLAB_RUNNER_HELPER_IMAGE', 'gitlab/gitlab-runner-helper:x86_64-v19.4.1')}"
    network_mode = "devops-poc"
    pull_policy = ["if-not-present"]
    privileged = false
    disable_cache = false
    # /deploy-target = web root of the demo-app container (stands in for a real environment)
    volumes = ["/cache", "devops-poc-demo-app-www:/deploy-target"]
    shm_size = 0
'''
        with open(conf_path, "w") as f:
            f.write(toml)
        with open(state, "w") as f:
            json.dump({"id": r["id"]}, f)

    # ------------------------------------------------------------------ run
    def run(self):
        self.wait_ready()
        self.instance_settings()
        self.group()
        projects = {n: self.project(n, d) for n, d in DEMO_PROJECTS.items()}
        self.push_ci_templates(projects["ci-templates"])
        log("GitLab -> YouTrack: project integration 'YouTrack' (issue references become links)")
        for p in projects.values():
            self.youtrack_integration(p)
        yt = youtrack.load()
        yt_token = ci_bot_token(yt)
        self.ci_variables(yt_token)
        self.runner()
        vcs_integration(yt, self, projects["ci-templates"])
        with open(os.path.join(STATE_DIR, "gitlab.json"), "w") as f:
            json.dump({"group_id": self.group_id, "projects": {n: p["id"] for n, p in projects.items()}}, f, indent=2)
        log("GitLab configuration complete")


def ci_bot_token(yt):
    """YouTrack account used by GitLab CI to write back to requests (member of the project team)."""
    tf = os.path.join(STATE_DIR, "youtrack-token-gitlab-bot")
    if os.path.exists(tf):
        return open(tf).read().strip()
    login, name = CI_BOT
    if not yt.hub_user(login):
        log(f"  + YouTrack user {login} (used by GitLab CI)")
        yt.api.post("hub/api/rest/users", {
            "login": login, "name": name,
            "details": [{"type": "LoginuserdetailsJSON", "login": login,
                         "password": {"type": "PlainpasswordJSON", "value": CFG["YOUTRACK_DEMO_USER_PASSWORD"]}}],
        }, params={"fields": "id"})
    user = None
    for _ in range(30):  # Hub -> YouTrack user sync is asynchronous
        user = next((u for u in yt.api.get("api/users", params={"fields": "id,login", "$top": 200})
                     if u["login"] == login), None)
        if user:
            break
        time.sleep(2)
    team = yt.api.get(f"api/admin/projects/{yt.project['id']}/team/ownUsers", params={"fields": "id"})
    if user["id"] not in {u["id"] for u in team}:
        yt.api.post(f"api/admin/projects/{yt.project['id']}/team/ownUsers", {"id": user["id"]})
    tok = yt.mint_token(login, CFG["YOUTRACK_DEMO_USER_PASSWORD"], "gitlab-ci")
    with open(tf, "w") as f:
        f.write(tok)
    return tok


def vcs_integration(yt, gl, project):
    """YouTrack's built-in GitLab integration (Project settings > VCS integrations).
    YouTrack reads commits and merge requests of the GitLab project and attaches those that
    mention a request ID (DEVOPS-123) to the request. Configured through the YouTrack REST API."""
    from .vcs import ensure_gitlab_vcs
    ensure_gitlab_vcs(yt, gl, project)


def run():
    GitLab().run()
