"""Command lines for driving a remote machine over ssh with Docker. Pure functions.

Remote layout, relative to the remote user's home directory:
    <dir>/src/<commit>/        unpacked source, built into image commander-sim:<commit>
    <dir>/jobs/<job>/bundle/   the job bundle (job.yaml, decks/, manifest.json)
    <dir>/jobs/<job>/runs/     results (the job folder is mounted into the container as /work)
    <dir>/jobs/<job>/start.sh  starts or resumes the job; used by `remote run` and the watchdog
    <dir>/jobs/<job>/stopped   marker left by `remote stop`, so the watchdog leaves the job alone
    <dir>/watchdog.sh          run by cron: resumes jobs whose container stopped unfinished
"""

import shlex
from dataclasses import dataclass

DEFAULT_REMOTE_DIR = "commander-sim"
RESTART_ATTEMPTS = 5
STOP_GRACE_SECONDS = 60
WATCHDOG_MINUTES = 10
START_FILE = "start.sh"
STOPPED_MARKER = "stopped"
WATCHDOG_FILE = "watchdog.sh"
WATCHDOG_LOG = "watchdog.log"
MEMORY_GB_PER_WORKER = 2
_SSH_OPTIONS = ("-o", "BatchMode=yes", "-o", "ConnectTimeout=15")


@dataclass(frozen=True)
class Remote:
    destination: str  # anything `ssh` accepts: user@host or a ~/.ssh/config alias
    directory: str = DEFAULT_REMOTE_DIR

    @property
    def label(self) -> str:
        """Short host name for local folder names, e.g. 'pino' for user@pino.example.org."""
        return self.destination.rsplit("@", 1)[-1].split(".")[0]

    def path(self, *parts: str) -> str:
        """A remote path relative to the home directory, shell-quoted."""
        return shlex.quote("/".join((self.directory, *parts)))

    def absolute(self, *parts: str) -> str:
        """An absolute remote path (Docker volumes need one), for use inside a shell script."""
        return f'"$HOME"/{self.path(*parts)}'


def ssh(remote: Remote, script: str) -> list[str]:
    return ["ssh", *_SSH_OPTIONS, remote.destination, script]


def scp_to(remote: Remote, local: str, remote_path: str) -> list[str]:
    return ["scp", *_SSH_OPTIONS, "-q", "-r", local, f"{remote.destination}:{remote_path}"]


def scp_from(remote: Remote, remote_path: str, local: str) -> list[str]:
    return ["scp", *_SSH_OPTIONS, "-q", f"{remote.destination}:{remote_path}", local]


def image(commit: str) -> str:
    return f"commander-sim:{commit[:12]}"


def container(job: str) -> str:
    return f"commander-sim-{job}"


def _tool(remote: Remote, job: str, *args: str) -> str:
    """Run a one-off commander-sim command, in the image the job's container was started
    from, on the job's folder. Fails (exit 4) if the job has no container."""
    name = container(job)
    return (
        f"img=$(docker inspect -f '{{{{.Config.Image}}}}' {name} 2>/dev/null) || "
        f"{{ echo 'no container for job {job}' >&2; exit 4; }}; "
        f'docker run --rm --user "$(id -u):$(id -g)" -v {remote.absolute("jobs", job)}:/work '
        f'"$img" {" ".join(shlex.quote(a) for a in args)}'
    )


def prepare_source_script(remote: Remote) -> str:
    return f"mkdir -p {remote.path('src')}"


def prepare_job_script(remote: Remote, job: str) -> str:
    """Create the job folder and drop its previous bundle; results are kept."""
    return f"mkdir -p {remote.path('jobs', job)} && rm -rf {remote.path('jobs', job, 'bundle')}"


def build_script(remote: Remote, commit: str) -> str:
    """Unpack the uploaded source archive and build the image, unless it already exists."""
    source = remote.path("src", commit)
    archive = remote.path("src", f"{commit}.tar")
    return (
        "set -e; command -v docker >/dev/null || "
        "{ echo 'docker is not installed' >&2; exit 2; }; "
        f"if docker image inspect {image(commit)} >/dev/null 2>&1; then rm -f {archive}; "
        f"echo 'image {image(commit)} already built'; exit 0; fi; "
        f"mkdir -p {source}; tar -xf {archive} -C {source}; rm -f {archive}; "
        f"docker build -q -t {image(commit)} {source}"
    )


def has_image_script(commit: str) -> str:
    return f"docker image inspect {image(commit)} >/dev/null 2>&1"


def start_script(remote: Remote, commit: str, job: str, workers: int) -> str:
    """Start the job in a detached container, or resume it from its last checkpoint.

    A container that is still running is left alone (exit code 3). A stopped one is replaced:
    the run resumes from the tasks already saved in its database. Docker restarts the container
    by itself if the run crashes (non-zero exit), up to RESTART_ATTEMPTS times.
    """
    name = container(job)
    run = (
        f"docker run -d --init --name {name} --restart on-failure:{RESTART_ATTEMPTS} "
        f"--cpus {workers + 1} --memory {workers * MEMORY_GB_PER_WORKER}g "
        f'--user "$(id -u):$(id -g)" -v {remote.absolute("jobs", job)}:/work '
        f"{image(commit)} run /work/bundle/job.yaml --runs-dir /work/runs"
    )
    return (
        f'if [ "$(docker inspect -f {{{{.State.Running}}}} {name} 2>/dev/null)" = true ]; then '
        f"echo '{name} is already running' >&2; exit 3; fi; "
        f"docker rm {name} >/dev/null 2>&1; {run}\n"
    )


