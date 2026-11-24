"""A self-contained copy of a job: job file, the decks it uses, and a manifest."""

import json
import shutil
from pathlib import Path

import yaml

from commander_sim.config import JobSpec, WorkerSettings
from commander_sim.decks.dck_format import read_dck
from commander_sim.decks.model import deck_hash
from commander_sim.forge.install import PINNED_RELEASE

JOB_FILE = "job.yaml"
DECKS_DIR = "decks"
MANIFEST_FILE = "manifest.json"


class BundleError(RuntimeError):
    """The bundle could not be written."""


def write_bundle(spec: JobSpec, out_dir: Path, commit: str, max_workers: int | None) -> Path:
    """Write a bundle for `spec` into `out_dir` (replacing an earlier bundle there).

    The bundled job points at the bundle's own `decks/` folder. `max_workers` caps the worker
    count on the target machine, which matters inside containers where the CPU and RAM the
    Python process sees are the whole host's.
    """
    missing = [d for d in spec.deck_files if not (spec.decks_dir / d).is_file()]
    if missing:
        raise BundleError(f"Deck files not found in {spec.decks_dir}: {', '.join(missing)}")
    if out_dir.exists():
        if not (out_dir / MANIFEST_FILE).is_file():
            raise BundleError(f"{out_dir} exists and is not a bundle; refusing to replace it")
        shutil.rmtree(out_dir)
    (out_dir / DECKS_DIR).mkdir(parents=True)
    for deck in spec.deck_files:
        shutil.copyfile(spec.decks_dir / deck, out_dir / DECKS_DIR / deck)

    bundled = spec.model_copy(
        update={"decks_dir": Path(DECKS_DIR), "workers": WorkerSettings(max=max_workers)}
    )
    job = bundled.model_dump(mode="json")
    (out_dir / JOB_FILE).write_text(yaml.safe_dump(job, sort_keys=False), encoding="utf-8")
    manifest = {
        "job": spec.name,
        "commit": commit,
        "forge_version": PINNED_RELEASE.version,
        "deck_hashes": {d: deck_hash(read_dck(spec.decks_dir / d)) for d in spec.deck_files},
    }
    (out_dir / MANIFEST_FILE).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out_dir
