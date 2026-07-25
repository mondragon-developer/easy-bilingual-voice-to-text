"""Regenerates requirements-lock.txt with artifact hashes from the PyPI API.

Version pins only promise the right version *number*: pip will install a
re-uploaded or hijacked artifact that keeps the same version. Hashes promise
the right bytes, so CI can install the release dependencies with
--require-hashes and a compromised upload cannot reach a signed build.

Run after changing any pinned version:

    python scripts/lock_hashes.py

Every published artifact for a pinned version is listed, not just the Windows
wheel, so the lockfile stays installable on other platforms (pip enforces
hash checking for the whole file as soon as one entry carries a hash).
"""

import json
import re
import urllib.request
from pathlib import Path

LOCKFILE = Path(__file__).resolve().parent.parent / "requirements-lock.txt"

HEADER = """\
# Exact versions AND artifact hashes used to build the official release
# binaries. Regenerate with:  python scripts/lock_hashes.py
#
#   pip install --require-hashes -r requirements-lock.txt
#
# Source installs can use the friendlier ranges in requirements.txt; this
# file records what actually ships inside the downloadable builds.
"""

GPU_HEADER = "# Windows/Linux GPU runtime (bundled only in the GPU build)"

PIN = re.compile(r"^([A-Za-z0-9._-]+)==([^;\s\\]+)\s*(?:;\s*(.+?))?\s*\\?$")


def hashes_for(name, version):
    """Every non-yanked sha256 PyPI publishes for one pinned version."""
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    with urllib.request.urlopen(url, timeout=60) as resp:
        data = json.load(resp)
    digests = sorted({f["digests"]["sha256"] for f in data["urls"]
                      if not f.get("yanked")})
    if not digests:
        raise SystemExit(f"{name}=={version}: no installable artifacts on PyPI")
    return digests


def render(name, version, marker):
    """One pip requirement block: the pin, then its hashes, continued lines."""
    pin = f"{name}=={version}"
    if marker:
        pin += f" ; {marker}"
    return " \\\n    ".join([pin] + [f"--hash=sha256:{h}"
                                     for h in hashes_for(name, version)])


def read_pins(path):
    """Parse the current lockfile into (name, version, marker), GPU last.

    Hash lines from a previous run are skipped, so the file regenerates
    from itself.
    """
    main, gpu = [], []
    bucket = main
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith(GPU_HEADER[:20]):
            bucket = gpu
            continue
        if not line or line.startswith("#") or line.startswith("--hash="):
            continue
        match = PIN.match(line)
        if not match:
            raise SystemExit(f"unparsed lockfile line: {line}")
        bucket.append(match.groups())
    return main, gpu


def main():
    pins, gpu = read_pins(LOCKFILE)
    body = HEADER + "\n".join(render(*p) for p in pins)
    body += f"\n\n{GPU_HEADER}\n" + "\n".join(render(*p) for p in gpu) + "\n"
    LOCKFILE.write_text(body, encoding="utf-8", newline="\n")
    print(f"{LOCKFILE.name}: {len(pins) + len(gpu)} packages, "
          f"{body.count('--hash=')} hashes")


if __name__ == "__main__":
    main()
