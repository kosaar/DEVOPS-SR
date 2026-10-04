Need something from the DevOps team? **Use one of the three forms below. It takes less than 2 minutes.**

| I want to... | Form |
|---|---|
| ask for something new (pipeline, environment, access, tooling, capacity) | **[New Demand]({{DEMAND_LINK}})** |
| report something broken in a DevOps service (CI, runners, deployment, Git, cluster) | **[Report a Bug]({{BUG_LINK}})** |
| suggest how an existing DevOps service could be better | **[Suggest an Improvement]({{IMPROVEMENT_LINK}})** |

### How to fill in the form

1. **Summary** – one line, e.g. *"Nightly integration pipeline for payments-api"*.
2. **Requester Squad** – your squad (mandatory).
3. **Service** – CI, CD, Git, Kubernetes, Infrastructure, Developer Experience or Other (mandatory).
4. **Priority** – P3 Normal by default. P1/P2 immediately notify the DevOps lead: use them for production impact or a hard deadline.
5. **Description** – the form is pre-filled with the sections we need. Replace every line starting with `TODO:`.
   * Demand: *Description*, *Business / technical impact* and a **Target Date** field.
   * Bug: *Description*, *Expected behavior*, *Actual behavior*, *Evidence* and the **Environment** field. Attach logs/screenshots.
   * Improvement: *Description* and *Expected benefit*.
6. Click **Create**. If something is missing, YouTrack tells you exactly what.

### What happens next

| State | Meaning |
|---|---|
| Triage | Every new request lands here. DevOps reviews the triage queue daily. |
| Accepted | DevOps will do it. An assignee is set when work is planned. |
| Rejected | Not done – a comment explains why (duplicate, out of scope, self-service...). |
| In Progress | Being implemented. The GitLab issue / merge request / pipeline are linked on the request. |
| Blocked | Waiting on something. The *Blocked Reason* field says what. |
| Done | Delivered. The GitLab reference shows where. |

You are notified by e-mail on every state change and comment of the requests you created.

### Follow your requests

* [My requests]({{BASE}}/issues?q=project:%20{{KEY}}%20reporter:%20me)
* [DevOps Kanban board]({{BOARD}}) – what the team is working on right now
* [DevOps demand dashboard]({{DASHBOARD}}) – volume, priorities, blockers and aging

Questions about this process: ask the DevOps lead.
