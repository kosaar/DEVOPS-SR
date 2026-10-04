"""End-to-end demo of the request lifecycle, played by the real personas:

  maria.payments (developer)  submits a Demand in YouTrack                -> Triage (workflow)
  devops.lead                 accepts it and assigns lee.cicd             -> Accepted
  lee.cicd                    opens the GitLab issue, links it            -> In Progress
                              branch + commit + merge request (DEVOPS-n in names/messages)
  GitLab CI                   MR pipeline: test + build, writes pipeline/MR refs back to YouTrack
  lee.cicd                    merges -> main pipeline: test, build, deploy, smoke test,
                              "deployed" comment on the request
  lee.cicd                    closes the request                         -> Done (guard: GitLab ref present)

Every step uses documented REST APIs (YouTrack /api, GitLab /api/v4). Re-runnable: each run
creates a new request.
"""
import base64
import json
import os
import time
import urllib.parse

from .config import CFG, STATE_DIR, log
from .http import Client, wait_for
from .gitlab import GitLab
from . import youtrack

DAY = 86400000


def persona(yt, login):
    tf = os.path.join(STATE_DIR, f"youtrack-token-{login}")
    if not os.path.exists(tf):
        with open(tf, "w") as f:
            f.write(yt.mint_token(login, CFG["YOUTRACK_DEMO_USER_PASSWORD"], "devops-poc-lifecycle"))
    return Client(yt.base, {"Authorization": "Bearer " + open(tf).read().strip()})


def fields_of(api, iid):
    issue = api.get(f"api/issues/{iid}", params={
        "fields": "idReadable,summary,resolved,customFields(name,value(name,login)),tags(name),comments(text,author(login))"})
    out = {}
    for c in issue["customFields"]:
        v = c["value"]
        out[c["name"]] = (v.get("name") or v.get("login")) if isinstance(v, dict) else v
    issue["f"] = out
    return issue


def wait_pipeline(gl, pid, pipeline_id, what):
    log(f"  waiting for {what} (pipeline #{pipeline_id}) ...")
    status = {}

    def done():
        status["p"] = gl.api.get(f"projects/{pid}/pipelines/{pipeline_id}")
        return status["p"]["status"] in ("success", "failed", "canceled", "skipped")
    wait_for(what, done, timeout=900, interval=5)
    jobs = gl.api.get(f"projects/{pid}/pipelines/{pipeline_id}/jobs")
    for j in sorted(jobs, key=lambda j: j["id"]):
        log(f"    {j['stage']:<8} {j['name']:<18} {j['status']}")
    if status["p"]["status"] != "success":
        raise RuntimeError(f"{what} ended with status {status['p']['status']}: {status['p']['web_url']}")
    return status["p"]


