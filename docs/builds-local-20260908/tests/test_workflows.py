#!/usr/bin/env python3
"""Run actual workflow shell blocks against local build-command stubs."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ["fastbuild", "self-host-fastbuild", "fastbuild-base", "fastbuild-toolchain"]


def block(source, name):
    match = re.search(r"    - name: " + re.escape(name) + r"\n      run: \|\n((?:        .*\n|\n)+)", source)
    assert match, name
    return textwrap.dedent(match[1])


def executable(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/bash\n" + contents)
    path.chmod(0o755)


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source_dir = root / "source"
        source_dir.mkdir()
        executable(root / "bin/make", '''
echo "${MODE:-download}" >> "$ATTEMPTS"
case "$BUILD_CASE" in
  fail) echo "build failed"; exit 2 ;;
  retry) [ "$MODE" = s ] ;;
  success) exit 0 ;;
esac
''')
        executable(root / "bin/nproc", "echo 1\n")
        executable(root / "bin/sudo", "exit 0\n")
        executable(root / "bin/git", 'echo "$1" >> "$ATTEMPTS"\n[ "$1" != "$FAIL_GIT" ]\n')
        executable(source_dir / "staging_dir/host/bin/ccache", "exit 7\n")
        executable(root / "profile/pre_compile.sh", "exit 0\n")
        env = dict(os.environ, PATH=f"{root / 'bin'}:{os.environ['PATH']}",
                   DK_OPENWRT=str(source_dir), DK_PROFILE=str(root / "profile"),
                   ATTEMPTS=str(root / "attempts"))
        # Execute the nested bash exactly as Docker would, including its -e flag.
        docker = '''
docker_exec() {
  if [ "$1" = -e ]; then export "$2"; shift 2; fi
  shift
  "$@"
}
'''
        checks = 0
        for name in WORKFLOWS:
            source = (ROOT / f".github/workflows/{name}.yaml").read_text()
            compile_script = docker + block(source, "Compile OpenWrt")
            for case, expected_modes, success in [
                ("success", ["c"], True),
                ("retry", ["c", "s"], True),
                ("fail", ["c", "s"], False),
            ]:
                Path(env["ATTEMPTS"]).write_text("")
                result = subprocess.run(["bash", "-eo", "pipefail", "-c", compile_script],
                                        cwd=root, env=dict(env, BUILD_CASE=case), capture_output=True)
                assert (result.returncode == 0) == success, (name, case, result.returncode)
                modes = Path(env["ATTEMPTS"]).read_text().splitlines()
                assert modes == expected_modes, (name, case, modes)
                checks += 1
            Path(env["ATTEMPTS"]).write_text("")
            result = subprocess.run(["bash", "-eo", "pipefail", "-c", compile_script], cwd=root,
                                    env=dict(env, BUILD_CASE="success", DK_OPENWRT=str(root / "missing")),
                                    capture_output=True)
            assert result.returncode != 0 and not Path(env["ATTEMPTS"]).read_text(), name
            checks += 1
            download = next(line.strip() for line in block(source, "Prepare OpenWrt source").splitlines()
                            if line.strip().startswith("make download "))
            for case in ("success", "fail"):
                result = subprocess.run(["bash", "-e", "-c", download], cwd=root,
                                        env=dict(env, BUILD_CASE=case), capture_output=True)
                assert (result.returncode == 0) == (case == "success"), (name, "download", case)
                checks += 1
            prepare = block(source, "Prepare OpenWrt source")
            git_commands = prepare.split("  git fetch", 1)[1].split("  { git log", 1)[0]
            for fail, expected in [("fetch", ["fetch"]), ("checkout", ["fetch", "checkout"]),
                                   ("pull", ["fetch", "checkout", "pull"]), ("", ["fetch", "checkout", "pull"])]:
                Path(env["ATTEMPTS"]).write_text("")
                result = subprocess.run(["bash", "-e", "-c", "git fetch" + git_commands], cwd=root,
                                        env=dict(env, FAIL_GIT=fail, REPO_BRANCH="ubi2"), capture_output=True)
                assert (result.returncode == 0) == (not fail), (name, "git", fail)
                assert Path(env["ATTEMPTS"]).read_text().splitlines() == expected, (name, fail)
                checks += 1
            custom = next(line.strip() for line in prepare.splitlines() if 'bash "$bp/custom.sh"' in line)
            for code in (0, 2, None):
                path = root / "profile/custom.sh"
                if code is None:
                    path.unlink()
                else:
                    executable(path, f"exit {code}\n")
                result = subprocess.run(["bash", "-e", "-c", custom], cwd=root,
                                        env=dict(env, bp=str(path.parent)), capture_output=True)
                assert (result.returncode == 0) == (code != 2), (name, "custom", code)
                checks += 1
        source = (ROOT / ".github/workflows/self-host-fastbuild.yaml").read_text()
        initialize = block(source, "Initialize environment").split("curl ", 1)[0]
        for name in ("openwrt_bin", "firmware", "user/current", "ghcache", "stcache", "dlcache"):
            (root / name).mkdir(parents=True)
            (root / name / "stale").touch()
        subprocess.run(["bash", "-e", "-c", 'docker() { return 0; }; sudo() { "$@"; };\n' + initialize],
                       cwd=root, check=True)
        for name in ("openwrt_bin", "firmware", "user/current"):
            assert not (root / name / "stale").exists(), name
        for name in ("ghcache", "stcache", "dlcache"):
            assert (root / name / "stale").exists(), name
        checks += 1
        print(f"PASS: {checks} workflow build/source/download/workspace checks")


if __name__ == "__main__":
    main()
