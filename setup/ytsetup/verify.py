"""Acceptance checks for the POC. Prints a PASS/FAIL table; exit code 1 on any failure."""
import json
import os
import time

from .config import CFG, STATE_DIR, log
from .http import ApiError, Client
from .gitlab import GitLab
from .lifecycle import persona
from . import youtrack

RESULTS = []


def check(area, name, fn):
    try:
        ok, detail = fn()
    except Exception as e:  # noqa: BLE001
        ok, detail = False, f"{type(e).__name__}: {str(e)[:160]}"
    RESULTS.append((area, name, ok, detail))


def count(api, q):
    for _ in range(20):
        c = api.post("api/issuesGetter/count", {"query": q}, params={"fields": "count"})["count"]
        if c >= 0:
            return c
        time.sleep(0.5)
    return -1


def run():
    yt = youtrack.load()
    api, key = yt.api, yt.key
    gl = GitLab()
    p = f"project: {key}"

    # ---------------------------------------------------------------- YouTrack model
    def fields():
        names = {c["field"]["name"] for c in api.get(f"api/admin/projects/{yt.project['id']}/customFields",
                                                       params={"fields": "field(name)"})}
        need = {"Type", "Requester Squad", "Service", "Priority", "State", "Assignee", "Target Date", "Blocked Reason",
                "GitLab Project", "GitLab Issue/MR reference", "Pipeline reference"}
        return need <= names, f"{len(names)} fields; missing: {sorted(need - names) or 'none'}"
    check("Model", "Project DEVOPS with all required fields", fields)

    def app():
        app_id = next(a["id"] for a in api.get("api/admin/apps", params={"fields": "id,name", "$top": 200})
                      if a["name"] == "devops-demand")
        rules = api.get(f"api/admin/workflows/{app_id}/rules", params={"fields": "name"})
        return len(rules) >= 9, f"{len(rules)} modules: " + ", ".join(r["name"] for r in rules)
    check("Workflow", "Workflow app installed", app)

    # ---------------------------------------------------------------- demo data
    check("Demo data", ">= 50 requests", lambda: (lambda n: (n >= 50, f"{n} requests"))(count(api, p)))
    def squads():
        res = {s: count(api, f"{p} {{Requester Squad}}: {{{s}}}") for s in youtrack.SQUADS}
        return all(v > 0 for v in res.values()), ", ".join(f"{k}={v}" for k, v in res.items())
    check("Demo data", "requests from all 10 squads", squads)
    for label, q in [("demands", "Type: Demand"), ("bugs", "Type: Bug"), ("improvements", "Type: Improvement"),
                     ("open P1/P2", "#Unresolved Priority: {P1 Critical}, {P2 High}"),
                     ("blocked with reason", "State: Blocked has: {Blocked Reason}"),
                     ("aging (tag)", "#Unresolved tag: aging"),
                     ("completed in last 30 days", "State: Done resolved date: {minus 30d} .. Today")]:
        check("Demo data", label, lambda q=q: (lambda n: (n > 0, f"{n}"))(count(api, f"{p} {q}")))

    # ---------------------------------------------------------------- developer experience
    maria = persona(yt, "maria.payments")

    def submit():
        t0 = time.time()
        i = maria.post("api/issues", {
            "project": {"id": yt.project["id"]}, "summary": "verify: runner tag for ARM builds",
            "description": "### Description (required)\nNeed an ARM runner tag.\n\n### Expected benefit (required)\nNative ARM images.\n",
            "customFields": [{"$type": "SingleEnumIssueCustomField", "name": "Type", "value": {"name": "Improvement"}},
                             {"$type": "SingleEnumIssueCustomField", "name": "Requester Squad", "value": {"name": "Payments"}},
                             {"$type": "SingleEnumIssueCustomField", "name": "Service", "value": {"name": "CI"}},
                             {"$type": "SingleEnumIssueCustomField", "name": "Priority", "value": {"name": "P4 Low"}}],
        }, params={"fields": "id,idReadable,customFields(name,value(name))"})
        state = next(c["value"]["name"] for c in i["customFields"] if c["name"] == "State")
        api.delete(f"api/issues/{i['id']}")
        return state == "Triage", f"{i['idReadable']} -> {state} in {time.time() - t0:.1f}s (deleted again)"
    check("Developer", "submit request -> lands in Triage", submit)

    def incomplete():
        try:
            maria.post("api/issues", {"project": {"id": yt.project["id"]}, "summary": "verify: incomplete bug",
                                      "description": "it is broken",
                                      "customFields": [{"$type": "SingleEnumIssueCustomField", "name": "Type", "value": {"name": "Bug"}},
                                                       {"$type": "SingleEnumIssueCustomField", "name": "Requester Squad", "value": {"name": "Payments"}},
                                                       {"$type": "SingleEnumIssueCustomField", "name": "Service", "value": {"name": "CI"}}]})
            return False, "incomplete bug was accepted"
        except ApiError as e:
            return True, json.loads(e.body).get("error_description", "")[:120]
    check("Developer", "incomplete request rejected with a clear message", incomplete)

    def status_visible():
        mine = maria.get("api/issues", params={"query": f"{p} reporter: me", "fields": "idReadable,customFields(name,value(name))"})
        return len(mine) > 0, f"maria sees {len(mine)} own requests with their State"
    check("Developer", "requester can see her requests' status", status_visible)

    def cannot_triage():
        mine = maria.get("api/issues", params={"query": f"{p} reporter: me State: Triage", "fields": "id", "$top": 1})
        if not mine:
            return True, "no triage request to test"
        try:
            maria.post(f"api/issues/{mine[0]['id']}", {"customFields": [
                {"$type": "StateIssueCustomField", "name": "State", "value": {"name": "Done"}}]})
            return False, "requester could change State"
        except ApiError as e:
            return True, f"HTTP {e.status} (DevOps Requester role)"
    check("Developer", "requester cannot change workflow state", cannot_triage)

    # ---------------------------------------------------------------- DevOps team
    lead = persona(yt, "devops.lead")

    def blocked_guard():
        i = lead.get("api/issues", params={"query": f"{p} State: Accepted", "fields": "id,idReadable", "$top": 1})[0]
        try:
            lead.post("api/commands", {"query": "State Blocked", "issues": [{"id": i["id"]}]})
            return False, "Blocked accepted without reason"
        except ApiError as e:
            return True, json.loads(e.body).get("error_description", "")[:110]
    check("DevOps", "Blocked requires Blocked Reason", blocked_guard)

    def done_guard():
        cands = lead.get("api/issues", params={"query": f"{p} State: Accepted",
                                               "fields": "id,tags(name),customFields(name,value)", "$top": 50})
        i = next(c for c in cands if not c["tags"] and not next((f["value"] for f in c["customFields"]
                                               if f["name"] == "GitLab Issue/MR reference"), None))
        try:
            lead.post("api/commands", {"query": "State Done", "issues": [{"id": i["id"]}]})
            return False, "Done accepted without GitLab reference"
        except ApiError as e:
            return True, json.loads(e.body).get("error_description", "")[:110]
    check("DevOps", "Done requires GitLab reference", done_guard)

    check("DevOps", "Kanban board with 5 columns, valid", lambda: (lambda b: (
        [c["presentation"] for c in b["columnSettings"]["columns"]] == ["Triage", "Accepted", "In Progress", "Blocked", "Done"]
        and b["status"]["valid"],
        " -> ".join(c["presentation"] for c in b["columnSettings"]["columns"]) + ("" if b["status"]["valid"] else f" ERRORS: {b['status']['errors']}")))(
        api.get(f"api/agiles/{yt.board['id']}", params={"fields": "columnSettings(columns(presentation)),status(valid,errors)"})))

    def mail():
        m = Client("http://mailpit:8025").get("api/v1/search", params={"query": f"to:{CFG['DEVOPS_LEAD_LOGIN']}@devops-poc.local subject:P1"})
        m2 = Client("http://mailpit:8025").get("api/v1/search", params={"query": f"to:{CFG['DEVOPS_LEAD_LOGIN']}@devops-poc.local subject:P2"})
        n = m.get("messages_count", 0) + m2.get("messages_count", 0)
        return n > 0, f"{n} P1/P2 escalation e-mails to the DevOps lead in Mailpit (sent ~1 min after the change)"
    check("DevOps", "P1/P2 notify the DevOps lead", mail)

    # ---------------------------------------------------------------- management
    def dashboard():
        d = api.get(f"api/dashboards/{yt.dashboard_id}", params={"fields": "name,widgets(id)"})
        return len(d["widgets"]) >= 10, f"'{d['name']}' with {len(d['widgets'])} widgets"
    check("Management", "dashboard exists", dashboard)

    def reports():
        from .seed import recalc_reports
        recalc_reports(api)
        time.sleep(5)
        rs = api.get("api/reports", params={"fields": "name,data(total(value))", "$top": 100})
        rs = [r for r in rs if r["name"] in {x[0] for x in yt.REPORTS}]
        ok = [r for r in rs if r.get("data") and r["data"].get("total")]
        return len(ok) == len(yt.REPORTS), f"{len(ok)}/{len(yt.REPORTS)} reports calculated"
    check("Management", "squad/service/priority/aging reports calculated", reports)

    # ---------------------------------------------------------------- GitLab
    def runner():
        rs = gl.api.get("runners/all", params={"type": "instance_type"})
        online = [r for r in rs if r.get("status") == "online"]
        return bool(online), f"{len(online)} online instance runner(s)"
    check("GitLab", "CI runner online", runner)

    lf = os.path.join(STATE_DIR, "lifecycle.json")
    if os.path.exists(lf):
        s = json.load(open(lf))
        check("Lifecycle", "request Done with GitLab MR + pipeline refs", lambda: (
            s["state"] == "Done" and "!" in s["GitLab Issue/MR reference"] and "/pipelines/" in s["Pipeline reference"],
            f"{s['request']} {s['state']} {s['GitLab Issue/MR reference']}"))
        check("Lifecycle", "CI wrote back to YouTrack (bot comments)", lambda: (
            sum(c.startswith("gitlab.bot") for c in s["comments"]) >= 2, f"{sum(c.startswith('gitlab.bot') for c in s['comments'])} gitlab.bot comments"))
        check("Lifecycle", "YouTrack GitLab integration attached commits", lambda: (
            s["vcs_changes_attached_by_youtrack"] > 0, f"{s['vcs_changes_attached_by_youtrack']} VCS changes on the request"))
        check("Lifecycle", "deployed version served by demo-app", lambda: (lambda v: (
            v == s["deployed_version"], f"demo-app serves {v}"))(Client("http://demo-app").get("version.txt", raw=True).decode().strip()))
    else:
        RESULTS.append(("Lifecycle", "lifecycle demo", False, "run `lifecycle` first"))

    width = max(len(r[1]) for r in RESULTS)
    print()
    for area, name, ok, detail in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'}  {area:<10} {name:<{width}}  {detail}")
    failed = [r for r in RESULTS if not r[2]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    with open(os.path.join(STATE_DIR, "verify.txt"), "w") as f:
        for area, name, ok, detail in RESULTS:
            f.write(f"{'PASS' if ok else 'FAIL'}  {area:<10} {name:<{width}}  {detail}\n")
    log("Verification finished")
    return not failed