def launch_script(remote: Remote, job: str) -> str:
    """Clear a `remote stop` marker and run the job's uploaded start script."""
    return (
        f"rm -f {remote.path('jobs', job, STOPPED_MARKER)} && "
        f"sh {remote.path('jobs', job, START_FILE)}"
    )


def status_script(remote: Remote, job: str) -> str:
    """Container state with what it means, games done, and the last log lines."""
    name = container(job)
    database = f"/work/runs/{job}/results.sqlite"
    meaning = (
        f"state=$(docker inspect -f '{{{{.State.Status}}}} {{{{.State.ExitCode}}}}' {name} "
        "2>/dev/null) || state='none'; "
        'case "$state" in '
        "'running '*) echo 'running';; "
        "'exited 0') echo 'finished';; "
        f"'exited 130') if [ -f {remote.path('jobs', job, STOPPED_MARKER)} ]; then "
        "echo 'stopped with remote stop; remote run resumes it'; else "
        "echo 'stopped by someone else; the watchdog or remote run resumes it'; fi;; "
        "none) echo 'no container for this job';; "
        '*) echo "stopped unexpectedly ($state); remote run resumes it from the saved games";; '
        "esac; "
    )
    return (
        meaning
        + f"docker inspect -f 'restarts: {{{{.RestartCount}}}}, started {{{{.State.StartedAt}}}}' "
        f"{name} 2>/dev/null; "
        f"if [ -f {remote.path('jobs', job, 'runs', job, 'results.sqlite')} ]; then "
        f"{_tool(remote, job, 'progress', database)}; else echo 'no results yet'; fi; "
        f"docker logs --tail 3 {name} 2>&1 | tail -3; "
        f"grep -s ' {job} ' {remote.path(WATCHDOG_LOG)} | tail -2"
    )


def stop_script(remote: Remote, job: str) -> str:
    """Mark the job as deliberately stopped, then SIGTERM it (the run treats it like Ctrl+C:
    finished games stay saved)."""
    return (
        f"touch {remote.path('jobs', job, STOPPED_MARKER)} && "
        f"docker stop -t {STOP_GRACE_SECONDS} {container(job)}"
    )


def snapshot_script(remote: Remote, job: str) -> str:
    return _tool(
        remote,
        job,
        "snapshot",
        f"/work/runs/{job}/results.sqlite",
        "/work/fetch/results.sqlite",
    )


def watchdog_script(remote: Remote) -> str:
    """Resume every job whose container is gone or stopped before finishing.

    Skipped: running or restarting containers, finished ones (exit code 0) and jobs stopped
    with `remote stop`. Run from cron in the remote home directory.
    """
    jobs = remote.path("jobs")
    return f"""#!/bin/sh
# commander-sim watchdog: resumes runs whose container stopped before finishing.
for start in {jobs}/*/{START_FILE}; do
  [ -f "$start" ] || continue
  dir=$(dirname "$start"); job=$(basename "$dir")
  [ -f "$dir/{STOPPED_MARKER}" ] && continue
  state=$(docker inspect -f '{{{{.State.Status}}}} {{{{.State.ExitCode}}}}' "commander-sim-$job" \
    2>/dev/null) || state=missing
  case "$state" in
    running*|restarting*|"exited 0") continue;;
  esac
  echo "$(date -Is) $job was '$state', resuming"
  sh "$start"
done
"""


def _crontab_without_watchdog() -> str:
    return f"crontab -l 2>/dev/null | grep -v '{WATCHDOG_FILE}'"


def install_watchdog_script(remote: Remote) -> str:
    """Write the watchdog and add (or replace) its cron entry, leaving other entries alone."""
    entry = (
        f'*/{WATCHDOG_MINUTES} * * * * cd "$HOME" && sh {remote.path(WATCHDOG_FILE)} '
        f">> {remote.path(WATCHDOG_LOG)} 2>&1"
    )
    return (
        "set -e; command -v crontab >/dev/null || "
        "{ echo 'crontab is not available' >&2; exit 2; }; "
        f"mkdir -p {remote.path()}; cat > {remote.path(WATCHDOG_FILE)} <<'WATCHDOG'\n"
        f"{watchdog_script(remote)}WATCHDOG\n"
        f"({_crontab_without_watchdog()}; echo {shlex.quote(entry)}) | crontab -; "
        "crontab -l | grep commander-sim"
    )


def remove_watchdog_script(remote: Remote) -> str:
    return f"({_crontab_without_watchdog()}) | crontab -; rm -f {remote.path(WATCHDOG_FILE)}"
