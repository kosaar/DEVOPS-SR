"""Configuration: .env values (passed by docker compose `env_file`) + defaults."""
import os
import sys
import time

ROOT = os.environ.get("POC_ROOT", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
STATE_DIR = os.path.join(ROOT, ".state")

DEFAULTS = {
    "YOUTRACK_INTERNAL_URL": "http://localhost:8080",
    "YOUTRACK_BASE_URL": "http://localhost:8080",
    "YOUTRACK_ADMIN_PASSWORD": "ChangeMe-YT-Admin1!",
    "YOUTRACK_DEMO_USER_PASSWORD": "Demo-Pass-2026!",
    "YOUTRACK_PROJECT_KEY": "DEVOPS",
    "AGING_THRESHOLD_DAYS": "14",
    "DEVOPS_LEAD_LOGIN": "devops.lead",
    "GITLAB_INTERNAL_URL": "http://localhost:8929",
    "GITLAB_EXTERNAL_URL": "http://localhost:8929",
    "GITLAB_ROOT_TOKEN": "",
    "GITLAB_DEMO_GROUP": "platform",
    "GITLAB_DEMO_PROJECT": "ci-templates",
    "DEMO_APP_PORT": "8088",
}


def _load_dotenv():
    vals = {}
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip()
    return vals


CFG = dict(DEFAULTS)
CFG.update(_load_dotenv())
CFG.update({k: v for k, v in os.environ.items() if k in DEFAULTS or k.startswith(("YOUTRACK_", "GITLAB_"))})
os.makedirs(STATE_DIR, exist_ok=True)


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, file=sys.stderr, flush=True)
