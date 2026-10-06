#!/usr/bin/env python3
"""Run the installed shell detector/rate limiter without router or root access."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "package/network/utils/w1700k-wifi-watchdog/files/w1700k-wifi-watchdog.sh"
SHELL = os.environ.get("WATCHDOG_TEST_SHELL", "/bin/sh")


def shell(body):
    result = subprocess.run(
        [SHELL, "-c", f'. {shlex.quote(str(SCRIPT))} --library\n{body}'],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout or f"exit {result.returncode}")
    return result.stdout


HELPERS = r'''
log() {
    detect_log "$1" "Mon Oct 5 12:00:00 2026 daemon.info hostapd: $2: STA $3 IEEE 802.11: $4"
}
assoc() { log "$1" "$2" "$3" 'associated (aid 1)' || :; }
deauth() { log "$1" "$2" "$3" 'deauthenticated due to local deauth request'; }
event() {
    assoc "$1" "$2" 02:00:00:00:00:01
    deauth "$1" "$2" 02:00:00:00:00:01
}
'''


class WatchdogTests(unittest.TestCase):
    def test_shell_syntax(self):
        subprocess.run([SHELL, "-n", str(SCRIPT)], check=True)

    def test_four_across_both_aps(self):
        shell(HELPERS + '''
event 100 ap-mld0 && exit 1
event 110 ap-mld0 && exit 2
event 120 phy0.0-ap0 && exit 3
event 160 phy0.0-ap0 || exit 4
''')

    def test_window_expires_and_same_ap_is_insufficient(self):
        shell(HELPERS + '''
event 100 ap-mld0 && exit 1
event 110 ap-mld0 && exit 2
event 120 ap-mld0 && exit 3
event 130 ap-mld0 && exit 4
event 191 phy0.0-ap0 && exit 5
exit 0
''')

    def test_unassociated_or_authenticated_only_does_not_count(self):
        shell(HELPERS + '''
for iface in ap-mld0 phy0.0-ap0; do
    for time in 100 110 120 130; do
        log "$time" "$iface" 02:00:00:00:00:01 authenticated && exit 1
        deauth "$time" "$iface" 02:00:00:00:00:01 && exit 2
    done
done
[ -z "$deauth_mld$deauth_legacy" ]
''')

    def test_deauth_consumes_association_and_old_association_expires(self):
        shell(HELPERS + '''
assoc 100 ap-mld0 02:00:00:00:00:01
deauth 110 ap-mld0 02:00:00:00:00:01 && exit 1
deauth 111 ap-mld0 02:00:00:00:00:01 && exit 2
set -- $deauth_mld
[ "$#" -eq 1 ] || exit 3
assoc 100 phy0.0-ap0 02:00:00:00:00:02
deauth 161 phy0.0-ap0 02:00:00:00:00:02 && exit 4
[ -z "$deauth_legacy" ]
''')

    def test_unrelated_ap_and_invalid_mac_are_ignored(self):
        shell(HELPERS + '''
assoc 100 other-ap 02:00:00:00:00:01
assoc 100 ap-mld0 invalid
[ -z "$known" ]
''')

    def test_poll_observation_can_qualify_deauth(self):
        shell(HELPERS + '''
remember_station 100 ap-mld0 02:00:00:00:00:01
deauth 110 ap-mld0 02:00:00:00:00:01 && exit 1
set -- $deauth_mld
[ "$#" -eq 1 ]
''')

    def test_idle_requires_previous_clients_and_more_than_five_minutes(self):
        shell('''
detect_empty 100 0 1 && exit 1
detect_empty 900 0 1 && exit 2
detect_empty 1000 1 1 && exit 3
detect_empty 1010 0 1 && exit 4
detect_empty 1310 0 1 && exit 5
detect_empty 1311 0 1 || exit 6
''')

    def test_failed_disabled_and_reassociation_break_empty_window(self):
        shell(HELPERS + '''
seen_clients=1
detect_empty 100 0 1 && exit 1
detect_empty 399 0 0 && exit 2
detect_empty 401 0 1 && exit 3
detect_empty 700 -1 1 && exit 4
detect_empty 702 0 1 && exit 5
assoc 1000 ap-mld0 02:00:00:00:00:01
detect_empty 1004 0 1 && exit 6
[ "$empty_since" = 1004 ]
''')

    def test_state_is_bounded(self):
        shell('''
i=0
while [ "$i" -lt 300 ]; do
    remember_station 100 ap-mld0 "$i"
    i=$((i + 1))
done
set -- $known
[ "$#" -eq 256 ]
''')

    def test_hour_limit_survives_service_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            setup = f"state_dir={shlex.quote(tmp)}\n"
            shell(setup + '''
reserve_snapshot 100 || exit 1
reserve_snapshot 3699 && exit 2
exit 0
''')
            shell(setup + '''
reserve_snapshot 3699 && exit 1
reserve_snapshot 3700 || exit 2
reserve_snapshot 3700 && exit 3
reserve_snapshot 7300 || exit 4
''')
            self.assertEqual((Path(tmp) / "last-snapshot").read_text(), "7300\n")

    def test_rate_limit_cannot_be_bypassed_by_backwards_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            shell(f"state_dir={shlex.quote(tmp)}\n" + '''
reserve_snapshot 100 || exit 1
reserve_snapshot 99 && exit 2
exit 0
''')

    def test_snapshot_section_byte_and_time_limits(self):
        output = shell('snapshot_section head -c 32768 /dev/zero')
        self.assertEqual(output.count("\0"), 16384)
        started = time.monotonic()
        shell('snapshot_section sleep 20')
        self.assertLess(time.monotonic() - started, 6)

    def test_daemon_cleans_up_logread_when_stopped_during_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            lines = []
            for iface in ["ap-mld0"] * 2 + ["phy0.0-ap0"] * 2:
                prefix = f"daemon.info hostapd: {iface}: STA 02:00:00:00:00:01 IEEE 802.11: "
                lines += [prefix + "associated (aid 1)", prefix + "deauthenticated due to local deauth request"]
            logread = path / "logread"
            logread.write_text(
                '#!/bin/sh\nprintf "%s\\n" "$$" > ' + shlex.quote(str(path / "log.pid")) + "\n"
                + "printf '%s\\n' " + " ".join(map(shlex.quote, lines)) + "\nexec sleep 30\n"
            )
            logread.chmod(0o755)
            body = f'''
. {shlex.quote(str(SCRIPT))} --library
state_dir={shlex.quote(str(path / "state"))}
uptime_seconds() {{ now=100; }}
poll_stations() {{ :; }}
capture_snapshot() {{
    printf '%s\\n' "$2" > "$state_dir/reason"
    sleep 2
}}
main
'''
            env = dict(os.environ, PATH=str(path) + ":" + os.environ["PATH"])
            process = subprocess.Popen([SHELL, "-c", body], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 5
                reason = path / "state/reason"
                while not reason.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(reason.exists(), "daemon did not detect streamed synthetic burst")
                self.assertEqual(reason.read_text(), "local-deauth-burst\n")
                self.assertEqual(reason.stat().st_mode & 0o777, 0o600)
                self.assertEqual(reason.parent.stat().st_mode & 0o777, 0o700)
                process.terminate()
                process.communicate(timeout=5)
                self.assertFalse((path / "state/log.fifo").exists())
                log_pid = int((path / "log.pid").read_text())
                with self.assertRaises(ProcessLookupError):
                    os.kill(log_pid, 0)
            finally:
                if (path / "log.pid").exists():
                    try:
                        os.kill(int((path / "log.pid").read_text()), 15)
                    except ProcessLookupError:
                        pass
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
