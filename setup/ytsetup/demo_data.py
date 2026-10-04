"""Demo requests for the DEVOPS project (58 requests, 10 squads).

Columns: type, squad, service, priority, state, age_days, assignee, summary, details
  details: dict with optional keys
    what / impact / benefit / expected / actual / evidence   -> description sections
    env           -> Environment (bugs)
    target        -> Target Date in days from today (negative = overdue)
    blocked       -> (reason, blocked_days)
    gitlab        -> (GitLab project, issue/MR reference, pipeline reference)
    no_code       -> True: tag no-code-change
    rejected_why  -> comment explaining a rejection
"""

D, B, I = "Demand", "Bug", "Improvement"
P1, P2, P3, P4 = "P1 Critical", "P2 High", "P3 Normal", "P4 Low"
LEAD, ALEX, SAM, LEE = "devops.lead", "alex.ops", "sam.platform", "lee.cicd"
GL = "platform/ci-templates"

REQUESTS = [
    # ---------------------------------------------------------------- Payments (9)
    (D, "Payments", "CD", P1, "In Progress", 4, ALEX, "Blue/green deployment for payments-api before PCI audit",
     dict(what="Zero-downtime blue/green deployment for payments-api on the prod cluster.",
          impact="PCI auditor visit in 3 weeks requires documented zero-downtime releases.", target=18,
          gitlab=("platform/deploy-templates", "platform/deploy-templates#14", ""))),
    (B, "Payments", "CI", P2, "Done", 12, LEE, "Integration tests job times out on shared runners",
     dict(env="Test", expected="Integration test stage completes in < 15 min.",
          actual="Job killed after 60 min: 'ERROR: Job failed: execution took longer than 1h0m0s'.",
          evidence="Pipeline #48211, job integration-tests (log attached).",
          gitlab=(GL, f"{GL}!7", "http://localhost:8929/platform/ci-templates/-/pipelines/31"))),
    (D, "Payments", "Infrastructure", P2, "Accepted", 9, SAM, "Dedicated Redis for payments session store",
     dict(what="Managed Redis instance (HA) for the payments session store.", impact="Shared Redis evictions cause checkout logouts.", target=25)),
    (I, "Payments", "CI", P3, "Triage", 2, None, "Cache Maven dependencies across pipeline stages",
     dict(what="Reuse ~/.m2 between build and test stages.", benefit="~6 min saved per pipeline, ~40 pipelines/day.")),
    (D, "Payments", "Kubernetes", P3, "Blocked", 21, SAM, "Network policy for payments namespace",
     dict(what="Default-deny network policy + explicit egress to PSP endpoints.", impact="Security finding SEC-2291 must be closed this quarter.",
          target=10, blocked=("Waiting for Security squad to validate the PSP egress IP list", 8))),
    (B, "Payments", "CD", P1, "Done", 6, ALEX, "Rollback failed for payments-api release 4.12",
     dict(env="Production", expected="helm rollback restores 4.11 within 5 minutes.", actual="Rollback hung on pending PVC resize; 22 min outage.",
          evidence="Incident INC-0912 timeline, deploy job #7781 log.",
          gitlab=("platform/deploy-templates", "platform/deploy-templates!22", "http://localhost:8929/platform/deploy-templates/-/pipelines/12"))),
    (D, "Payments", "Git", P4, "Done", 40, LEE, "Protected branch rules for payments-* repositories",
     dict(what="Require 2 approvals + green pipeline on main for all payments-* repos.", impact="Audit requirement (4-eyes principle).", target=-10,
          gitlab=("platform/gitlab-config", "platform/gitlab-config!3", ""))),
    (I, "Payments", "Developer Experience", P3, "Accepted", 33, LEE, "Self-service preview environments per merge request",
     dict(what="Spin up an ephemeral environment for each MR.", benefit="QA can test features before merge; fewer staging conflicts.")),
    (D, "Payments", "CI", P2, "Triage", 1, None, "SAST scanning in payments pipelines",
     dict(what="Add SAST + dependency scanning to the payments pipeline template.", impact="Required by the new secure-SDLC policy from next month.", target=30)),

    # ---------------------------------------------------------------- Customer Portal (7)
    (B, "Customer Portal", "CD", P2, "In Progress", 3, ALEX, "Static assets not invalidated in CDN after deploy",
     dict(env="Production", expected="New JS bundle served right after deploy.", actual="Users get stale bundle for up to 2 h; white screen on login.",
          evidence="Screenshots + CDN response headers attached.", gitlab=(GL, f"{GL}#4", ""))),
    (D, "Customer Portal", "Kubernetes", P3, "Triage", 5, None, "HPA for portal-frontend based on request rate",
     dict(what="Autoscale portal-frontend on requests/s instead of CPU.", impact="Marketing campaign on the 15th: expect 5x traffic.", target=14)),
    (I, "Customer Portal", "CI", P4, "Rejected", 50, LEE, "Run Lighthouse audit on every commit",
     dict(what="Lighthouse report on every push.", benefit="Catch performance regressions early.",
          rejected_why="Rejected: too costly on every push. Use the nightly Lighthouse job template (ci-templates/lighthouse.yml) instead.")),
    (D, "Customer Portal", "Git", P3, "Done", 15, LEE, "Migrate portal repositories to the new GitLab group",
     dict(what="Move 6 repos from legacy group to customer-portal/.", impact="Ownership and CODEOWNERS cleanup.", target=-2,
          gitlab=("platform/gitlab-config", "platform/gitlab-config!5", ""))),
    (B, "Customer Portal", "CI", P3, "Accepted", 18, LEE, "Flaky e2e stage: Chrome crashes in docker executor",
     dict(env="Test", expected="e2e stage stable.", actual="~15% of runs fail with 'session deleted because of page crash'.",
          evidence="Last 20 pipelines, 3 failed (links in comment).")),
    (D, "Customer Portal", "Infrastructure", P2, "Blocked", 26, SAM, "WAF rules for the new customer login page",
     dict(what="WAF rules + rate limiting for /login and /password-reset.", impact="Credential stuffing attempts seen last week.", target=5,
          blocked=("Waiting for network team firewall change FW-1182", 12))),
    (I, "Customer Portal", "Developer Experience", P4, "Triage", 64, None, "Document how to debug pods in the portal namespace",
     dict(what="Runbook: kubectl access, logs, port-forward for portal devs.", benefit="Fewer ad-hoc DevOps interruptions (3-4/week).")),

    # ---------------------------------------------------------------- Mobile (6)
    (D, "Mobile", "CI", P2, "In Progress", 11, LEE, "macOS runners for iOS builds",
     dict(what="2 macOS runners registered to the mobile group.", impact="iOS builds are done manually on a laptop; release delays.", target=7,
          gitlab=(GL, f"{GL}#5", ""))),
    (B, "Mobile", "CD", P3, "Done", 20, ALEX, "Android signing key not available in release job",
     dict(env="Production", expected="Release job signs the AAB.", actual="'Keystore file not found' in release stage.",
          evidence="Job #6650 log.", gitlab=(GL, f"{GL}!9", "http://localhost:8929/platform/ci-templates/-/pipelines/18"))),
    (I, "Mobile", "CI", P3, "Triage", 7, None, "Parallelize unit tests for the Android app",
     dict(what="Split Gradle test task across 4 parallel jobs.", benefit="Pipeline from 28 to ~10 minutes.")),
    (D, "Mobile", "Infrastructure", P4, "Accepted", 75, SAM, "Device farm access from CI",
     dict(what="Network route from runners to the on-prem device farm.", impact="Manual device testing before each release (1 day).")),
    (B, "Mobile", "Git", P3, "Triage", 3, None, "Git LFS quota exceeded on mobile-assets repo",
     dict(env="Development", expected="Push of design assets succeeds.", actual="'LFS objects are missing' / quota exceeded on push.",
          evidence="Error output pasted in comment.")),
    (D, "Mobile", "CD", P2, "Blocked", 30, ALEX, "Automated upload to app stores from pipeline",
     dict(what="fastlane-based upload to TestFlight and Play Console.", impact="Manual store upload takes 2 h per release.", target=-3,
          blocked=("Waiting for Apple developer account API key from Mobile product owner", 16))),

    # ---------------------------------------------------------------- Data (7)
    (D, "Data", "Kubernetes", P2, "In Progress", 8, SAM, "Spark operator on the analytics cluster",
     dict(what="Install and configure the Spark operator.", impact="Nightly jobs run on a single VM that is out of memory.", target=12,
          gitlab=("platform/k8s-addons", "platform/k8s-addons!11", ""))),
    (B, "Data", "Infrastructure", P1, "Done", 2, SAM, "Airflow scheduler pod OOMKilled every night",
     dict(env="Production", expected="Scheduler stable.", actual="OOMKilled at 02:10 daily; DAGs miss SLA.",
          evidence="kubectl describe + Grafana memory panel attached.", gitlab=("platform/k8s-addons", "platform/k8s-addons!12", ""))),
    (D, "Data", "Infrastructure", P3, "Accepted", 45, SAM, "Object storage bucket for data lake raw zone",
     dict(what="S3-compatible bucket with lifecycle rules (90 d).", impact="Raw zone currently on NFS; 85% full.", target=20)),
    (I, "Data", "CI", P3, "Done", 35, LEE, "dbt model tests in merge request pipelines",
     dict(what="Run dbt test on changed models in MRs.", benefit="Broken models caught before deploy.",
          gitlab=(GL, f"{GL}!6", "http://localhost:8929/platform/ci-templates/-/pipelines/9"))),
    (D, "Data", "CD", P3, "Triage", 12, None, "Promote Airflow DAGs dev -> prod via pipeline",
     dict(what="Git-based promotion of DAGs with approval gate.", impact="Manual copy to prod causes drift.", target=40)),
    (B, "Data", "Kubernetes", P2, "Blocked", 19, SAM, "PVC stuck in Terminating for kafka-connect",
     dict(env="Staging", expected="PVC released after pod deletion.", actual="PVC stuck Terminating for 3 days; connector cannot restart.",
          evidence="kubectl get pvc output.", blocked=("Waiting for storage vendor support case #55871", 6))),
    (I, "Data", "Developer Experience", P4, "Triage", 90, None, "Template repository for new data pipelines",
     dict(what="Cookiecutter-style template with CI pre-configured.", benefit="New pipeline set up in 10 min instead of 1 day.")),

    # ---------------------------------------------------------------- CRM (4)
    (D, "CRM", "Git", P3, "Done", 28, LEE, "GitLab group and access for the new CRM squad",
     dict(what="Group crm/, 6 developer accounts, maintainers.", impact="New squad onboarding next Monday.", target=-20, no_code=True)),
    (B, "CRM", "CD", P3, "Accepted", 14, ALEX, "Deploy job fails when release notes contain quotes",
     dict(env="Staging", expected="Deploy succeeds.", actual="YAML parse error in helm values when notes contain \".",
          evidence="Job #7003.")),
    (I, "CRM", "CI", P4, "Triage", 4, None, "Slack notification on failed pipelines for main",
     dict(what="Notify #crm-dev on failed main pipelines.", benefit="Faster reaction to broken main.")),
    (D, "CRM", "Infrastructure", P2, "Triage", 1, None, "Outbound SMTP relay for CRM campaign service",
     dict(what="Authenticated SMTP relay with SPF/DKIM.", impact="Campaign go-live date in 2 weeks.", target=14)),

    # ---------------------------------------------------------------- Analytics (5)
    (D, "Analytics", "Kubernetes", P3, "In Progress", 16, SAM, "GPU node pool for model training",
     dict(what="2 GPU nodes with taints/tolerations for training jobs.", impact="Training runs on CPU take 18 h.", target=21,
          gitlab=("platform/k8s-addons", "platform/k8s-addons#7", ""))),
    (B, "Analytics", "CI", P3, "Done", 9, LEE, "Docker build cache not used for Python images",
     dict(env="Development", expected="Cached layers reused.", actual="Full rebuild every time (12 min).", evidence="Build logs.",
          gitlab=(GL, f"{GL}!8", "http://localhost:8929/platform/ci-templates/-/pipelines/15"))),
    (D, "Analytics", "Other", P4, "Rejected", 22, LEAD, "Buy a BI tool licence for the team",
     dict(what="Licence for a commercial BI tool.", impact="Dashboards for product team.",
          rejected_why="Rejected: licence procurement is handled by IT procurement, not DevOps. Please raise it via the procurement process.")),
    (I, "Analytics", "Developer Experience", P3, "Accepted", 68, LEE, "JupyterHub with access to the data lake",
     dict(what="Shared JupyterHub with SSO and read-only lake access.", benefit="Analysts stop copying data to laptops (GDPR risk).")),
    (D, "Analytics", "CD", P3, "Triage", 47, None, "Scheduled refresh deployment for dashboards",
     dict(what="Nightly redeploy of dashboard service with refreshed cache.", impact="Stale numbers in Monday management review.", target=30)),

    # ---------------------------------------------------------------- Security (5)
    (D, "Security", "CI", P1, "In Progress", 1, LEE, "Rotate CI secrets after token leak",
     dict(what="Rotate all CI/CD variables of group payments/ and customer-portal/.", impact="A deploy token was exposed in a public gist.", target=1,
          gitlab=(GL, f"{GL}#6", ""))),
    (D, "Security", "Git", P2, "Done", 17, LEE, "Enforce signed commits on protected branches",
     dict(what="Push rule: reject unsigned commits on main.", impact="Supply-chain hardening objective Q4.", target=-5,
          gitlab=("platform/gitlab-config", "platform/gitlab-config!7", ""))),
    (I, "Security", "CI", P2, "Accepted", 23, LEE, "Container image scanning in the shared pipeline template",
     dict(what="Trivy scan stage in ci-templates.", benefit="Known CVEs blocked before deployment.")),
    (B, "Security", "Kubernetes", P3, "Triage", 6, None, "Pods running as root in 3 namespaces",
     dict(env="Production", expected="All workloads run as non-root (policy).", actual="Policy in audit mode only; 14 pods as root.",
          evidence="Policy report attached.")),
    (D, "Security", "Infrastructure", P3, "Blocked", 58, SAM, "Centralized audit logging for bastion hosts",
     dict(what="Ship bastion auditd logs to the SIEM.", impact="Audit finding A-77.", target=-8,
          blocked=("Waiting for SIEM licence capacity upgrade (procurement)", 25))),

    # ---------------------------------------------------------------- Internal Tools (4)
    (I, "Internal Tools", "Developer Experience", P4, "Done", 31, LEE, "Self-service runner registration docs",
     dict(what="Docs + script to register project runners.", benefit="No DevOps ticket needed for runners.", no_code=True)),
    (D, "Internal Tools", "CD", P3, "Accepted", 52, ALEX, "Deployment pipeline for the internal wiki",
     dict(what="CI/CD for wiki container with staging + prod.", impact="Manual updates via SSH today.", target=15)),
    (B, "Internal Tools", "Git", P4, "Triage", 105, None, "Repository mirror to backup site stopped syncing",
     dict(env="Production", expected="Mirror updated hourly.", actual="Last sync 3 weeks ago, no error in UI.", evidence="Mirror settings screenshot.")),
    (D, "Internal Tools", "Kubernetes", P3, "In Progress", 37, SAM, "Namespace and quota for the new ticket-bot",
     dict(what="Namespace, quota, service account and deploy token.", impact="Bot launch for support team.", target=-4,
          gitlab=("platform/k8s-addons", "platform/k8s-addons#9", ""))),

    # ---------------------------------------------------------------- Commerce (6)
    (D, "Commerce", "CD", P2, "In Progress", 13, ALEX, "Canary releases for checkout-service",
     dict(what="10% canary with automatic rollback on error rate.", impact="Black Friday freeze starts in 5 weeks.", target=20,
          gitlab=("platform/deploy-templates", "platform/deploy-templates!25", ""))),
    (B, "Commerce", "Infrastructure", P1, "Triage", 0, None, "Checkout latency spikes after load balancer change",
     dict(env="Production", expected="p95 < 300 ms.", actual="p95 2.5 s since LB config change yesterday 18:00.",
          evidence="Grafana dashboard link + LB change ID CHG-3301.")),
    (D, "Commerce", "Kubernetes", P3, "Accepted", 27, SAM, "Separate node pool for search indexing",
     dict(what="Dedicated nodes for Elasticsearch indexing jobs.", impact="Indexing slows down the shop at night.", target=35)),
    (I, "Commerce", "CI", P3, "Done", 19, LEE, "Reusable pipeline template for Node.js services",
     dict(what="Shared .gitlab-ci template (lint, test, build, scan).", benefit="8 services, ~200 lines of duplicated YAML removed.",
          gitlab=(GL, f"{GL}!4", "http://localhost:8929/platform/ci-templates/-/pipelines/6"))),
    (D, "Commerce", "Infrastructure", P3, "Triage", 15, None, "Staging environment refresh with anonymized prod data",
     dict(what="Monthly refresh of staging DB with anonymized prod snapshot.", impact="Bugs not reproducible on stale staging data.", target=30)),
    (B, "Commerce", "CD", P3, "Rejected", 11, ALEX, "Deploy button greyed out in GitLab environment page",
     dict(env="Staging", expected="Manual deploy available.", actual="Button disabled.", evidence="Screenshot.",
          rejected_why="Not a bug: the environment is protected; only Maintainers of commerce/ can deploy. Ask your squad maintainer.")),

    # ---------------------------------------------------------------- Operations (5)
    (D, "Operations", "Infrastructure", P2, "Done", 5, SAM, "Backup policy for GitLab and YouTrack servers",
     dict(what="Nightly backup + weekly restore test for GitLab and YouTrack.", impact="No tested restore today.", target=-1,
          gitlab=("platform/ops-automation", "platform/ops-automation!2", ""))),
    (I, "Operations", "Developer Experience", P3, "Done", 8, ALEX, "On-call runbook links in alert messages",
     dict(what="Add runbook URL annotation to all alerts.", benefit="Faster incident response.",
          gitlab=("platform/ops-automation", "platform/ops-automation!3", ""))),
    (D, "Operations", "Kubernetes", P3, "Triage", 85, None, "Cluster upgrade to the next Kubernetes minor version",
     dict(what="Upgrade dev/staging/prod clusters.", impact="Current version end-of-support in 4 months.", target=60)),
    (B, "Operations", "CI", P4, "Accepted", 41, LEE, "Runner disk fills up with old docker images",
     dict(env="Development", expected="Runners clean up images automatically.", actual="Weekly manual docker system prune.",
          evidence="df -h output.")),
    (I, "Operations", "Other", P4, "Done", 3, LEAD, "Monthly DevOps demand review with squad leads",
     dict(what="Use the YouTrack demand dashboard in a monthly review.", benefit="Shared view of priorities and blockers.", no_code=True)),
]
