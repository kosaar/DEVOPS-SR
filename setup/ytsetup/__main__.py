"""Entry point:  python -m setup.ytsetup <command>

Commands
  youtrack   configure YouTrack (users, project, fields, app, board, reports, dashboard)
  gitlab     configure GitLab (group/project, runner, YouTrack integrations, CI variables)
  seed       load the demo requests into YouTrack
  lifecycle  run the end-to-end demo: request -> triage -> GitLab issue/branch/MR/pipeline -> Done
  verify     check that everything is in place (acceptance checks)
  all        youtrack + gitlab + seed + lifecycle + verify
"""
import sys

from .config import log


def main(argv):
    cmd = argv[0] if argv else "all"
    steps = ["youtrack", "gitlab", "seed", "lifecycle", "verify"] if cmd == "all" else [cmd]
    for step in steps:
        log(f"===== {step} =====")
        if step == "youtrack":
            from .youtrack import YouTrack
            YouTrack().run()
        elif step == "gitlab":
            from .gitlab import run
            run()
        elif step == "seed":
            from .seed import run
            run()
        elif step == "lifecycle":
            from .lifecycle import run
            run()
        elif step == "verify":
            from .verify import run
            if not run():
                sys.exit(1)
        else:
            print(__doc__)
            sys.exit(2)


if __name__ == "__main__":
    main(sys.argv[1:])
