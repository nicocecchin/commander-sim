"""Command lines for driving a remote machine over ssh with Docker. Pure functions.

Remote layout, relative to the remote user's home directory:
    <dir>/src/<commit>/        unpacked source, built into image commander-sim:<commit>
    <dir>/jobs/<job>/bundle/   the job bundle (job.yaml, decks/, manifest.json)
    <dir>/jobs/<job>/runs/     results, mounted into the container as /work
"""

import shlex
from dataclasses import dataclass

DEFAULT_REMOTE_DIR = "commander-sim"
RESTART_ATTEMPTS = 5
STOP_GRACE_SECONDS = 60
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
        f"docker run -d --name {name} --restart on-failure:{RESTART_ATTEMPTS} "
        f"--cpus {workers + 1} --memory {workers * MEMORY_GB_PER_WORKER}g "
        f'--user "$(id -u):$(id -g)" -v {remote.absolute("jobs", job)}:/work '
        f"{image(commit)} run /work/bundle/job.yaml --runs-dir /work/runs"
    )
    return (
        f'if [ "$(docker inspect -f {{{{.State.Running}}}} {name} 2>/dev/null)" = true ]; then '
        f"echo '{name} is already running' >&2; exit 3; fi; "
        f"docker rm {name} >/dev/null 2>&1; {run}"
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
        "'exited 130') echo 'stopped cleanly; remote run resumes it';; "
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
        f"docker logs --tail 3 {name} 2>&1 | tail -3"
    )


def stop_script(job: str) -> str:
    """SIGTERM, which the run treats like Ctrl+C: finished games stay saved."""
    return f"docker stop -t {STOP_GRACE_SECONDS} {container(job)}"


def snapshot_script(remote: Remote, job: str) -> str:
    return _tool(
        remote,
        job,
        "snapshot",
        f"/work/runs/{job}/results.sqlite",
        "/work/fetch/results.sqlite",
    )
