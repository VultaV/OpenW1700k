#!/usr/bin/env python3
"""Run the board defaults with stubbed UCI, including restored upgrade settings."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "target/linux/airoha/an7581/base-files/etc/uci-defaults/99-w1700k-log-size"
STUBS = r'''
board_name() { printf '%s\n' "$TEST_BOARD"; }
uci() {
	printf '%s\n' "$*" >> "$TEST_CALLS"
	case "$*" in
		'-q get system.@system[0].log_size')
			[ -f "$TEST_SIZE" ] && cat "$TEST_SIZE" ;;
		'set system.@system[0].log_size=1024')
			[ "$TEST_SET_FAIL" != 1 ] || return 1
			printf 1024 > "$TEST_SIZE" ;;
		'commit system') [ "$TEST_COMMIT_FAIL" != 1 ] ;;
		*) return 2 ;;
	esac
}
'''


def main():
    source = SCRIPT.read_text()
    assert source.count(". /lib/functions.sh") == 1
    count = 0
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        functions = tmp / "functions.sh"
        functions.write_text(STUBS)
        script = tmp / SCRIPT.name
        script.write_text(source.replace(". /lib/functions.sh", '. "$TEST_FUNCTIONS"'))
        size, calls = tmp / "log_size", tmp / "calls"
        env = dict(os.environ, TEST_FUNCTIONS=str(functions), TEST_SIZE=str(size),
                   TEST_CALLS=str(calls), TEST_SET_FAIL="0", TEST_COMMIT_FAIL="0")

        def run(board, value, **overrides):
            size.unlink(missing_ok=True)
            calls.unlink(missing_ok=True)
            if value is not None:
                size.write_text(value)
            result = subprocess.run(["sh", str(script)], capture_output=True, text=True,
                                    env=dict(env, TEST_BOARD=board, **overrides), timeout=5)
            commands = calls.read_text().splitlines() if calls.exists() else []
            return result.returncode, size.read_text() if size.exists() else None, commands

        for board in ("gemtek,w1700k-ubi", "airoha,an7581-evb", ""):
            for old in (None, "", "128", "64", "256", "1024", "1280", "0"):
                code, new, commands = run(board, old)
                change = board == "gemtek,w1700k-ubi" and old in (None, "", "128")
                assert code == 0 and new == ("1024" if change else old), (board, old, new)
                assert commands == (["-q get system.@system[0].log_size"] + (
                    ["set system.@system[0].log_size=1024", "commit system"] if change else []
                ) if board == "gemtek,w1700k-ubi" else []), commands
                count += 1

        # A fresh image reruns its defaults after restoring /etc/config/system.
        # Both the migrated value and later explicit user choices must survive.
        for kept in ("1024", "512", "2048"):
            code, new, commands = run("gemtek,w1700k-ubi", kept)
            assert code == 0 and new == kept and len(commands) == 1
            count += 1

        for failure in ("TEST_SET_FAIL", "TEST_COMMIT_FAIL"):
            code, _, commands = run("gemtek,w1700k-ubi", "128", **{failure: "1"})
            assert code != 0, failure  # boot must retain the defaults script for retry
            if failure == "TEST_SET_FAIL":
                assert "commit system" not in commands
            count += 1

    print(f"PASS: {count} log-default checks (board, unset/stock/custom, kept settings, failures)")


if __name__ == "__main__":
    main()
