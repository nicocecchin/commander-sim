"""`commander-sim remote ...`: run jobs on another machine over ssh, inside Docker."""

import subprocess
import tempfile
from pathlib import Path

import typer

from commander_sim.config import load_job
from commander_sim.decks.playgroup import DEFAULT_PLAYGROUP_FILE, load_owners
from commander_sim.remote import commands
from commander_sim.remote.bundle import BundleError, write_bundle
from commander_sim.remote.commands import Remote
from commander_sim.remote.source import SourceError, clean_head_commit, write_source_archive
from commander_sim.report.render import write_report
from commander_sim.storage.load import load_databases

remote_app = typer.Typer(
    no_args_is_help=True,
    help="Run jobs on another machine over ssh (the remote needs Docker and a POSIX shell).",
)
watchdog_app = typer.Typer(
    no_args_is_help=True,
    help="A cron job on the remote that resumes runs stopped before finishing.",
)
remote_app.add_typer(watchdog_app, name="watchdog")

HOST_OPTION = typer.Option(
    ..., envvar="COMMANDER_SIM_HOST", help="ssh destination, e.g. user@runbox or a ssh alias."
)
DIR_OPTION = typer.Option(commands.DEFAULT_REMOTE_DIR, help="Folder under the remote home.")
DEFAULT_WORKERS = 8


def _execute(command: list[str], echo: bool = True) -> str:
    """Run a local ssh/scp command; print and return its output, or exit with its error."""
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    output = completed.stdout.strip()
    if echo and output:
        typer.echo(output)
    if completed.returncode != 0:
        typer.secho(completed.stderr.strip() or f"{command[0]} failed", fg=typer.colors.RED)
        raise typer.Exit(completed.returncode)
    return output


def _succeeds(command: list[str]) -> bool:
    return subprocess.run(command, capture_output=True, check=False).returncode == 0


def _ensure_image(remote: Remote, repo: Path, commit: str, scratch: Path) -> None:
    if _succeeds(commands.ssh(remote, commands.has_image_script(commit))):
        return
    typer.echo(f"Building image {commands.image(commit)} on {remote.destination} ...")
    archive = write_source_archive(repo, commit, scratch / f"{commit}.tar")
    _execute(commands.ssh(remote, commands.prepare_source_script(remote)))
    _execute(commands.scp_to(remote, str(archive), remote.path("src")))
    _execute(commands.ssh(remote, commands.build_script(remote, commit)))


@remote_app.command("run")
def run(
    job_file: Path,
    host: str = HOST_OPTION,
    remote_dir: str = DIR_OPTION,
    workers: int = typer.Option(DEFAULT_WORKERS, min=1, help="Forge processes on the remote."),
) -> None:
    """Start a job on the remote, or resume it from its last saved game."""
    remote = Remote(host, remote_dir)
    spec = load_job(job_file)
    try:
        commit = clean_head_commit(Path.cwd())
    except SourceError as error:
        raise typer.BadParameter(str(error)) from None
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp)
        _ensure_image(remote, Path.cwd(), commit, scratch)
        try:
            bundle = write_bundle(spec, scratch / "bundle", commit, workers)
        except BundleError as error:
            raise typer.BadParameter(str(error)) from None
        start = scratch / commands.START_FILE
        start.write_text(commands.start_script(remote, commit, spec.name, workers), "utf-8")
        _execute(commands.ssh(remote, commands.prepare_job_script(remote, spec.name)))
        _execute(commands.scp_to(remote, str(bundle), remote.path("jobs", spec.name)))
        _execute(commands.scp_to(remote, str(start), remote.path("jobs", spec.name)))
    _execute(commands.ssh(remote, commands.launch_script(remote, spec.name)))
    typer.echo(
        f"Started {spec.name} on {remote.destination} with {workers} workers. "
        f"Check it with: commander-sim remote status {spec.name}"
    )


@remote_app.command("status")
def status(job: str, host: str = HOST_OPTION, remote_dir: str = DIR_OPTION) -> None:
    """Container state, games done and the last log lines of a remote job."""
    remote = Remote(host, remote_dir)
    _execute(commands.ssh(remote, commands.status_script(remote, job)))


@remote_app.command("stop")
def stop(job: str, host: str = HOST_OPTION, remote_dir: str = DIR_OPTION) -> None:
    """Stop a remote job cleanly; `remote run` with the same job file resumes it."""
    remote = Remote(host, remote_dir)
    _execute(commands.ssh(remote, commands.stop_script(remote, job)), echo=False)
    typer.echo(f"Stopped {job}; the watchdog will leave it alone. Finished games are saved.")


@remote_app.command("fetch")
def fetch(
    job: str,
    host: str = HOST_OPTION,
    remote_dir: str = DIR_OPTION,
    runs_dir: Path = Path("runs"),
    playgroup: Path = DEFAULT_PLAYGROUP_FILE,
) -> None:
    """Copy a consistent snapshot of a remote job's results here and build its report.

    Safe while the job is still running.
    """
    remote = Remote(host, remote_dir)
    target = runs_dir / f"{job}@{remote.label}"
    target.mkdir(parents=True, exist_ok=True)
    _execute(commands.ssh(remote, commands.snapshot_script(remote, job)), echo=False)
    database = target / "results.sqlite"
    _execute(
        commands.scp_from(
            remote, remote.path("jobs", job, "fetch", "results.sqlite"), str(database)
        )
    )
    report = write_report(
        load_databases([database]), load_owners(playgroup), target / "report.html"
    )
    typer.echo(f"Fetched {database}\nReport: {report}")


@watchdog_app.command("install")
def watchdog_install(host: str = HOST_OPTION, remote_dir: str = DIR_OPTION) -> None:
    """Every 10 minutes, resume jobs whose container is gone or stopped unfinished
    (someone stopped it, the machine rebooted). Jobs stopped with `remote stop` are left alone."""
    remote = Remote(host, remote_dir)
    _execute(commands.ssh(remote, commands.install_watchdog_script(remote)))
    typer.echo(f"Watchdog installed; it logs to {remote.path(commands.WATCHDOG_LOG)}.")


@watchdog_app.command("remove")
def watchdog_remove(host: str = HOST_OPTION, remote_dir: str = DIR_OPTION) -> None:
    """Remove the watchdog's cron entry and script; other cron entries are kept."""
    remote = Remote(host, remote_dir)
    _execute(commands.ssh(remote, commands.remove_watchdog_script(remote)))
    typer.echo("Watchdog removed.")
