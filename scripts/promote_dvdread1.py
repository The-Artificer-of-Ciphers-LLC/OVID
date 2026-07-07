#!/usr/bin/env python3
"""D-04/D-05 one-command dvdread1-* promotion cutover wrapper.

Performs, as a single operator action:

    toggle read-only -> `alembic upgrade head` -> toggle read-write

by reusing the existing, already-tested ``MirrorModeMiddleware`` read-only
gate (see ``api/app/middleware.py``) — this script adds ZERO new
middleware code. ``MirrorModeMiddleware`` is wired conditionally at
process-import time in ``api/main.py``::

    if os.environ.get("OVID_MODE") == "mirror":
        app.add_middleware(MirrorModeMiddleware)

so the toggle requires **restarting** the ``api`` service (recreating the
container with a new ``OVID_MODE`` value), not merely exporting an
environment variable on the host — an in-process env var change has zero
effect on an already-running gunicorn worker.

IMPORTANT — this also interrupts READS, not just writes. Each of the two
service restarts this script performs briefly drops the API entirely
(both read and write traffic) while the ``api`` container recreates, on
top of write-only "mirror mode" 405s once it's back up. Do not run this
expecting a write-only quiesce with zero read impact.

The wrapper NEVER defaults to a specific compose file — you MUST name
every compose file your deployment actually uses via a repeatable
``--compose-file``/``-f`` flag (mirroring ``docker compose -f``
semantics), e.g.::

    python scripts/promote_dvdread1.py -f docker-compose.yml
    python scripts/promote_dvdread1.py -f docker-compose.yml -f docker-compose.prod.yml

It captures the CURRENT ``OVID_MODE`` value before flipping to
``mirror`` and restores that captured value (never a hardcoded default)
in a ``finally`` block — regardless of whether the migration succeeds or
fails — so a canonical-mode operator's restore step can never silently
leave the server on the wrong mode, and a failed migration never strands
the deployment in read-only mode. If the capture itself fails, the
script aborts loudly BEFORE anything has changed (see
``_current_ovid_mode``); if the restore step itself fails, the script
prints an explicit operator recovery message and exits non-zero rather
than leaving the failure to a bare traceback.

Run from the repo root, on the host that runs `docker compose` for the
target deployment (this script is never invoked by the API itself):

    python scripts/promote_dvdread1.py -f docker-compose.yml
"""

import argparse
import os
import subprocess
import sys

def _current_ovid_mode(compose_args: list[str]) -> str:
    """Capture the OVID_MODE the running api service currently reports.

    Raises ``RuntimeError`` if the container isn't reachable, the
    `printenv` call fails, or it returns empty output — this capture runs
    BEFORE any change is made, so aborting here (rather than silently
    falling back to a hardcoded default) leaves the deployment completely
    untouched. A silent fallback would be actively dangerous: on a MIRROR
    deployment, a transient capture failure defaulting to "standalone"
    would cause the `finally` restore step to flip a read-only mirror
    into read-write standalone, producing divergent, un-syncable writes.
    """
    try:
        result = subprocess.run(
            ["docker", "compose", *compose_args, "exec", "api", "printenv", "OVID_MODE"],
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise RuntimeError(
            "Failed to capture the current OVID_MODE (docker compose exec "
            "could not run). Verify the deployment is reachable via the "
            "given --compose-file(s) and retry — no changes have been "
            f"made. Underlying error: {exc}"
        ) from exc
    if result.returncode != 0:
        raise RuntimeError(
            "Failed to capture the current OVID_MODE (docker compose exec "
            f"exited with code {result.returncode}). Verify the deployment "
            "is reachable via the given --compose-file(s) and retry — no "
            "changes have been made."
        )
    mode = result.stdout.strip()
    if not mode:
        raise RuntimeError(
            "Failed to capture the current OVID_MODE (empty output from "
            "printenv OVID_MODE). Verify the deployment is reachable via "
            "the given --compose-file(s) and retry — no changes have been "
            "made."
        )
    return mode


def _set_ovid_mode_and_restart(compose_args: list[str], mode: str) -> None:
    """Recreate the api service with OVID_MODE=<mode>.

    MirrorModeMiddleware is wired conditionally at process-import time
    (api/main.py), never evaluated per-request — so taking effect
    requires recreating the api container, not just setting an env var.
    """
    env = {**os.environ, "OVID_MODE": mode}
    subprocess.run(
        ["docker", "compose", *compose_args, "up", "-d", "--no-deps", "api"],
        env=env,
        check=True,
    )


def _run_migration(compose_args: list[str]) -> None:
    """Run the promotion migration inside the (now read-only) api container."""
    subprocess.run(
        ["docker", "compose", *compose_args, "exec", "api", "alembic", "upgrade", "head"],
        check=True,
    )


def _confirm(prompt: str) -> bool:
    answer = input(prompt)
    return answer.strip().lower() in ("y", "yes")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "D-04/D-05 one-command dvdread1-* promotion cutover: toggle "
            "read-only -> alembic upgrade head -> restore the prior "
            "read-write state. This also briefly interrupts reads, not "
            "just writes, during each of the two api service restarts."
        )
    )
    parser.add_argument(
        "--compose-file",
        "-f",
        dest="compose_files",
        action="append",
        required=True,
        help=(
            "Compose file to pass to `docker compose -f`. Repeatable, "
            "mirroring docker compose's own -f semantics — e.g. "
            "-f docker-compose.yml -f docker-compose.prod.yml. There is "
            "NO default; you must name every compose file your "
            "deployment actually uses so this can never silently target "
            "the wrong deployment."
        ),
    )
    args = parser.parse_args(argv)

    compose_args: list[str] = []
    for compose_file in args.compose_files:
        compose_args += ["-f", compose_file]

    original_mode = _current_ovid_mode(compose_args)
    print(f"Captured current OVID_MODE={original_mode!r} for restore.")
    print(f"Target compose files: {' '.join(args.compose_files)}")
    print(
        "This performs TWO api service restarts (toggle read-only, then "
        "restore) — reads are briefly interrupted too, not just writes, "
        "during each restart."
    )
    if not _confirm("Proceed? [y/N] "):
        print("Aborted — no changes made.")
        return 1

    migration_failed = False
    try:
        _set_ovid_mode_and_restart(compose_args, "mirror")
        _run_migration(compose_args)
    except subprocess.CalledProcessError as exc:
        migration_failed = True
        print(f"ERROR: cutover step failed: {exc}", file=sys.stderr)
    finally:
        try:
            _set_ovid_mode_and_restart(compose_args, original_mode)
            print(f"Restored OVID_MODE={original_mode!r}.")
        except subprocess.CalledProcessError as exc:
            manual_cmd = (
                "OVID_MODE="
                + original_mode
                + " docker compose "
                + " ".join(compose_args)
                + " up -d --no-deps api"
            )
            print(
                "CRITICAL: failed to restore "
                f"OVID_MODE={original_mode!r}; the deployment may be "
                f"stranded read-only. Underlying error: {exc}\n"
                "Manually run the following command to restore it:\n"
                f"    {manual_cmd}",
                file=sys.stderr,
            )
            raise

    if migration_failed:
        print(
            "Migration failed, but OVID_MODE has been restored to its "
            "original captured value above — the deployment is NOT "
            "stranded read-only. Investigate the alembic error before "
            "retrying; re-running this script is safe (the promotion "
            "migration is per-disc idempotent, D-01).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
