"""Idempotent YouTrack configuration for the DevOps Demand Management POC.

Everything is done through YouTrack / embedded Hub REST APIs with a permanent token
(the documented authentication method for scripts). Re-running is safe: objects are
looked up by name and only created/updated when needed.
"""
import io
import json
import os
import time
import zipfile

from .config import CFG, STATE_DIR, ROOT, log
from .http import ApiError, Client, browser_login_token, wait_for

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
SQUADS = ["Payments", "Customer Portal", "Mobile", "Data", "CRM", "Analytics",
          "Security", "Internal Tools", "Commerce", "Operations"]
SERVICES = ["CI", "CD", "Git", "Kubernetes", "Infrastructure", "Developer Experience", "Other"]
PRIORITIES = [("P1 Critical", "#d93025"), ("P2 High", "#e8710a"), ("P3 Normal", "#1a73e8"), ("P4 Low", "#9aa0a6")]
TYPES = ["Demand", "Bug", "Improvement"]
STATES = [("New", False), ("Triage", False), ("Accepted", False), ("In Progress", False),
          ("Blocked", False), ("Done", True), ("Rejected", True)]
ENVIRONMENTS = ["Development", "Test", "Staging", "Production"]
AGING = ["0-7 days", "8-14 days", "15-30 days", "31-60 days", "60+ days"]

# (field name, field type, bundle name or None, values, required, empty text, default)
FIELDS = [
    ("Type", "enum[1]", "DEVOPS Request Types", TYPES, True, None, "Demand"),
    ("Requester Squad", "enum[1]", "DEVOPS Squads", SQUADS, True, "Select your squad", None),
    ("Service", "enum[1]", "DEVOPS Services", SERVICES, True, "Select a service", None),
    ("Priority", "enum[1]", "DEVOPS Priorities", [p for p, _ in PRIORITIES], True, None, "P3 Normal"),
    ("State", "state[1]", "DEVOPS States", [s for s, _ in STATES], True, None, "New"),
    ("Assignee", "user[1]", "DEVOPS Team", None, False, "Unassigned", None),
    ("Target Date", "date", None, None, False, "No target date", None),
    ("Requested On", "date", None, None, False, "Set on submit", None),
    ("Environment", "enum[1]", "DEVOPS Environments", ENVIRONMENTS, False, "Not applicable", None),
    ("Blocked Reason", "string", None, None, False, "", None),
    ("Blocked Since", "date and time", None, None, False, "", None),
    ("GitLab Project", "string", None, None, False, "", None),
    ("GitLab Issue/MR reference", "string", None, None, False, "", None),
    ("Pipeline reference", "string", None, None, False, "", None),
    ("Aging", "enum[1]", "DEVOPS Aging", AGING, False, "Not computed yet", None),
]
TAGS = ["aging", "lead-notified", "no-code-change"]

# Demo users. YouTrack Server is free for up to 10 users (admin + 7 people + the GitLab CI bot = 9).
# Users beyond the licence limit are automatically banned.
TEAM_GROUP = "DevOps Team"
REQUESTERS_GROUP = "Squad Developers"
MANAGEMENT_GROUP = "Engineering Management"
USERS = [
    # login, full name, group
    ("devops.lead", "Dana Lead (DevOps lead)", TEAM_GROUP),
    ("alex.ops", "Alex Ops", TEAM_GROUP),
    ("sam.platform", "Sam Platform", TEAM_GROUP),
    ("lee.cicd", "Lee CI/CD", TEAM_GROUP),
    ("maria.payments", "Maria (Payments squad)", REQUESTERS_GROUP),
    ("tom.mobile", "Tom (Mobile squad)", REQUESTERS_GROUP),
    ("eng.manager", "Erin (Engineering manager)", MANAGEMENT_GROUP),
]

REQUESTER_ROLE_KEY = "devops-requester"
REQUESTER_PERMISSIONS = [
    "JetBrains.YouTrack.READ_ISSUE", "JetBrains.YouTrack.CREATE_ISSUE",
    "JetBrains.YouTrack.READ_COMMENT", "JetBrains.YouTrack.CREATE_COMMENT", "JetBrains.YouTrack.UPDATE_COMMENT",
    "JetBrains.YouTrack.CREATE_ATTACHMENT_ISSUE", "JetBrains.YouTrack.VIEW_WATCHERS",
    "JetBrains.YouTrack.READ_ARTICLE", "JetBrains.YouTrack.READ_ARTICLE_COMMENT",
    "jetbrains.jetpass.project-read-basic",
]


