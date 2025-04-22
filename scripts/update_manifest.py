"""manifest.json updater."""
import json
import sys


def update_manifest(new_version: str) -> None:
    """Update the version in the manifest.json file."""
    manifest_path = "custom_components/ipx800v4/manifest.json"

    try:
        with open(manifest_path, "r", encoding="UTF-8") as f:
            manifest = json.load(f)

        manifest["version"] = new_version

        with open(manifest_path, "w", encoding="UTF-8") as f:
            json.dump(manifest, f, indent=2)
            f.write("\n")

        print(f"Updated {manifest_path} to version {new_version}")

    except FileNotFoundError:
        print(f"Error: {manifest_path} not found.")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Failed to parse {manifest_path}.")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python update_manifest.py <version>")
        sys.exit(1)

    version = sys.argv[1]
    update_manifest(version)
