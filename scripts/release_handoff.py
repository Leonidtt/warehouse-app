"""Verify the deployed checkout and print a public, machine-readable report."""

import argparse
import hashlib
import json
import subprocess
import time
from datetime import datetime, timezone
from http.client import HTTPException
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = "https://warehouse-app-production-3e9d62c2.up.railway.app"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def app_fingerprint(commit):
    # Match /app/version. Read the commit, even if files in the checkout were edited.
    files = git("ls-tree", "-z", "--name-only", f"{commit}:backend").decode().split("\0")
    digest = hashlib.sha256()
    for name in sorted(files):
        if Path(name).suffix in {".py", ".html", ".css", ".js"}:
            digest.update(name.encode() + b"\\0")
            digest.update(hashlib.sha256(git("show", f"{commit}:backend/{name}")).digest())
    return digest.hexdigest()[:20]


def check_endpoint(path, matches):
    try:
        with urlopen(PRODUCTION + path, timeout=5) as response:
            return int(response.status == 200 and matches(response.read(1_000_000)))
    except (OSError, HTTPException, ValueError):
        return 0


def production_checks(version):
    marker = f'<meta name="warehouse-app-version" content="{version}">'.encode()
    return {
        "health": check_endpoint("/health", lambda body: json.loads(body) == {"status": "ok"}),
        "version": check_endpoint("/app/version", lambda body: json.loads(body) == {"version": version}),
        "web": check_endpoint("/", lambda body: marker in body),
        "pwa": check_endpoint("/pwa/", lambda body: marker in body and b"/pwa/manifest.webmanifest" in body),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wait", type=int, default=0, metavar="SECONDS",
                        help="Retry while the expected build becomes available.")
    args = parser.parse_args()
    if args.wait < 0:
        parser.error("--wait must be nonnegative")

    commit = git("rev-parse", "HEAD").decode().strip()
    version = app_fingerprint(commit)
    deadline = time.monotonic() + args.wait
    while True:
        checks = production_checks(version)
        remaining = deadline - time.monotonic()
        if all(checks.values()) or remaining <= 0:
            break
        time.sleep(min(5, remaining))

    print(json.dumps({
        "schema": 1,
        "source_commit": commit,
        "app_fingerprint": version,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "checks": checks,
    }, separators=(",", ":")))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
