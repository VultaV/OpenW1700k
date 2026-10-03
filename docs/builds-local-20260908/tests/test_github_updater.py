#!/usr/bin/env python3
"""Run with python3 tests/test_github_updater.py (requires jq and Node.js).

All network, ubus, and sysupgrade commands are mocked; /tmp paths in script
copies are redirected into a private directory. Nothing is flashed.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CGI = ROOT / "user/default/files/www/cgi-bin"
FIRMWARE = b"test sysupgrade image\n"
DIGEST = hashlib.sha256(FIRMWARE).hexdigest()
RELEASE = json.loads((ROOT / "tests/fixtures/ubi2-release-2026-09-07.json").read_text())
NAME = RELEASE["assets"][0]["name"]
TAG = RELEASE["tag_name"]
URL = "https://github.com/w1700k/builds/releases/download/" + TAG + "/"
TOKEN = "1" * 32
BASELINE = "9449e4ca242ab30278df20940d6654ddc1c102e8"

MOCK = r'''
import hashlib, json, os, pathlib, sys
name, args = pathlib.Path(sys.argv[0]).name, sys.argv[1:]
p = pathlib.Path(os.environ["CASE_DIR"])
c = json.loads((p / "case.json").read_text())
with (p / "calls").open("a") as log:
    log.write(name + " " + json.dumps(args) + "\n")
if name == "ubus":
    access = json.loads(args[-1])
    allowed = access["ubus_rpc_session"] == "1" * 32 and not c.get("deny")
    allowed = allowed and not (c.get("deny_file") and access["scope"] == "file")
    print(json.dumps({"access": allowed}))
elif name == "curl":
    url = args[-1]
    if "api.github.com" in url:
        data = json.dumps(c["releases"] if url.endswith("/releases") else c["release"]).encode()
        failed = c.get("metadata_error")
    elif url.endswith("sha256sums"):
        data = c.get("sums", "").encode()
        failed = c.get("sums_error")
    else:
        data = pathlib.Path(c["firmware_file"]).read_bytes() if c.get("firmware_file") else c.get("firmware", "test sysupgrade image\n").encode()
        failed = c.get("download_error")
    if failed and any(a.startswith("-") and not a.startswith("--") and "f" in a for a in args):
        sys.exit(22)
    if failed:
        data = b"404 Not Found\n"
    if "-o" in args:
        pathlib.Path(args[args.index("-o") + 1]).write_bytes(data)
    else:
        sys.stdout.buffer.write(data)
    if c.get("partial") and "api.github.com" not in url:
        sys.exit(18)
elif name == "sha256sum":
    print(hashlib.sha256(pathlib.Path(args[0]).read_bytes()).hexdigest() + "  " + args[0])
elif name == "sysupgrade":
    assert args[0] == "--test", "Flashing is forbidden in this check"
    expected = pathlib.Path(c["firmware_file"]).read_bytes() if c.get("firmware_file") else b"test sysupgrade image\n"
    assert pathlib.Path(args[1]).read_bytes() == expected
    sys.exit(1 if c.get("incompatible") else 0)
'''


def run_case(name, changes=None, *, method="POST", session=TOKEN, script="github_fetch", baseline=False):
    with tempfile.TemporaryDirectory(prefix="github-updater-test-") as folder:
        folder = Path(folder)
        release = copy.deepcopy(RELEASE)
        # The release metadata comes from GitHub; ordinary cases use a tiny mocked payload.
        release["assets"][0]["digest"] = "sha256:" + DIGEST
        case = {"release": release, "releases": [release]}
        if changes:
            changes(case)
        (folder / "case.json").write_text(json.dumps(case))
        source = subprocess.check_output(["git", "show", BASELINE + ":user/default/files/www/cgi-bin/" + script], cwd=ROOT, text=True) if baseline else (CGI / script).read_text()
        target = folder / script
        target.write_text(source.replace("/tmp/", str(folder) + "/"))
        image = folder / "firmware.bin"
        image.write_bytes(b"previous image")
        for command in ("curl", "ubus", "sha256sum", "sysupgrade"):
            mock = folder / command
            mock.write_text("#!" + sys.executable + "\n" + MOCK)
            mock.chmod(0o700)
        body = json.dumps({"tag": TAG, "sessionid": session})
        env = dict(os.environ, PATH=str(folder) + os.pathsep + os.environ["PATH"],
                   CASE_DIR=str(folder), REQUEST_METHOD=method, CONTENT_LENGTH=str(len(body)),
                   QUERY_STRING="tag=" + TAG)
        result = subprocess.run(["sh", str(target)], input=body, env=env, capture_output=True, text=True, timeout=10)
        data = json.loads(result.stdout.split("\n\n", 1)[1])
        calls = (folder / "calls").read_text() if (folder / "calls").exists() else ""
        if baseline:
            assert data.get("success") is True and image.read_bytes() != b"previous image", (name, data)
            return
        assert not list(folder.glob("github_firmware.*")), name + ": staging files leaked"
        if script == "github_check":
            if "expected" in case:
                assert result.returncode == 0 and data == case["expected"], (name, data)
            else:
                assert result.returncode != 0 and "error" in data, (name, data)
        elif name in ("success", "checksum fallback", "actual release firmware"):
            expected_firmware = Path(case["firmware_file"]).read_bytes() if case.get("firmware_file") else FIRMWARE
            expected_digest = hashlib.sha256(expected_firmware).hexdigest()
            assert result.returncode == 0 and data["success"] is True and data["sha256"] == expected_digest, (name, data)
            assert image.read_bytes() == expected_firmware and "sysupgrade" in calls, name
        else:
            assert result.returncode != 0 and "error" in data, (name, data)
            assert image.read_bytes() == b"previous image", name + ": previous image overwritten"
            if name in ("GET", "missing session", "denied session", "denied path"):
                assert "curl" not in calls, name + ": network used before authorization"
        print("PASS", name)


def fallback(case):
    case["release"]["assets"][0]["digest"] = None
    case["release"]["assets"].append({"name": "sha256sums", "browser_download_url": URL + "sha256sums"})
    case["sums"] = "0" * 64 + "  " + NAME + ".old\n" + DIGEST + "  " + NAME + "\n"


if __name__ == "__main__":
    if "--firmware" in sys.argv:
        firmware_file = str(Path(sys.argv[sys.argv.index("--firmware") + 1]).resolve())
        assert hashlib.sha256(Path(firmware_file).read_bytes()).hexdigest() == RELEASE["assets"][0]["digest"].removeprefix("sha256:")
        run_case("actual release firmware", lambda c: c.update(release=copy.deepcopy(RELEASE), firmware_file=firmware_file))
    if "--prove-baseline" in sys.argv:
        run_case("baseline corrupt image accepted", lambda c: c.update(firmware="corrupt"), baseline=True)
        run_case("baseline HTTP error accepted", lambda c: c.update(download_error=True), baseline=True)
        print("CONFIRMED baseline accepts corrupt and HTTP error bodies as firmware")
        sys.exit(0)
    run_case("success")
    run_case("checksum fallback", fallback)
    run_case("GET", method="GET")
    run_case("missing session", session="")
    run_case("denied session", lambda c: c.update(deny=True))
    run_case("denied path", lambda c: c.update(deny_file=True))
    for flag in ("metadata_error", "download_error", "partial", "incompatible"):
        run_case(flag, lambda c, flag=flag: c.update({flag: True}))
    run_case("checksum mismatch", lambda c: c.update(firmware="corrupt"))
    run_case("missing digest", lambda c: c["release"]["assets"][0].update(digest=None))
    run_case("multiple images", lambda c: c["release"]["assets"].append(c["release"]["assets"][0]))
    run_case("external URL", lambda c: c["release"]["assets"][0].update(browser_download_url="https://example.com/firmware.bin"))
    run_case("checksum filename mismatch", lambda c: (fallback(c), c.update(sums=DIGEST + "  " + NAME + ".old\n")))
    run_case("checksum download failure", lambda c: (fallback(c), c.update(sums_error=True)))
    run_case("release list HTTP error", lambda c: c.update(metadata_error=True), script="github_check")
    run_case("invalid release list", lambda c: c.update(releases={"message": "rate limited"}), script="github_check")
    run_case("actual release list", lambda c: c.update(releases=[RELEASE], expected=[{"tag": TAG, "url": URL + NAME, "version": "gemtek_w1700k-ubi"}]), script="github_check")
    run_case("escaped release tags", lambda c: (c["release"].update(tag_name='tag"with\\quotes'), c.update(expected=[{"tag": 'tag"with\\quotes', "url": URL + NAME, "version": "gemtek_w1700k-ubi"}])), script="github_check")
    subprocess.run(["node", str(ROOT / "tests/test_github_updater_ui.js")], check=True)
