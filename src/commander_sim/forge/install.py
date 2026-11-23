"""Download and unpack a pinned Forge release into a local directory."""

import hashlib
import tarfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

_RELEASE_URL = (
    "https://github.com/Card-Forge/forge/releases/download/forge-{v}/forge-installer-{v}.tar.bz2"
)
_CHUNK = 1 << 20
DEFAULT_VENDOR_DIR = Path("vendor") / "forge"


@dataclass(frozen=True)
class ForgeRelease:
    version: str
    sha256: str

    @property
    def url(self) -> str:
        return _RELEASE_URL.format(v=self.version)


PINNED_RELEASE = ForgeRelease(
    version="2.0.16",
    sha256="feb1338c2f4a8c62e9289b6270caa7fcc38f2441d5ec4d7cff237c2c1a3b15d0",
)


def download(url: str, dest: Path) -> str:
    """Stream `url` to `dest` and return the sha256 hex digest of the content."""
    digest = hashlib.sha256()
    with urllib.request.urlopen(url) as response, dest.open("wb") as out:
        while chunk := response.read(_CHUNK):
            digest.update(chunk)
            out.write(chunk)
    return digest.hexdigest()


def install_forge(release: ForgeRelease, vendor_dir: Path) -> Path:
    """Install `release` under `vendor_dir/<version>` and return that directory.

    Does nothing if that version is already installed. The archive is verified against the
    pinned checksum before being extracted.
    """
    target = vendor_dir / release.version
    if target.is_dir():
        return target
    vendor_dir.mkdir(parents=True, exist_ok=True)
    archive = vendor_dir / f"forge-{release.version}.tar.bz2"
    try:
        actual = download(release.url, archive)
        if actual != release.sha256:
            raise RuntimeError(
                f"Checksum mismatch for {release.url}: expected {release.sha256}, got {actual}"
            )
        staging = vendor_dir / f".{release.version}.partial"
        with tarfile.open(archive) as tar:
            tar.extractall(staging, filter="data")
        staging.rename(target)
    finally:
        archive.unlink(missing_ok=True)
    return target
