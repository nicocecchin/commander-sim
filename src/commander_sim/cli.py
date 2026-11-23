"""Command line interface."""

from pathlib import Path

import typer

from commander_sim.forge.install import PINNED_RELEASE, install_forge

app = typer.Typer(no_args_is_help=True, help="Headless Forge Commander simulation harness.")
forge_app = typer.Typer(no_args_is_help=True, help="Manage the local Forge installation.")
app.add_typer(forge_app, name="forge")

DEFAULT_VENDOR_DIR = Path("vendor") / "forge"


@forge_app.command("setup")
def forge_setup(vendor_dir: Path = DEFAULT_VENDOR_DIR) -> None:
    """Download the pinned Forge release into vendor_dir (skipped if already present)."""
    typer.echo(f"Installing Forge {PINNED_RELEASE.version} into {vendor_dir} ...")
    installed = install_forge(PINNED_RELEASE, vendor_dir)
    typer.echo(f"Forge {PINNED_RELEASE.version} ready at {installed}")
