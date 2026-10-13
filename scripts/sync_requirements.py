"""Pin the manifest requirements to the versions locked in uv.lock.

uv.lock is the source of truth for the libraries pinned with "==" in
manifest.json: Dependabot bumps them there, the tests run with them, and the
release copies their locked versions to the manifest.

Usage:
    python scripts/sync_requirements.py          # update manifest.json
    python scripts/sync_requirements.py --print  # print the requirements
"""

import argparse
import json
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parent.parent
PINNED = re.compile(r"^(?P<name>[A-Za-z0-9._-]+)==(?P<version>\S+)$")


def normalize(name: str) -> str:
    """Normalize a package name (PEP 503)."""
    return re.sub(r"[-_.]+", "-", name).lower()


def locked_requirements(requirements: list[str]) -> list[str]:
    """Return the requirements, the pinned ones at their locked version."""
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked: dict[str, set[str]] = {}
    for package in lock["package"]:
        locked.setdefault(normalize(package["name"]), set()).add(package["version"])

    result = []
    for requirement in requirements:
        if match := PINNED.match(requirement):
            versions = locked.get(normalize(match["name"]))
            if not versions:
                raise SystemExit(f"{match['name']} is not in uv.lock")
            if len(versions) > 1:
                raise SystemExit(f"{match['name']} has several locked versions")
            requirement = f"{match['name']}=={versions.pop()}"
        result.append(requirement)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--print", action="store_true", help="print instead of updating"
    )
    args = parser.parse_args()

    (manifest_path,) = ROOT.glob("custom_components/*/manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    requirements = locked_requirements(manifest["requirements"])

    if args.print:
        print("\n".join(requirements))
    elif requirements != manifest["requirements"]:
        manifest["requirements"] = requirements
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Updated {manifest_path} requirements: {', '.join(requirements)}")


if __name__ == "__main__":
    main()
