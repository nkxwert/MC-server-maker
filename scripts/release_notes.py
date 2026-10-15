"""Print the release notes (from CHANGELOG.md) for the current APP_VERSION.

Used by the build workflow:  python scripts/release_notes.py > notes.md
Exits with an error when CHANGELOG.md has no section for the version, so a release is never
published without notes.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mc_server_maker import APP_VERSION  # noqa: E402
from mc_server_maker.core.updater import release_body  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--version":
        print(APP_VERSION)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(release_body((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), APP_VERSION))
