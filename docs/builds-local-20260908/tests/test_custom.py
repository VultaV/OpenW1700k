#!/usr/bin/env python3
"""Verify custom overlay installation succeeds or immediately reports failure."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "user/default/custom.sh"
OVERVIEW = Path("feeds/luci/applications/luci-app-attendedsysupgrade/htdocs/luci-static/resources/view/attendedsysupgrade/overview.js")
PATCH = Path("feeds/luci/modules/luci-mod-status/patches/998-single-wiphy.patch")

for missing in (None, "overview.js", "998-single-wiphy.patch", "destination"):
    with tempfile.TemporaryDirectory(prefix="custom-overlay-test-") as folder:
        folder = Path(folder)
        (folder / "files").mkdir()
        if missing != "destination":
            (folder / OVERVIEW).parent.mkdir(parents=True)
        for name in ("overview.js", "998-single-wiphy.patch"):
            if missing != name:
                (folder / "files" / name).write_text(name)
        result = subprocess.run(["bash", str(SCRIPT)], cwd=folder, capture_output=True, text=True)
        if missing is None:
            assert result.returncode == 0, result.stderr
            assert (folder / OVERVIEW).read_text() == "overview.js"
            assert (folder / PATCH).read_text() == "998-single-wiphy.patch"
        else:
            assert result.returncode != 0, f"Missing {missing} was silently ignored"
        print("PASS custom overlay", missing or "success")
