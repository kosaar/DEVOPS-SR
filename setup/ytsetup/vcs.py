"""YouTrack -> GitLab: YouTrack's built-in GitLab VCS integration.

Same call the YouTrack UI makes in Project settings > Version Control > New VCS integration
(server type GitLab, repository URL + access token). YouTrack then registers a webhook in the
GitLab project and attaches commits / merge requests that mention DEVOPS-<n> to the request.
"""
import time

from .config import log


def ensure_gitlab_vcs(yt, gl, project):
    proc = _ensure_processor(yt, gl, project)
    check_webhook(yt, gl, project)
    return proc


def check_webhook(yt, gl, project):
    """YouTrack registers the GitLab webhook itself (with a secret token). Report where it points."""
    for _ in range(15):
        hooks = [h for h in gl.api.get(f"projects/{project['id']}/hooks") if "/api/vcsHooksReceiver/" in h["url"]]
        if hooks:
            for h in hooks:
                log(f"  GitLab webhook registered by YouTrack: {h['url']} (secret token: {h.get('token_present')})")
            return
        time.sleep(2)
    log("  WARNING: YouTrack did not register a webhook in GitLab")


def _ensure_processor(yt, gl, project):
    path = project["path_with_namespace"]
    # public URL: YouTrack stores links built from it (reachable from YouTrack via the loopback helper)
    url = f"{gl.public}/{path}"
    for server in yt.api.get("api/admin/integrations/vcsHostingServers",
                             params={"fields": "id,url,changesProcessors(id,path,project(id))"}):
        for proc in server.get("changesProcessors", []):
            if proc["path"] == path and proc["project"]["id"] == yt.project["id"]:
                return proc
    everyone = yt.all_users()
    log(f"YouTrack -> GitLab: VCS integration DEVOPS <-> {path}")
    return yt.api.post("api/admin/integrations/vcsHostingProcessors", {
        "$type": "GitLabChangesProcessor",
        "server": {"$type": "GitLabServer"},
        "project": {"id": yt.project["id"]},
        "url": url,
        "token": gl.api.headers["PRIVATE-TOKEN"],
        # requesters see the commits/MRs on their request too
        "visibleForGroups": [everyone],
    }, params={"fields": "id,path,server(id,url)"})