def run():
    yt = youtrack.load()
    gl = GitLab()
    gl.group_id = gl.api.get(f"groups/{gl.pid(gl.group_path)}")["id"]
    project = gl.api.get(f"projects/{gl.pid(gl.group_path + '/ci-templates')}")
    pid = project["id"]
    gl_public = gl.public
    maria, lead, lee = persona(yt, "maria.payments"), persona(yt, "devops.lead"), persona(yt, "lee.cicd")
    yt_url = yt.public
    now = int(time.time() * 1000)
    stamp = time.strftime("%H%M%S")

    # 1. Developer submits a Demand (the same data the request form collects)
    log("1. maria.payments (Payments squad) submits a Demand")
    issue = maria.post("api/issues", {
        "project": {"id": yt.project["id"]},
        "summary": "Reusable smoke-test job in the CI template catalog",
        "description": ("### Description (required)\nWe need a shared `smoke-test` job template that checks a deployed "
                        "service answers on its health URL, so every squad stops copy-pasting curl loops.\n\n"
                        "### Business / technical impact (required)\nPayments had 2 releases last month where a broken "
                        "deploy was only detected by customers. A post-deploy smoke test would have caught both.\n\n"
                        "### Acceptance criteria (optional)\n- template `smoke-test` in platform/ci-templates\n"
                        "- visible in the template catalog\n"),
        "customFields": [
            {"$type": "SingleEnumIssueCustomField", "name": "Type", "value": {"name": "Demand"}},
            {"$type": "SingleEnumIssueCustomField", "name": "Requester Squad", "value": {"name": "Payments"}},
            {"$type": "SingleEnumIssueCustomField", "name": "Service", "value": {"name": "CI"}},
            {"$type": "SingleEnumIssueCustomField", "name": "Priority", "value": {"name": "P2 High"}},
            {"$type": "DateIssueCustomField", "name": "Target Date", "value": now + 14 * DAY},
        ],
    }, params={"fields": "id,idReadable"})
    key, iid = issue["idReadable"], issue["id"]
    st = fields_of(maria, iid)
    log(f"   {key} created -> State: {st['f']['State']} (intake rule), lead notified: {'lead-notified' in [t['name'] for t in st['tags']]}")
    assert st["f"]["State"] == "Triage", st["f"]

    # 2. DevOps lead triages
    log("2. devops.lead triages: Accepted, assigned to lee.cicd")
    lead.post(f"api/issues/{iid}", {"customFields": [
        {"$type": "StateIssueCustomField", "name": "State", "value": {"name": "Accepted"}},
        {"$type": "SingleUserIssueCustomField", "name": "Assignee", "value": {"login": "lee.cicd"}}]})
    lead.post(f"api/issues/{iid}/comments", {"text": "Accepted in triage: good fit for the shared CI templates. @lee.cicd please take it."})

    # 3. Implementation issue in GitLab, linked both ways
    log("3. lee.cicd opens the GitLab implementation issue and links it")
    gl_issue = gl.api.post(f"projects/{pid}/issues", {
        "title": f"{key}: reusable smoke-test job template",
        "description": f"Implementation of DevOps request {key} ({yt_url}/issue/{key}).\n\n"
                       "- [ ] add `templates/smoke-test.yml`\n- [ ] catalog shows it after deployment",
        "labels": "devops-request"})
    gl_issue_ref = f"{project['path_with_namespace']}#{gl_issue['iid']}"
    lee.post(f"api/issues/{iid}", {"customFields": [
        {"$type": "SimpleIssueCustomField", "name": "GitLab Project", "value": project["path_with_namespace"]},
        {"$type": "SimpleIssueCustomField", "name": "GitLab Issue/MR reference", "value": gl_issue_ref},
        {"$type": "StateIssueCustomField", "name": "State", "value": {"name": "In Progress"}}]})
    lee.post(f"api/issues/{iid}/comments", {"text": f"Implementation tracked in GitLab: [{gl_issue_ref}]({gl_issue['web_url']})"})

    # 4. Branch + commit + merge request
    branch = f"feature/{key}-smoke-test-{stamp}"
    log(f"4. branch {branch}, commit, merge request")
    gl.api.post(f"projects/{pid}/repository/branches", {"branch": branch, "ref": "main"})
    template = ("# Post-deploy smoke test: fail the job if the service does not answer on SMOKE_URL.\n"
                ".smoke-test:\n  image: alpine:3.20\n  script:\n"
                "    - for i in 1 2 3 4 5; do wget -q -O /dev/null \"$SMOKE_URL\" && exit 0; sleep 3; done; exit 1\n")
    try:
        gl.api.get(f"projects/{pid}/repository/files/{gl.pid('templates/smoke-test.yml')}", params={"ref": branch})
        action = "update"
    except Exception:  # noqa: BLE001
        action = "create"
    commit = gl.api.post(f"projects/{pid}/repository/commits", {
        "branch": branch,
        "commit_message": f"{key} Add reusable smoke-test job template\n\nCloses #{gl_issue['iid']}",
        "actions": [{"action": action, "file_path": "templates/smoke-test.yml", "encoding": "base64",
                     "content": base64.b64encode(template.encode()).decode()}]})
    mr = gl.api.post(f"projects/{pid}/merge_requests", {
        "source_branch": branch, "target_branch": "main",
        "title": f"{key}: Add reusable smoke-test job template",
        "description": f"Implements DevOps request {key}.\n\nCloses #{gl_issue['iid']}",
        "remove_source_branch": True})
    mr_ref = f"{project['path_with_namespace']}!{mr['iid']}"
    log(f"   commit {commit['short_id']}, merge request {mr_ref}")

    # 5. MR pipeline
    def mr_pipeline():
        m = gl.api.get(f"projects/{pid}/merge_requests/{mr['iid']}")
        return m.get("head_pipeline")
    wait_for("MR pipeline creation", lambda: mr_pipeline(), timeout=300, interval=3)
    wait_pipeline(gl, pid, mr_pipeline()["id"], "merge request pipeline")

    # 6. Merge -> main pipeline with deployment
    log("6. lee.cicd merges the MR -> main pipeline deploys to the demo environment")
    wait_for("MR mergeable", lambda: gl.api.get(f"projects/{pid}/merge_requests/{mr['iid']}")
             .get("detailed_merge_status") == "mergeable", timeout=120, interval=3)
    merged = gl.api.put(f"projects/{pid}/merge_requests/{mr['iid']}/merge", {"should_remove_source_branch": True})
    sha = merged["merge_commit_sha"] or merged["sha"]
    holder = {}

    def main_pipeline():
        ps = gl.api.get(f"projects/{pid}/pipelines", params={"ref": "main", "sha": sha})
        holder["p"] = ps[0] if ps else None
        return holder["p"]
    wait_for("main pipeline creation", main_pipeline, timeout=300, interval=3)
    main = wait_pipeline(gl, pid, holder["p"]["id"], "main pipeline (deploy)")

    # 7. Verify the deployment itself
    demo = Client("http://demo-app")
    served = demo.get("version.txt", raw=True).decode().strip()
    page = demo.get("", raw=True).decode()
    assert served == sha[:8], f"demo-app serves {served}, expected {sha[:8]}"
    assert "smoke-test" in page, "catalog does not list the new template"
    log(f"7. demo-app serves {served}; catalog lists 'smoke-test' -> deployment verified")

    # 8. Close the request (Done guard requires the GitLab reference)
    log("8. lee.cicd closes the request")
    lee.post(f"api/issues/{iid}", {"customFields": [
        {"$type": "SimpleIssueCustomField", "name": "GitLab Issue/MR reference", "value": mr_ref},
        {"$type": "StateIssueCustomField", "name": "State", "value": {"name": "Done"}}]})
    lee.post(f"api/issues/{iid}/comments", {"text": (
        f"Delivered: template `smoke-test` is available in the catalog "
        f"(http://localhost:{CFG['DEMO_APP_PORT']}). MR [{mr_ref}]({mr['web_url']}), "
        f"pipeline [#{main['id']}]({main['web_url']}).")})

    # 9. What the requester now sees
    time.sleep(5)
    final = fields_of(maria, iid)
    vcs = yt.api.get(f"api/issues/{iid}/vcsChanges", params={"fields": "id,version,text,urls"}) or []
    gl_issue_state = gl.api.get(f"projects/{pid}/issues/{gl_issue['iid']}")["state"]
    summary = {
        "request": f"{yt_url}/issue/{key}",
        "state": final["f"]["State"],
        "assignee": final["f"]["Assignee"],
        "GitLab Project": final["f"]["GitLab Project"],
        "GitLab Issue/MR reference": final["f"]["GitLab Issue/MR reference"],
        "Pipeline reference": final["f"]["Pipeline reference"],
        "gitlab_issue": f"{gl_public}/{project['path_with_namespace']}/-/issues/{gl_issue['iid']} ({gl_issue_state})",
        "merge_request": f"{gl_public}/{project['path_with_namespace']}/-/merge_requests/{mr['iid']}",
        "main_pipeline": main["web_url"],
        "deployed_version": served,
        "comments": [f"{c['author']['login']}: {c['text'][:90]}" for c in final["comments"]],
        "vcs_changes_attached_by_youtrack": len(vcs),
    }
    with open(os.path.join(STATE_DIR, "lifecycle.json"), "w") as f:
        json.dump(summary, f, indent=2)
    log("Lifecycle complete:\n" + json.dumps(summary, indent=2))
    assert final["f"]["State"] == "Done"
    assert final["f"]["Pipeline reference"], "CI did not write the pipeline reference"
    return summary