class YouTrack:
    def __init__(self):
        self.base = CFG["YOUTRACK_INTERNAL_URL"]
        self.public = CFG["YOUTRACK_BASE_URL"].rstrip("/")
        self.key = CFG["YOUTRACK_PROJECT_KEY"]
        self.api = Client(self.base)
        self.project = None
        self.field_ids = {}

    # ------------------------------------------------------------------ auth
    def wait_ready(self):
        log("Waiting for YouTrack ...")
        wait_for("YouTrack", lambda: self.api.get("api/config", params={"fields": "version"}), timeout=900)

    def token_file(self):
        return os.path.join(STATE_DIR, "youtrack-token")

    def authenticate(self):
        tf = self.token_file()
        if os.path.exists(tf):
            tok = open(tf).read().strip()
            self.api.headers["Authorization"] = f"Bearer {tok}"
            try:
                self.api.get("api/users/me", params={"fields": "login"})
                return
            except ApiError:
                log("Stored YouTrack token is no longer valid, re-creating it")
        cfg = self.api.get("api/config", params={"fields": "ring(serviceId)"})
        service_id = cfg["ring"]["serviceId"]
        access = None
        for pwd in (CFG["YOUTRACK_ADMIN_PASSWORD"], "admin"):
            access = browser_login_token(self.base, service_id, "admin", pwd, public_url=self.public)
            if access:
                break
        if not access:
            raise RuntimeError("Cannot log into YouTrack as admin with the configured password or the default one")
        tmp = Client(self.base, {"Authorization": f"Bearer {access}"})
        tok = tmp.post("hub/api/rest/users/me/permanenttokens", {
            "name": f"devops-poc-setup-{int(time.time())}",
            "scope": [{"id": "0-0-0-0-0"}, {"id": service_id}],
        }, params={"fields": "token"})["token"]
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(tf, "w") as f:
            f.write(tok)
        os.chmod(tf, 0o600)
        self.api.headers["Authorization"] = f"Bearer {tok}"
        log("Created a YouTrack permanent token for admin (stored in .state/youtrack-token)")
        if pwd == "admin":
            self.set_password("admin", CFG["YOUTRACK_ADMIN_PASSWORD"], old="admin")
            log("Replaced the default YouTrack admin password with YOUTRACK_ADMIN_PASSWORD")

    def mint_token(self, login, password, name):
        """Permanent token for another user (used by GitLab CI to update requests)."""
        service_id = self.api.get("api/config", params={"fields": "ring(serviceId)"})["ring"]["serviceId"]
        access = browser_login_token(self.base, service_id, login, password, public_url=self.public)
        if not access:
            raise RuntimeError(f"Cannot log into YouTrack as {login}")
        tmp = Client(self.base, {"Authorization": f"Bearer {access}"})
        return tmp.post("hub/api/rest/users/me/permanenttokens", {
            "name": name, "scope": [{"id": "0-0-0-0-0"}, {"id": service_id}],
        }, params={"fields": "token"})["token"]

    # ------------------------------------------------------------------ hub helpers
    def hub_user(self, login):
        res = self.api.get("hub/api/rest/users", params={
            "query": f"login: {login}", "fields": "id,login,details(id,type,login)", "$top": 5})
        for u in res.get("users", []):
            if u["login"] == login:
                return u
        return None

    def set_password(self, login, password, old=None):
        u = self.hub_user(login)
        for d in u.get("details", []):
            if d["type"] == "LoginuserdetailsJSON":
                self.api.post(f"hub/api/rest/userdetails/{d['id']}", {
                    "type": "LoginuserdetailsJSON",
                    "password": dict({"type": "PlainpasswordJSON", "value": password},
                                     **({"oldValue": old} if old else {})),
                }, params={"fields": "id"})

    def hub_group(self, name, description=""):
        res = self.api.get("hub/api/rest/usergroups", params={"query": f'name: "{name}"', "fields": "id,name", "$top": 50})
        for g in res.get("usergroups", []):
            if g["name"] == name:
                return g
        log(f"  + group {name}")
        return self.api.post("hub/api/rest/usergroups", {"name": name, "description": description},
                             params={"fields": "id,name"})

    # ------------------------------------------------------------------ steps
    def remove_demo_project(self):
        for p in self.api.get("api/admin/projects", params={"fields": "id,shortName"}):
            if p["shortName"] == "DEMO" and CFG.get("KEEP_YOUTRACK_DEMO", "false").lower() != "true":
                log("Removing the sample 'Demo project' shipped with YouTrack")
                for d in self.api.get("api/dashboards", params={"fields": "id,name", "$top": 100}):
                    if d["name"] == "DEMO Dashboard":
                        self.api.delete(f"api/dashboards/{d['id']}")
                self.api.delete(f"api/admin/projects/{p['id']}")

    def configure_email(self):
        log("Configuring e-mail notifications -> Mailpit SMTP sink")
        self.api.post("api/admin/globalSettings/notificationSettings", {
            "emailSettings": {
                "isEnabled": True, "host": "mailpit", "port": 1025, "mailProtocol": "SMTP",
                "anonymous": True, "from": "youtrack@devops-poc.local", "replyTo": "no-reply@devops-poc.local",
            }
        }, params={"fields": "emailSettings(isEnabled)"})

    def users_and_groups(self):
        log("Users and groups")
        groups = {g: self.hub_group(g) for g in (TEAM_GROUP, REQUESTERS_GROUP, MANAGEMENT_GROUP)}
        for login, name, group in USERS:
            u = self.hub_user(login)
            if not u:
                log(f"  + user {login}")
                u = self.api.post("hub/api/rest/users", {
                    "login": login, "name": name,
                    "profile": {"email": {"type": "EmailJSON", "email": f"{login}@devops-poc.local", "verified": True}},
                    "details": [{"type": "LoginuserdetailsJSON", "login": login,
                                 "password": {"type": "PlainpasswordJSON", "value": CFG["YOUTRACK_DEMO_USER_PASSWORD"]}}],
                }, params={"fields": "id,login"})
            members = self.api.get(f"hub/api/rest/usergroups/{groups[group]['id']}/users",
                                   params={"fields": "id", "$top": 200}).get("users", [])
            if u["id"] not in {m["id"] for m in members}:
                self.api.post(f"hub/api/rest/usergroups/{groups[group]['id']}/users", {"id": u["id"]})
        self.groups = groups

    def requester_role(self):
        """Custom role (YouTrack roles API) - returns the matching Hub role (for project role grants)."""
        roles = self.api.get("api/roles", params={"fields": "id,name", "$top": 100})
        if not any(r["name"] == "DevOps Requester" for r in roles):
            log("  + role 'DevOps Requester' (create/read/comment requests, cannot change workflow fields)")
            self.api.post("api/roles", {
                "name": "DevOps Requester",
                "description": "Squad developers: submit and follow DevOps requests.",
                "permissions": [{"id": k} for k in REQUESTER_PERMISSIONS],
            }, params={"fields": "id"})
        roles = self.api.get("api/roles", params={"fields": "id,name", "$top": 100})
        return {"yt_id": next(r["id"] for r in roles if r["name"] == "DevOps Requester")}

    def bundle(self, kind, name, values):
        """Create/extend an enum/state/user bundle; returns its id."""
        path = f"api/admin/customFieldSettings/bundles/{kind}"
        existing = self.api.get(path, params={"fields": "id,name", "$top": 500})
        b = next((x for x in existing if x["name"] == name), None)
        if kind == "user":
            if not b:
                b = self.api.post(path, {"name": name}, params={"fields": "id"})
            grp = self.api.get("api/groups", params={"fields": "id,name", "$top": 200})
            g = next(x for x in grp if x["name"] == TEAM_GROUP)
            have = self.api.get(f"{path}/{b['id']}/groups", params={"fields": "id"})
            if g["id"] not in {x["id"] for x in have}:
                self.api.post(f"{path}/{b['id']}/groups", {"id": g["id"]})
            return b["id"]
        if not b:
            b = self.api.post(path, {"name": name}, params={"fields": "id"})
        have = {v["name"]: v for v in self.api.get(f"{path}/{b['id']}/values", params={"fields": "id,name", "$top": 200})}
        for i, v in enumerate(values):
            body = {"name": v, "ordinal": i}
            if kind == "state":
                body["isResolved"] = dict(STATES)[v]
            if name == "DEVOPS Priorities":
                body["color"] = {"id": {"P1 Critical": "2", "P2 High": "8", "P3 Normal": "4", "P4 Low": "1"}[v]}
            if v in have:
                self.api.post(f"{path}/{b['id']}/values/{have[v]['id']}", body)
            else:
                self.api.post(f"{path}/{b['id']}/values", body)
        return b["id"]

    def global_field(self, name, ftype):
        fields = self.api.get("api/admin/customFieldSettings/customFields",
                              params={"fields": "id,name,fieldType(id)", "$top": 500})
        f = next((x for x in fields if x["name"] == name), None)
        if f:
            if f["fieldType"]["id"] != ftype:
                raise RuntimeError(f"Field {name} exists with type {f['fieldType']['id']} (expected {ftype})")
            return f["id"]
        log(f"  + custom field {name} ({ftype})")
        return self.api.post("api/admin/customFieldSettings/customFields", {
            "name": name, "fieldType": {"id": ftype}, "isAutoAttached": False, "isDisplayedInIssueList": True,
        }, params={"fields": "id"})["id"]

    def create_project(self):
        projects = self.api.get("api/admin/projects", params={"fields": "id,shortName,name,ringId", "$top": 200})
        p = next((x for x in projects if x["shortName"] == self.key), None)
        if not p:
            log(f"Creating project {self.key}")
            me = self.api.get("api/users/me", params={"fields": "id"})
            lead = self.api.get("api/users", params={"query": CFG["DEVOPS_LEAD_LOGIN"], "fields": "id,login"})
            lead = next((u for u in lead if u["login"] == CFG["DEVOPS_LEAD_LOGIN"]), me)
            p = self.api.post("api/admin/projects", {
                "name": "DevOps Requests", "shortName": self.key, "leader": {"id": lead["id"]},
                "description": "Central intake for demands, bugs and improvements addressed to the DevOps team. "
                               "Submit requests with the forms in the knowledge base article 'How to request DevOps help'.",
            }, params={"fields": "id,shortName,ringId", "template": "kanban"})
        self.project = p

    def project_fields(self):
        log("Project custom fields")
        pid = self.project["id"]
        path = f"api/admin/projects/{pid}/customFields"
        current = self.api.get(path, params={"fields": "id,field(id,name),bundle(id,name)", "$top": 100})
        wanted = {f[0] for f in FIELDS}
        # drop fields from the project template that are not part of the model
        for pcf in current:
            if pcf["field"]["name"] not in wanted:
                self.api.delete(f"{path}/{pcf['id']}")
        current = {c["field"]["name"]: c for c in self.api.get(path, params={"fields": "id,field(id,name),bundle(id,name)"})}
        for i, (name, ftype, bundle_name, values, required, empty_text, default) in enumerate(FIELDS):
            fid = self.global_field(name, ftype)
            self.field_ids[name] = fid
            body = {"field": {"id": fid}, "canBeEmpty": not required, "ordinal": i, "isPublic": True}
            if empty_text:
                body["emptyFieldText"] = empty_text
            kind = None
            if ftype.startswith("enum"):
                body["$type"], kind, btype = "EnumProjectCustomField", "enum", "EnumBundle"
            elif ftype.startswith("state"):
                body["$type"], kind, btype = "StateProjectCustomField", "state", "StateBundle"
            elif ftype.startswith("user"):
                body["$type"], kind, btype = "UserProjectCustomField", "user", "UserBundle"
            else:
                body["$type"] = "SimpleProjectCustomField"
            body["field"]["$type"] = "CustomField"
            if kind:
                bid = self.bundle(kind, bundle_name, values)
                body["bundle"] = {"id": bid, "$type": btype}
                body["defaultValues"] = []
                if default:
                    vals = self.api.get(f"api/admin/customFieldSettings/bundles/{kind}/{bid}/values",
                                        params={"fields": "id,name"})
                    dv = next(v for v in vals if v["name"] == default)
                    body["defaultValues"] = [{"id": dv["id"], "$type": "StateBundleElement" if kind == "state" else "EnumBundleElement"}]
            body = dict([("$type", body.pop("$type"))] + list(body.items()))  # $type must come first
            pcf = current.get(name)
            if pcf and "bundle" in body and pcf.get("bundle", {}).get("id") != body["bundle"]["id"]:
                # attached by the project template with a shared bundle -> re-attach with ours
                self.api.delete(f"{path}/{pcf['id']}")
                time.sleep(2)
                pcf = None
            if pcf:
                upd = {k: v for k, v in body.items() if k not in ("field", "bundle")}
                self.api.post(f"{path}/{pcf['id']}", upd)
            else:
                self.api.post(path, body, params={"fields": "id"})

    def team_and_roles(self):
        log("Project team and access")
        pid = self.project["id"]
        groups = {g["name"]: g for g in self.api.get("api/groups", params={"fields": "id,name,ringId", "$top": 200})}
        team = {g["id"] for g in self.api.get(f"api/admin/projects/{pid}/team/groups", params={"fields": "id"})}
        if groups[TEAM_GROUP]["id"] not in team:
            self.api.post(f"api/admin/projects/{pid}/team/groups", {"id": groups[TEAM_GROUP]["id"]})
        role = self.requester_role()
        have = self.api.get("api/assignedRoles", params={
            "fields": "id,role(id,name),scope(project(id)),holder(id)", "$top": 500})
        for gname in (REQUESTERS_GROUP, MANAGEMENT_GROUP):
            gid = groups[gname]["id"]
            if not any(r["role"]["id"] == role["yt_id"] and (r.get("holder") or {}).get("id") == gid
                       and ((r.get("scope") or {}).get("project") or {}).get("id") == pid for r in have):
                self.api.post("api/assignedRoles", {
                    "$type": "AssignedRole",
                    "scope": {"$type": "ProjectScope", "project": {"id": pid}},
                    "holder": {"$type": "NestedGroup", "id": gid},
                    "role": {"id": role["yt_id"]},
                })

    def tags(self):
        log("Shared tags")
        groups = {g["name"]: g for g in self.api.get("api/groups", params={"fields": "id,name,allUsersGroup", "$top": 200})}
        everyone = next(g for g in groups.values() if g.get("allUsersGroup"))
        existing = {t["name"]: t for t in self.api.get("api/tags", params={"fields": "id,name", "$top": 500})}
        for t in TAGS:
            sharing = {"readSharingSettings": {"permittedGroups": [{"id": everyone["id"]}]},
                       "tagSharingSettings": {"permittedGroups": [{"id": everyone["id"]}]},
                       "updateSharingSettings": {"permittedGroups": [{"id": groups[TEAM_GROUP]["id"]}]}}
            if t not in existing:
                self.api.post("api/tags", dict(name=t, **sharing), params={"fields": "id"})
            else:
                self.api.post(f"api/tags/{existing[t]['id']}", sharing)

    # ------------------------------------------------------------------ app (workflows + widget)
    def build_app_zip(self):
        src = os.path.join(ROOT, "youtrack", "app", "devops-demand")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for dirpath, _, files in os.walk(src):
                for fn in sorted(files):
                    full = os.path.join(dirpath, fn)
                    rel = os.path.relpath(full, src)
                    data = open(full, "rb").read()
                    if rel == "settings.json":
                        # bake .env values in as defaults (still editable in the YouTrack UI)
                        s = json.loads(data)
                        s["properties"]["agingThresholdDays"]["default"] = int(CFG["AGING_THRESHOLD_DAYS"])
                        s["properties"]["devopsLeadLogin"]["default"] = CFG["DEVOPS_LEAD_LOGIN"]
                        data = json.dumps(s, indent=2).encode()
                    z.writestr(rel, data)
        return buf.getvalue()

    def install_app(self):
        log("Uploading app 'devops-demand' (workflow rules + KPI widget)")
        app = self.api.upload("api/admin/apps/import", "devops-demand.zip", self.build_app_zip(),
                              params={"fields": "id,name,title"})
        if isinstance(app, list):
            app = app[0]
        pid = self.project["id"]
        confs = self.api.get(f"api/admin/projects/{pid}/appConfigurations", params={"fields": "id,app(id,name)"},
                             ok404=True) or []
        if not any(c["app"]["name"] == "devops-demand" for c in confs):
            self.api.post(f"api/admin/projects/{pid}/appConfigurations", {"app": {"id": app["id"]}},
                          params={"fields": "id"})
        self.app = app
        # surface rule problems early (e.g. missing fields)
        rules = self.api.get(f"api/admin/workflows/{app['id']}/rules", params={"fields": "name,title"})
        log(f"  app {app['id']} has {len(rules)} rules: {', '.join(r['name'] for r in rules)}")

    # ------------------------------------------------------------------ board, searches, reports, dashboard
    def agile_board(self):
        log("Kanban board 'DevOps Kanban'")
        state_field = self.field_ids["State"]
        body = {
            "name": "DevOps Kanban",
            "projects": [{"id": self.project["id"]}],
            "columnSettings": {
                "field": {"id": state_field},
                "columns": [
                    dict({"presentation": s, "fieldValues": [{"name": s}], "ordinal": i},
                         **({"wipLimit": {"max": 6}} if s == "In Progress" else {}))
                    for i, s in enumerate(["Triage", "Accepted", "In Progress", "Blocked", "Done"])
                ],
            },
            "sprintsSettings": {"disableSprints": True, "isExplicit": False,
                                "explicitQuery": "#Unresolved or resolved date: {minus 30d} .. Today"},
            "colorCoding": {"$type": "FieldBasedColorCoding", "prototype": {"id": self.field_ids["Priority"]}},
            "cardSettings": {"fields": [
                {"field": {"id": self.field_ids[f]}, "presentation": {"id": "FULL_NAME"}}
                for f in ("Type", "Requester Squad", "Service", "Assignee", "Target Date")]},
            "readSharingSettings": {"permittedGroups": [self.all_users()]},
        }
        boards = self.api.get("api/agiles", params={"fields": "id,name,projects(id)", "$top": 100})
        for x in boards:  # board auto-created by the project template
            if x["name"] != "DevOps Kanban" and [p["id"] for p in x["projects"]] == [self.project["id"]]:
                self.api.delete(f"api/agiles/{x['id']}")
        b = next((x for x in boards if x["name"] == "DevOps Kanban"), None)
        if b:
            # columns are only defined at creation (existing columns are referenced by cards)
            for k in ("sprintsSettings", "colorCoding", "readSharingSettings"):
                self.api.post(f"api/agiles/{b['id']}", {k: body[k]})
        else:
            b = self.api.post("api/agiles", {k: body[k] for k in ("name", "projects", "columnSettings", "sprintsSettings")},
                              params={"fields": "id"})
            for k in ("colorCoding", "cardSettings", "readSharingSettings"):
                self.api.post(f"api/agiles/{b['id']}", {k: body[k]})
        self.board = b

    def all_users(self):
        g = next(g for g in self.api.get("api/groups", params={"fields": "id,allUsersGroup", "$top": 200}) if g.get("allUsersGroup"))
        return {"id": g["id"]}

    SAVED_QUERIES = [
        ("DevOps: Triage queue", "project: {k} State: New, Triage sort by: Priority, created"),
        ("DevOps: P1/P2 open", "project: {k} #Unresolved Priority: {{P1 Critical}}, {{P2 High}} sort by: Priority, created"),
        ("DevOps: Blocked", "project: {k} State: Blocked sort by: {{Blocked Since}} asc"),
        ("DevOps: Aging (over threshold)", "project: {k} #Unresolved tag: aging sort by: {{Requested On}} asc"),
        ("DevOps: In progress", "project: {k} State: {{In Progress}} sort by: Assignee"),
        ("DevOps: Recently completed", "project: {k} State: Done resolved date: {{minus 30d}} .. Today sort by: {{resolved date}} desc"),
        ("DevOps: My squad requests (Payments example)", "project: {k} {{Requester Squad}}: Payments sort by: updated desc"),
        ("DevOps: Unassigned accepted work", "project: {k} State: Accepted Assignee: Unassigned"),
        ("DevOps: My requests", "project: {k} reporter: me sort by: updated desc"),
    ]

    def saved_queries(self):
        log("Saved searches")
        everyone = self.all_users()
        existing = {q["name"]: q for q in self.api.get("api/savedQueries", params={"fields": "id,name", "$top": 500})}
        self.queries = {}
        for name, q in self.SAVED_QUERIES:
            body = {"name": name, "query": q.format(k=self.key),
                    "readSharingSettings": {"permittedGroups": [everyone]}}
            if name in existing:
                self.api.post(f"api/savedQueries/{existing[name]['id']}", body)
                self.queries[name] = existing[name]["id"]
            else:
                self.queries[name] = self.api.post("api/savedQueries", body, params={"fields": "id"})["id"]

    REPORTS = [
        # name, x field, y field (matrix) or None, query
        ("Open requests by Requester Squad", "Requester Squad", None, "#Unresolved"),
        ("Open requests by Service", "Service", None, "#Unresolved"),
        ("Open requests by Priority", "Priority", None, "#Unresolved"),
        ("Open requests by Aging", "Aging", None, "#Unresolved"),
        ("Open requests by State", "State", None, "#Unresolved"),
        ("DevOps workload by Assignee", "Assignee", None, "#Unresolved State: Accepted, {In Progress}, Blocked"),
        ("Demand by Squad and Service (all time)", "Requester Squad", "Service", ""),
        ("Requests by Squad and Type (last 90 days)", "Requester Squad", "Type", "created: {minus 90d} .. Today"),
    ]

    def reports(self):
        log("Reports")
        everyone = self.all_users()
        existing = {r["name"]: r for r in self.api.get("api/reports", params={"fields": "id,name", "$top": 500})}
        self.report_ids = {}
        for name, x, y, q in self.REPORTS:
            body = {
                "$type": "MatrixReport" if y else "FlatDistributionReport",
                "name": name, "projects": [{"id": self.project["id"]}], "query": q or None,
                "readSharingSettings": {"permittedGroups": [everyone]},
                "xsortOrder": "DISPLAY_NAME_ASC" if x in ("Priority", "Aging", "State") else "COUNT_INDEX_DESC",
                "presentation": "DEFAULT",
            }
            if y:
                body["ysortOrder"] = "COUNT_INDEX_DESC"
            axis = lambda f: {"field": {"$type": "CustomFilterField", "id": self.field_ids[f], "name": f}}  # noqa: E731
            if y:
                body["xaxis"], body["yaxis"] = axis(x), axis(y)
            else:
                body["xaxis"] = axis(x)
            if name in existing:
                self.api.post(f"api/reports/{existing[name]['id']}", body)
                self.report_ids[name] = existing[name]["id"]
            else:
                self.report_ids[name] = self.api.post("api/reports", body, params={"fields": "id"})["id"]

    def widget_ids(self):
        ws = self.api.get("api/admin/widgets/general", params={"fields": "id,key,appName", "$top": -1})
        return {w["key"]: w["id"] for w in ws}

    def dashboard(self):
        log("Management dashboard 'DevOps Demand - Management'")
        w = self.widget_ids()
        svc = self.api.get("api/config", params={"fields": "ring(serviceId)"})["ring"]["serviceId"]
        yt = {"id": svc, "homeUrl": self.public + "/"}

        def report(name):
            rtype = "MatrixReport" if next(r for r in self.REPORTS if r[0] == name)[2] else "FlatDistributionReport"
            return {"customWidgetConfig": json.dumps({
                "youTrack": yt, "refreshPeriod": 600,
                "report": {"id": self.report_ids[name], "$type": rtype, "name": name}})}

        def issues(title, query):
            return {"customWidgetConfig": json.dumps({"search": query, "title": title, "refreshPeriod": 240})}
        k = self.key
        # dashboard grid: 8 columns
        layout = [
            # widget key, x, y, w, h, settings
            ("devops-demand-kpis", 0, 0, 8, 4, {}),
            ("widget-youtrack-report", 0, 4, 4, 3, report("Open requests by Requester Squad")),
            ("widget-youtrack-report", 4, 4, 4, 3, report("Open requests by Service")),
            ("widget-youtrack-report", 0, 7, 4, 3, report("Open requests by Priority")),
            ("widget-youtrack-report", 4, 7, 4, 3, report("Open requests by Aging")),
            ("widget-youtrack-report", 0, 10, 4, 3, report("Open requests by State")),
            ("widget-youtrack-report", 4, 10, 4, 3, report("DevOps workload by Assignee")),
            ("youtrack-issues-list", 0, 13, 4, 3, issues("Highest priority open requests (P1/P2)",
                f"project: {k} #Unresolved Priority: {{P1 Critical}}, {{P2 High}} sort by: Priority, {{Requested On}} asc")),
            ("youtrack-issues-list", 4, 13, 4, 3, issues("Blocked requests", f"project: {k} State: Blocked sort by: {{Blocked Since}} asc")),
            ("youtrack-issues-list", 0, 16, 4, 3, issues("Currently in progress", f"project: {k} State: {{In Progress}} sort by: Assignee")),
            ("youtrack-issues-list", 4, 16, 4, 3, issues("Recently completed (30 days)",
                f"project: {k} State: Done resolved date: {{minus 30d}} .. Today sort by: {{resolved date}} desc")),
            ("widget-youtrack-report", 0, 19, 8, 4, report("Demand by Squad and Service (all time)")),
        ]
        widgets = []
        for i, (key, x, y, wd, h, settings) in enumerate(layout):
            widgets.append({"key": f"w{i}", "widget": {"id": w[key]}, "x": x, "y": y, "width": wd, "height": h,
                            "settings": json.dumps(settings)})
        body = {"name": "DevOps Demand - Management", "widgets": widgets,
                "readSharingSettings": {"permittedGroups": [self.all_users()]}}
        boards = self.api.get("api/dashboards", params={"fields": "id,name", "$top": 100})
        d = next((x for x in boards if x["name"] == body["name"]), None)
        if d:
            self.api.delete(f"api/dashboards/{d['id']}")
        d = self.api.post("api/dashboards", body, params={"fields": "id"})
        self.dashboard_id = d["id"]
        log(f"  dashboard: {self.public}/dashboard?id={d['id']}")

    # ------------------------------------------------------------------ request forms
    def intake_links(self):
        """Pre-filled 'new issue' links: the developer lands on the YouTrack create
        form with the Type set; the app inserts the matching template."""
        out = {}
        for t in TYPES:
            out[t] = f"{self.public}/newIssue?project={self.key}&c={_q('Type ' + t)}"
        return out

    def kb_article(self):
        log("Knowledge base article 'How to request DevOps help'")
        links = self.intake_links()
        content = open(os.path.join(ROOT, "youtrack", "request-guide.md")).read()
        for t, url in links.items():
            content = content.replace("{{" + t.upper() + "_LINK}}", url)
        content = content.replace("{{BASE}}", self.public).replace("{{KEY}}", self.key)
        content = content.replace("{{BOARD}}", f"{self.public}/agiles/{self.board['id']}/current")
        content = content.replace("{{DASHBOARD}}", f"{self.public}/dashboard?id={self.dashboard_id}")
        arts = self.api.get("api/articles", params={"fields": "id,summary,project(shortName)", "$top": 200})
        a = next((x for x in arts if x["summary"] == "How to request DevOps help"
                  and x.get("project", {}).get("shortName") == self.key), None)
        body = {"summary": "How to request DevOps help", "content": content, "project": {"id": self.project["id"]}}
        if a:
            self.api.post(f"api/articles/{a['id']}", body)
        else:
            a = self.api.post("api/articles", body, params={"fields": "id,idReadable"})
        self.article = self.api.get(f"api/articles/{a['id']}", params={"fields": "id,idReadable"})

    def backups(self):
        log("Scheduled database backups (daily 02:00, keep 7)")
        self.api.post("api/admin/databaseBackup/settings", {
            "isOn": True, "cronExpression": "0 0 2 * * ?", "filesToKeep": 7, "archiveFormat": "TAR_GZ"})

    # ------------------------------------------------------------------ run
    def run(self):
        self.wait_ready()
        self.authenticate()
        self.remove_demo_project()
        self.configure_email()
        self.users_and_groups()
        self.create_project()
        self.project_fields()
        self.team_and_roles()
        self.tags()
        self.install_app()
        self.agile_board()
        self.saved_queries()
        self.reports()
        self.dashboard()
        self.kb_article()
        self.backups()
        state = {"project": self.project, "board": self.board["id"], "dashboard": self.dashboard_id,
                 "app": self.app["id"], "fields": self.field_ids, "article": self.article["idReadable"]}
        with open(os.path.join(STATE_DIR, "youtrack.json"), "w") as f:
            json.dump(state, f, indent=2)
        log("YouTrack configuration complete")


def _q(s):
    import urllib.parse
    return urllib.parse.quote(s)


def load():
    yt = YouTrack()
    yt.authenticate()
    with open(os.path.join(STATE_DIR, "youtrack.json")) as f:
        st = json.load(f)
    yt.project = st["project"]
    yt.field_ids = st["fields"]
    yt.board = {"id": st["board"]}
    yt.dashboard_id = st["dashboard"]
    return yt
