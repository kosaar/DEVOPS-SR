"""Load the demo requests (demo_data.py) into the DEVOPS project.

Requests are created through the REST API exactly like real ones, so every workflow
rule runs (intake -> Triage, P1/P2 escalation, Blocked/Done guards). Then the DevOps
lead moves them through the workflow. Because YouTrack's REST API cannot backdate an
issue's creation time, the demo backlog's original request date is stored in the
"Requested On" field (which the DevOps team may set for migrated backlog items) and
"Blocked Since" is backdated for blocked items.
"""
import os
import time

from .config import CFG, STATE_DIR, log
from .demo_data import REQUESTS
from .http import Client
from . import youtrack

DAY = 86400000
SQUAD_REPORTER = {"Payments": "maria.payments", "Mobile": "tom.mobile"}


def describe(rtype, d):
    if rtype == "Demand":
        parts = [("Description", d["what"]), ("Business / technical impact", d["impact"])]
    elif rtype == "Bug":
        parts = [("Description", d.get("what", "See expected/actual behavior below.")),
                 ("Expected behavior", d["expected"]), ("Actual behavior", d["actual"]),
                 ("Evidence", d["evidence"])]
    else:
        parts = [("Description", d["what"]), ("Expected benefit", d["benefit"])]
    return "\n\n".join(f"### {h} (required)\n{t}" for h, t in parts) + "\n"


def enum(name, value):
    return {"$type": "SingleEnumIssueCustomField", "name": name, "value": {"name": value}}


def simple(name, value, t="SimpleIssueCustomField"):
    return {"$type": t, "name": name, "value": value}


def lead_client(yt):
    tf = os.path.join(STATE_DIR, "youtrack-token-devops-lead")
    if not os.path.exists(tf):
        tok = yt.mint_token(CFG["DEVOPS_LEAD_LOGIN"], CFG["YOUTRACK_DEMO_USER_PASSWORD"], "devops-poc-seed")
        with open(tf, "w") as f:
            f.write(tok)
    return Client(yt.base, {"Authorization": "Bearer " + open(tf).read().strip()})


def run():
    yt = youtrack.load()
    api = yt.api
    lead = lead_client(yt)
    pid = yt.project["id"]
    key = yt.key
    users = {u["login"]: u["id"] for u in api.get("api/users", params={"fields": "id,login", "$top": 100})}
    existing = {i["summary"] for i in api.get("api/issues", params={
        "query": f"project: {key}", "fields": "summary", "$top": 2000})}
    now = int(time.time() * 1000)
    created = 0
    for (rtype, squad, service, prio, state, age, assignee, summary, d) in REQUESTS:
        if summary in existing:
            continue
        fields = [enum("Type", rtype), enum("Requester Squad", squad), enum("Service", service), enum("Priority", prio)]
        if rtype == "Bug":
            fields.append(enum("Environment", d.get("env", "Production")))
        if "target" in d or rtype == "Demand":
            fields.append(simple("Target Date", now + d.get("target", 30) * DAY, "DateIssueCustomField"))
        reporter = SQUAD_REPORTER.get(squad, CFG["DEVOPS_LEAD_LOGIN"])
        issue = api.post(f"api/admin/projects/{pid}/issues", {
            "summary": summary, "description": describe(rtype, d), "reporter": {"id": users[reporter]},
            "customFields": fields,
        }, params={"fields": "id,idReadable"})
        iid = issue["id"]

        # The DevOps lead records the original request date (migrated backlog) and triages.
        upd = [simple("Requested On", now - age * DAY, "DateIssueCustomField")]
        if assignee:
            upd.append({"$type": "SingleUserIssueCustomField", "name": "Assignee", "value": {"login": assignee}})
        lead.post(f"api/issues/{iid}", {"customFields": upd})

        path = {"Triage": [], "Accepted": ["Accepted"], "In Progress": ["Accepted", "In Progress"],
                "Blocked": ["Accepted", "In Progress", "Blocked"], "Done": ["Accepted", "In Progress", "Done"],
                "Rejected": ["Rejected"]}[state]
        if "gitlab" in d:
            proj, ref, pipe = d["gitlab"]
            gl = [simple("GitLab Project", proj), simple("GitLab Issue/MR reference", ref)]
            if pipe:
                gl.append(simple("Pipeline reference", pipe))
            lead.post(f"api/issues/{iid}", {"customFields": gl})
        if d.get("no_code"):
            lead.post("api/commands", {"query": "tag no-code-change", "issues": [{"id": iid}]})
        if state == "Rejected":
            lead.post(f"api/issues/{iid}/comments", {"text": d["rejected_why"]})
        for st in path:
            body = [{"$type": "StateIssueCustomField", "name": "State", "value": {"name": st}}]
            if st == "Blocked":
                body.insert(0, simple("Blocked Reason", d["blocked"][0]))
            lead.post(f"api/issues/{iid}", {"customFields": body})
        if state == "Blocked":
            lead.post(f"api/issues/{iid}", {"customFields": [
                simple("Blocked Since", now - d["blocked"][1] * DAY, "DateIssueCustomField")]})
        if state == "Accepted":
            lead.post(f"api/issues/{iid}/comments", {"text": "Accepted in triage. Planned within the next iterations."})
        created += 1
        log(f"  {issue['idReadable']:<11} {state:<12} {prio:<12} {squad:<16} {summary}")
    log(f"Created {created} demo requests ({len(REQUESTS)} in the data set)")

    # Recompute Aging buckets/tags now instead of waiting for the hourly rule.
    api.post("api/commands", {"query": "refresh-aging", "issues": [
        {"id": i["id"]} for i in api.get("api/issues", params={"query": f"project: {key}", "fields": "id", "$top": 2000})]})
    log("Aging refreshed (command 'refresh-aging')")
    recalc_reports(api)


def recalc_reports(api):
    """Reports are computed lazily; trigger a calculation so the dashboard is populated."""
    for r in api.get("api/reports", params={"fields": "id", "$top": 200}):
        api.post(f"api/reports/{r['id']}/status", {"calculationInProgress": True})
    log("Reports recalculated")
