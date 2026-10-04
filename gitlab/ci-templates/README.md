# platform/ci-templates

Reusable GitLab CI templates maintained by the DevOps team, plus the
**template catalog** web page (deployed to the `demo` environment by this pipeline).

Every change is linked to a DevOps request in YouTrack: put the request ID
(e.g. `DEVOPS-12`) in the branch name, commit message and merge request title.
The `youtrack-sync` job then writes the pipeline/MR references back to the request.
